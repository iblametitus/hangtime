"""Run the video-understanding part of the pipeline on one file (milestone M3).

    uv run python -m app.pipeline.run_cli video.mp4 [--caption "..."]

Prints VideoUnderstanding, Claim and ExerciseProfile as JSON, plus timings per step.
"""

import argparse
import json
import time
from pathlib import Path

from app.exercises import load_exercises
from app.models import Claim, CoarseScan, ExerciseProfile, VideoUnderstanding
from app.pipeline.exercise import identify
from app.pipeline.scan import SCAN_THRESHOLD_S, coarse_scan
from app.pipeline.understand import understand
from app.pipeline.video import extract_frames, frame_times, probe_duration


def understand_video(path: Path, caption: str | None = None) -> dict:
    timings: dict[str, float] = {}
    t0 = time.monotonic()

    duration = probe_duration(path)
    scan: CoarseScan | None = None
    window = None
    if duration > SCAN_THRESHOLD_S:
        scan, window = coarse_scan(path, duration)
        timings["scan"] = time.monotonic() - t0
    start, end = window or (0.0, duration)

    t1 = time.monotonic()
    frames = extract_frames(path, frame_times(start, end))
    timings["frames"] = time.monotonic() - t1

    t2 = time.monotonic()
    understanding: VideoUnderstanding = understand(frames, scan.on_screen_text if scan else None)
    timings["understand"] = time.monotonic() - t2

    t3 = time.monotonic()
    claim: Claim
    profile: ExerciseProfile
    claim, profile = identify(understanding, caption, load_exercises())
    timings["exercise"] = time.monotonic() - t3
    timings["total"] = time.monotonic() - t0

    return {
        "duration_s": round(duration, 1),
        "window_s": [round(start, 1), round(end, 1)],
        "coarse_scan": scan.model_dump() if scan else None,
        "understanding": understanding.model_dump(),
        "claim": claim.model_dump(),
        "profile": profile.model_dump(mode="json"),
        "timings_s": {k: round(v, 1) for k, v in timings.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--caption", default=None)
    args = parser.parse_args()
    print(json.dumps(understand_video(args.video, args.caption), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
