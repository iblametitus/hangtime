import time

import pytest
from fastapi.testclient import TestClient

from app import jobs, plans
from app.demo import DEMO_PLAN, DEMO_PROFILE
from app.main import app
from app.models import Citation, ExternalSource, Segment, VideoUnderstanding
from app.pipeline import run
from app.pipeline.swap import SwapResult
from tests.test_evidence import CLAIM, make_card, make_verdict
from tests.test_exercises import make_exercise

client = TestClient(app)


def demo_swap() -> SwapResult:
    """Real swap: a depth jump into the demo plan on a Monday replaces the box jump."""
    from app.exercises import load_exercises
    from app.pipeline.swap import propose_swap
    exercises = load_exercises()
    depth_jump = next(e for e in exercises if e.id == "depth-jump")
    return propose_swap(depth_jump, DEMO_PROFILE, DEMO_PLAN, exercises, 0)


def fake_result(segment: int = 0, swap: SwapResult | None = None) -> run.AnalysisResult:
    verdict = make_verdict([
        Citation(source_id="doe-2020", quote="Plyometric training improved CMJ height (ES = 0.84)."),
        Citation(source_id="web-1", quote="Depth jumps increased jump height."),
    ])
    return run.AnalysisResult(
        duration_s=30.0,
        segments=[Segment(name="Box Jump", start_s=0, end_s=8, frame_count=9),
                  Segment(name="Pogo Hops", start_s=10, end_s=18, frame_count=5)],
        selected_segment=segment,
        scan=None,
        understanding=VideoUnderstanding(movement_description="", on_screen_text=[], equipment_seen=[], execution_notes=""),
        claim=CLAIM,
        profile=make_exercise(id="depth-jump", name="Depth Jump") if swap else make_exercise(),
        cards=[make_card("doe-2020", ["box-jump"])],
        web=[ExternalSource(id="web-1", title="Depth jump study", url="https://pubmed.ncbi.nlm.nih.gov/1",
                            snippet="Depth jumps increased jump height.")],
        swap=swap or SwapResult(proposal=None, session=None, blocked_reason=None,
                                note="No equivalent slot in your next session (Friday - Max strength)."),
        verdict=verdict,
        removed_citations=1,
        timings_s={"total": 17.2},
    )


class Calls(list):
    pass


@pytest.fixture(autouse=True)
def fake_pipeline(monkeypatch):
    calls = Calls()

    def analyse(path, user, plan, caption=None, segment=0, scan=None, on_step=None):
        calls.append({"caption": caption, "segment": segment, "plan": plan})
        for key in ["frames", "understand", "verdict"]:
            on_step(key, run.STEPS[key])
        return fake_result(segment, calls.swap if hasattr(calls, "swap") else None)

    monkeypatch.setattr(run, "analyse", analyse)
    monkeypatch.setattr(jobs, "probe_duration", lambda path: 30.0)
    jobs.clear()
    yield calls
    jobs.clear()


def wait_done(job_id: str) -> str:
    for _ in range(50):
        job = jobs.get(job_id)
        if job.status in ("done", "error"):
            break
        time.sleep(0.02)
    return client.get(f"/api/analyses/{job_id}").text


def upload(name: str = "drill.mp4", caption: str = "") -> str:
    response = client.post("/api/analyses", files={"video": (name, b"fake video", "video/mp4")}, data={"caption": caption})
    assert response.status_code == 200
    return response.text


def only_job() -> jobs.Job:
    return next(iter(jobs._jobs.values()))


def test_pages_render():
    assert "demo athlete" in client.get("/").text
    page = client.get("/demo").text
    assert "Box Jump" in page and "Analyse video" in page
    about = client.get("/about").text
    assert "Nemotron" in about and "Honest limits" in about


def test_upload_shows_progress_then_result_card(fake_pipeline):
    html = upload(caption="  +10 cm in 2 weeks ")
    assert "Analysing" in html or "Well supported" in html
    job = only_job()
    result = wait_done(job.id)
    assert "Well supported" in result and "Good fit for you" in result
    assert "Plyometric training improved CMJ height" in result
    assert "web source, not curated" in result
    assert "1 unverifiable quote was removed" in result
    assert "Check Pogo Hops" in result and "Check Box Jump" not in result
    assert "No equivalent slot" in result
    assert fake_pipeline[0]["caption"] == "+10 cm in 2 weeks"


def test_check_other_exercise_reuses_video(fake_pipeline):
    upload()
    first = only_job()
    wait_done(first.id)
    client.post(f"/api/analyses/{first.id}/segments/1")
    second = next(j for j in jobs._jobs.values() if j.id != first.id)
    assert second.video == first.video
    assert "Check Box Jump" in wait_done(second.id)
    assert fake_pipeline[1]["segment"] == 1


def test_rejects_non_video_and_long_video(monkeypatch):
    assert "Please upload a video file" in upload("notes.txt")
    monkeypatch.setattr(jobs, "probe_duration", lambda path: 200.0)
    upload()
    assert "longer than 3 minutes" in wait_done(only_job().id)


def test_progress_marks_steps():
    job = jobs.Job(id="x", video=jobs.new_video_path(".mp4"), user=None, plan=None, caption=None,
                   steps=["frames", "understand"])
    from app.web import _progress
    states = dict(_progress(job))
    assert states[run.STEPS["frames"]] == "done"
    assert states[run.STEPS["understand"]] == "current"
    assert states[run.STEPS["verdict"]] == "pending"
    assert run.STEPS["scan"] not in states


def test_unknown_analysis_expired():
    assert "expired" in client.get("/api/analyses/nope").text


def test_apply_swap_updates_only_this_sessions_plan(fake_pipeline):
    fake_pipeline.swap = demo_swap()
    client.cookies.set(plans.COOKIE, "session-a")
    try:
        upload()
        job = only_job()
        result = wait_done(job.id)
        assert "Apply swap to next session" in result
        assert "Box Jump</s>" in result and "Depth Jump" in result
        applied = client.post(f"/api/analyses/{job.id}/apply-swap").text
        assert "Added to your plan" in applied
        assert [e.exercise_id for e in plans.get_plan("session-a").sessions[0].exercises][0] == "depth-jump"
        assert plans.get_plan("someone-else").sessions[0].exercises[0].exercise_id == "box-jump"
        page = client.get("/demo").text
        assert "Updated" in page and "Reset demo plan" in page
        assert "Added to your plan" in client.post(f"/api/analyses/{job.id}/apply-swap").text  # idempotent
        client.get("/demo?reset=1")
        assert plans.get_plan("session-a").sessions[0].exercises[0].exercise_id == "box-jump"
    finally:
        client.cookies.clear()
        plans.reset("session-a")


def test_picking_an_athlete_changes_profile_and_plan(fake_pipeline):
    client.cookies.set(plans.COOKIE, "session-b")
    try:
        page = client.get("/demo?athlete=beginner").text
        assert "Goblet Squat" in page and "Back Squat" not in page
        upload()
        assert only_job().user.training_age_years == 0.5
        assert "Spanish Squat" in client.get("/demo?athlete=veteran").text
    finally:
        client.cookies.clear()
