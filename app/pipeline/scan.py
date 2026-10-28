"""Coarse scan for videos longer than 20 s: where in the video is the exercise performed?

Intros, talking and outros eat most of a typical social media clip. One cheap low-res pass over
the whole video finds the exercise window, so the 8 full-res frames are not wasted on talking.
The scan also transcribes all on-screen text, because the claim is often in the intro.
"""

from pathlib import Path

from app.config import get_settings
from app.llm import call_json_schema, image_content
from app.models import CoarseScan
from app.pipeline.video import FRAME_COUNT, SCAN_RES, extract_frames, frame_times, to_data_uri

SCAN_THRESHOLD_S = 20.0
MAX_WINDOW_S = 8.0

SCAN_PROMPT = (
    "You see 8 low-resolution frames spread evenly over a fitness video, in order. Return the indices "
    "of the frames where the exercise is actually being performed (not talking, intro or outro). "
    "Transcribe all on-screen text exactly, from every frame. Set multiple_exercises if more than one "
    "different exercise is shown."
)


def longest_run(indices: list[int]) -> list[int]:
    """Longest block of consecutive frame indices; the later block wins a tie (demos often show the
    real reps after the explanation)."""
    runs: list[list[int]] = []
    for i in indices:
        if runs and i == runs[-1][-1] + 1:
            runs[-1].append(i)
        else:
            runs.append([i])
    return max(reversed(runs), key=len) if runs else []


def exercise_window(scan: CoarseScan, times: list[float], duration: float) -> tuple[float, float] | None:
    """Time window for the 8 full-res frames, or None if the scan found no exercise (caller falls
    back to the whole video).

    Takes the longest consecutive block of exercise frames, padded by one frame spacing on each
    side, and caps it at MAX_WINDOW_S around its centre: 8 frames over 40 s miss every jump
    (test 28.10.: a squat jump was read as a lateral lunge), 8 frames over 8 s show the reps.
    """
    run = longest_run(sorted({i for i in scan.exercise_frames if 0 <= i < len(times)}))
    if not run:
        return None
    step = duration / len(times)
    start = max(0.0, times[run[0]] - step)
    end = min(duration, times[run[-1]] + step)
    if end - start > MAX_WINDOW_S:
        centre = (start + end) / 2
        start, end = centre - MAX_WINDOW_S / 2, centre + MAX_WINDOW_S / 2
    return start, end


def coarse_scan(path: Path, duration: float) -> tuple[CoarseScan, tuple[float, float] | None]:
    times = frame_times(0.0, duration, FRAME_COUNT)
    frames = extract_frames(path, times, max_edge=SCAN_RES)
    content = [{"type": "text", "text": "Frames in order:"}] + [image_content(to_data_uri(f)) for f in frames]
    scan = call_json_schema(
        model=get_settings().model_vision,
        system_prompt=SCAN_PROMPT,
        user_content=content,
        schema_model=CoarseScan,
    )
    return scan, exercise_window(scan, times, duration)
