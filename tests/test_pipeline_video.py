import shutil
import subprocess

import pytest

from app.models import Claim, CoarseScan, ScanPart, SeenExercise, VideoUnderstanding
from app.pipeline import exercise as exercise_step
from app.pipeline.exercise import identify, slugify
from app.pipeline.scan import MAX_WINDOW_S, exercise_window, longest_run, merge_parts, segments
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


def test_longest_run_prefers_longest_then_latest():
    assert longest_run([2, 5, 6, 7]) == [5, 6, 7]
    assert longest_run([0, 1, 4, 5]) == [4, 5]
    assert longest_run([]) == []


def test_exercise_window_pads_one_frame_spacing_and_clamps():
    times = frame_times(0.0, 24.0, 8)  # 1.5, 4.5, ..., 22.5; spacing 3 s
    assert exercise_window([4], times, 24.0) == (10.5, 16.5)
    assert exercise_window([0], times, 24.0) == (0.0, 4.5)


def test_exercise_window_caps_long_runs_around_their_centre():
    times = frame_times(0.0, 51.6, 8)  # the army demo from the 28.10. test
    start, end = exercise_window([2, 5, 6, 7], times, 51.6)
    assert end - start == pytest.approx(MAX_WINDOW_S)
    assert start > 35  # inside the 5-7 block, not the isolated frame 2


def test_exercise_window_ignores_bad_indices():
    assert exercise_window([-1, 8, 99], frame_times(0.0, 40.0, 8), 40.0) is None


def test_merge_parts_maps_to_global_indices_and_joins_same_name():
    part1 = ScanPart(exercises=[SeenExercise(name="Box Jump", frames=[5, 6, 7, 9])], on_screen_text=["+10 cm"])
    part2 = ScanPart(
        exercises=[SeenExercise(name="box jump ", frames=[0, 1]), SeenExercise(name="Pogo Hops", frames=[4, 5, 6])],
        on_screen_text=["Day 1"],
    )
    scan = merge_parts([part1, part2])
    assert [(e.name, e.frames) for e in scan.exercises] == [("Box Jump", [5, 6, 7, 8, 9]), ("Pogo Hops", [12, 13, 14])]
    assert scan.on_screen_text == ["+10 cm", "Day 1"]


def test_merge_parts_drops_dunks_and_game_play():
    part = ScanPart(
        exercises=[SeenExercise(name="Basketball Dunk", frames=[0, 1, 2]), SeenExercise(name="Depth Jump", frames=[4])],
        on_screen_text=[],
    )
    assert [e.name for e in merge_parts([part]).exercises] == ["Depth Jump"]


def test_segments_put_main_exercise_first():
    scan = CoarseScan(
        exercises=[SeenExercise(name="Pogo Hops", frames=[1, 2]), SeenExercise(name="Box Jump", frames=[8, 9, 10, 11])],
        on_screen_text=[],
    )
    segs = segments(scan, 48.0)  # 16 frames, 3 s apart
    assert [s.name for s in segs] == ["Box Jump", "Pogo Hops"]
    assert segs[0].end_s - segs[0].start_s <= MAX_WINDOW_S
    assert (segs[1].start_s, segs[1].end_s) == (2.0, 10.0)  # 1.5-10.5 s padded, capped to 8 s


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
