import shutil
import subprocess

import pytest

from app.models import Claim, CoarseScan, VideoUnderstanding
from app.pipeline import exercise as exercise_step
from app.pipeline.exercise import identify, slugify
from app.pipeline.scan import exercise_window
from app.pipeline.understand import merge_text
from app.pipeline.video import extract_frames, frame_times, probe_duration
from app.profiling import ExerciseDraft
from tests.test_exercises import make_exercise

UNDERSTANDING = VideoUnderstanding(
    movement_description="Athlete steps off a box and jumps up immediately after landing.",
    on_screen_text=["+10 cm in 4 weeks"],
    equipment_seen=["box"],
    execution_notes="short ground contact",
)


def test_frame_times_are_centred_and_inside_window():
    times = frame_times(0.0, 8.0, 8)
    assert times == [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5]
    assert frame_times(10.0, 14.0, 4) == [10.5, 11.5, 12.5, 13.5]


def test_exercise_window_pads_one_frame_spacing_and_clamps():
    times = frame_times(0.0, 40.0, 8)  # 2.5, 7.5, ..., 37.5; spacing 5 s
    scan = CoarseScan(exercise_frames=[3, 4, 5], on_screen_text=[], multiple_exercises=False)
    assert exercise_window(scan, times, 40.0) == (12.5, 32.5)

    edge = CoarseScan(exercise_frames=[0, 7], on_screen_text=[], multiple_exercises=False)
    assert exercise_window(edge, times, 40.0) == (0.0, 40.0)


def test_exercise_window_ignores_bad_indices_and_returns_none_without_exercise():
    times = frame_times(0.0, 40.0, 8)
    bad = CoarseScan(exercise_frames=[-1, 8, 99], on_screen_text=[], multiple_exercises=False)
    assert exercise_window(bad, times, 40.0) is None


def test_merge_text_keeps_intro_text_and_drops_duplicates():
    merged = merge_text(["+10 CM IN 4 WEEKS", "Do this daily"], ["+10 cm  in 4 weeks", "Rep 3"])
    assert merged == ["+10 CM IN 4 WEEKS", "Do this daily", "Rep 3"]


def test_slugify():
    assert slugify("Single-Leg Depth Jump!") == "single-leg-depth-jump"
    assert slugify("???") == "unknown-exercise"


def test_identify_returns_db_profile_for_known_exercise(monkeypatch):
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs["schema_model"])
        return Claim(exercise_name="Box Jump", promised_effect="+10 cm", target_audience="athletes",
                     matched_exercise_id="box-jump", match_confidence=0.9)

    monkeypatch.setattr(exercise_step, "call_json_schema", fake_call)
    claim, profile = identify(UNDERSTANDING, None, [make_exercise()])
    assert profile.id == "box-jump" and not profile.auto_profiled
    assert calls == [Claim]


def test_identify_profiles_unknown_exercise_without_saving(monkeypatch):
    draft_data = make_exercise(id="whatever").model_dump(exclude={"reviewed", "auto_profiled"})
    draft_data["equipment"] = ["box", "spaceship"]

    def fake_call(**kwargs):
        if kwargs["schema_model"] is Claim:
            return Claim(exercise_name="Banded Depth Drop", promised_effect="", target_audience="",
                         matched_exercise_id="not-in-db", match_confidence=0.3)
        return ExerciseDraft.model_validate(draft_data)

    monkeypatch.setattr(exercise_step, "call_json_schema", fake_call)
    claim, profile = identify(UNDERSTANDING, "caption", [make_exercise()])
    assert claim.matched_exercise_id is None
    assert profile.id == "banded-depth-drop"
    assert profile.name == "Banded Depth Drop"
    assert profile.auto_profiled and not profile.reviewed
    assert profile.equipment == ["box"]  # unknown equipment clamped away


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_extract_frames_from_synthetic_video(tmp_path):
    video = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=4:size=1280x720:rate=25",
         "-pix_fmt", "yuv420p", str(video)],
        check=True,
    )
    duration = probe_duration(video)
    assert 3.9 < duration < 4.1
    frames = extract_frames(video, frame_times(0.0, duration), max_edge=384)
    assert len(frames) == 8
    assert all(f.startswith(b"\xff\xd8") for f in frames)  # JPEG magic bytes
