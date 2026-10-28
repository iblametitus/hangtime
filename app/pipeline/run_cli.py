"""Run the video-understanding part of the pipeline on one file (milestone M3).

    uv run python -m app.pipeline.run_cli video.mp4 [--caption "..."] [--segment 1]

Prints the exercises found in the video (segments), and for the chosen one (default: the main
exercise) VideoUnderstanding, Claim and ExerciseProfile as JSON, plus timings per step.
"""

import argparse
import json
import time
from pathlib import Path

from app.exercises import load_exercises
from app.models import CoarseScan, Segment
from app.pipeline.exercise import identify
from app.pipeline.scan import SCAN_THRESHOLD_S, coarse_scan, segments
from app.pipeline.understand import understand
from app.pipeline.video import extract_frames, frame_times, probe_duration


def understand_video(
    path: Path, caption: str | None = None, segment: int = 0, scan: CoarseScan | None = None
) -> dict:
    """Analyse one exercise of the video. `segment` picks it from the segment list (0 = main
    exercise). Pass the `scan` of an earlier run to check another exercise without scanning again."""
    timings: dict[str, float] = {}
    t0 = time.monotonic()

    duration = probe_duration(path)
    if scan is None and duration > SCAN_THRESHOLD_S:
        scan = coarse_scan(path, duration)
        timings["scan"] = time.monotonic() - t0
    segs: list[Segment] = segments(scan, duration) if scan else []
    if not segs:  # short video, or the scan found no exercise: whole video, one segment
        segs = [Segment(name="", start_s=0.0, end_s=round(duration, 2), frame_count=0)]
    chosen = segs[min(segment, len(segs) - 1)]

    t1 = time.monotonic()
    frames = extract_frames(path, frame_times(chosen.start_s, chosen.end_s))
    timings["frames"] = time.monotonic() - t1

    t2 = time.monotonic()
    understanding = understand(frames, scan.on_screen_text if scan else None)
    timings["understand"] = time.monotonic() - t2

    t3 = time.monotonic()
    claim, profile = identify(understanding, caption, load_exercises())
    timings["exercise"] = time.monotonic() - t3
    timings["total"] = time.monotonic() - t0

    return {
        "duration_s": round(duration, 1),
        "segments": [s.model_dump() for s in segs],
        "selected_segment": segs.index(chosen),
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
    parser.add_argument("--segment", type=int, default=0, help="0 = main exercise, 1 = next, ...")
    args = parser.parse_args()
    print(json.dumps(understand_video(args.video, args.caption, args.segment), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
