"""Run the full pipeline on one video file for the demo athlete.

    uv run python -m app.pipeline.run_cli video.mp4 [--caption "..."] [--segment 1] [--json]

Default output is a short readable summary; --json prints the whole AnalysisResult.
"""

import argparse
import sys
from pathlib import Path

from app.demo import DEMO_PLAN, DEMO_PROFILE
from app.pipeline.run import analyse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--caption", default=None)
    parser.add_argument("--segment", type=int, default=0, help="0 = main exercise, 1 = next, ...")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args()

    result = analyse(
        args.video, DEMO_PROFILE, DEMO_PLAN, args.caption, args.segment,
        on_step=lambda key, label: print(f"... {label}", file=sys.stderr),
    )
    if args.json:
        print(result.model_dump_json(indent=2))
        return

    v = result.verdict
    print(f"Exercises in video: {[s.name for s in result.segments]} (analysed #{result.selected_segment})")
    print(f"Exercise: {result.profile.name} ({result.profile.id}{', auto-profiled' if result.profile.auto_profiled else ''})")
    print(f"Promise:  {v.promise!r}")
    print(f"Exercise: {v.exercise_take}")
    print(f"Rating:   {v.rating.value} - {v.headline}")
    print(f"Why:      {v.reasoning}")
    print(f"Fit:      {v.personal_fit.value} - {v.personal_fit_reason}")
    s = result.swap
    if s.proposal:
        p = s.proposal
        print(f"Swap:     {p.replaces_raw_name} {p.old_prescription} -> {result.profile.name} {p.new_prescription}"
              f" in {s.session.label} (similarity {p.similarity}) - {p.volume_note}")
    else:
        print(f"Swap:     none - {s.note}")
    for c in v.citations:
        print(f"  [{c.source_id}] \"{c.quote}\"")
    print(f"Evidence: {len(result.cards)} cards, {len(result.web)} web sources, {result.removed_citations} citations removed")
    print(f"Timings:  {result.timings_s}")


if __name__ == "__main__":
    main()
