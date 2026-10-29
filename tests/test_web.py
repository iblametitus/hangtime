import time

import pytest
from fastapi.testclient import TestClient

from app import jobs
from app.main import app
from app.models import Citation, ExternalSource, Segment, VideoUnderstanding
from app.pipeline import run
from tests.test_evidence import CLAIM, make_card, make_verdict
from tests.test_exercises import make_exercise

client = TestClient(app)


def fake_result(segment: int = 0) -> run.AnalysisResult:
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
        profile=make_exercise(),
        cards=[make_card("doe-2020", ["box-jump"])],
        web=[ExternalSource(id="web-1", title="Depth jump study", url="https://pubmed.ncbi.nlm.nih.gov/1",
                            snippet="Depth jumps increased jump height.")],
        verdict=verdict,
        removed_citations=1,
        timings_s={"total": 17.2},
    )


@pytest.fixture(autouse=True)
def fake_pipeline(monkeypatch):
    calls = []

    def analyse(path, user, caption=None, segment=0, scan=None, on_step=None):
        calls.append({"caption": caption, "segment": segment})
        for key in ["frames", "understand", "verdict"]:
            on_step(key, run.STEPS[key])
        return fake_result(segment)

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
    monkeypatch.setattr(jobs, "probe_duration", lambda path: 75.0)
    upload()
    assert "longer than 60 seconds" in wait_done(only_job().id)


def test_progress_marks_steps():
    job = jobs.Job(id="x", video=jobs.new_video_path(".mp4"), user=None, caption=None, steps=["frames", "understand"])
    from app.web import _progress
    states = dict(_progress(job))
    assert states[run.STEPS["frames"]] == "done"
    assert states[run.STEPS["understand"]] == "current"
    assert states[run.STEPS["verdict"]] == "pending"
    assert run.STEPS["scan"] not in states


def test_unknown_analysis_expired():
    assert "expired" in client.get("/api/analyses/nope").text
