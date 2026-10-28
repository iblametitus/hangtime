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

SCAN_PROMPT = (
    "You see 8 low-resolution frames spread evenly over a fitness video, in order. Return the indices "
    "of the frames where the exercise is actually being performed (not talking, intro or outro). "
    "Transcribe all on-screen text exactly, from every frame. Set multiple_exercises if more than one "
    "different exercise is shown."
)


def exercise_window(scan: CoarseScan, times: list[float], duration: float) -> tuple[float, float] | None:
    """Time window around the frames that show the exercise, padded by one frame spacing on each
    side. None if the scan found no exercise (caller falls back to the whole video)."""
    indices = sorted({i for i in scan.exercise_frames if 0 <= i < len(times)})
    if not indices:
        return None
    step = duration / len(times)
    start = max(0.0, times[indices[0]] - step)
    end = min(duration, times[indices[-1]] + step)
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
