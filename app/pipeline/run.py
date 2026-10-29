"""Full analysis of one video: scan -> frames -> understand -> exercise -> evidence -> verdict -> citations.

`on_step` is called before each step with a short English label, so the web app can show
progress (and the demo video can show the pipeline at work).
"""

import logging
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from app.evidence_cards import load_cards
from app.exercises import load_exercises
from app.models import (
    Claim,
    CoarseScan,
    EvidenceCard,
    ExerciseProfile,
    ExternalSource,
    Segment,
    UserProfile,
    Verdict,
    VideoUnderstanding,
)
from app.pipeline.citations import check_citations
from app.pipeline.evidence import find_evidence
from app.pipeline.exercise import identify
from app.pipeline.scan import SCAN_THRESHOLD_S, coarse_scan, segments
from app.pipeline.understand import understand
from app.pipeline.verdict import judge
from app.pipeline.video import extract_window, probe_duration

logger = logging.getLogger(__name__)

STEPS = {
    "scan": "Finding the exercises in the video",
    "frames": "Extracting frames",
    "understand": "Watching the movement",
    "exercise": "Identifying the exercise",
    "evidence": "Searching the research",
    "verdict": "Weighing the evidence",
    "citations": "Checking every citation",
}


class AnalysisResult(BaseModel):
    duration_s: float
    segments: list[Segment]
    selected_segment: int
    scan: CoarseScan | None
    understanding: VideoUnderstanding
    claim: Claim
    profile: ExerciseProfile
    cards: list[EvidenceCard]
    web: list[ExternalSource]
    verdict: Verdict
    removed_citations: int
    timings_s: dict[str, float]


def analyse(
    path: Path,
    user: UserProfile,
    caption: str | None = None,
    segment: int = 0,
    scan: CoarseScan | None = None,
    on_step: Callable[[str, str], None] | None = None,
) -> AnalysisResult:
    """Analyse one exercise of the video (`segment` 0 = main exercise). Pass the `scan` of an
    earlier run to check another exercise of the same video without scanning again."""
    timings: dict[str, float] = {}
    t_start = time.monotonic()
    t = t_start

    def step(key: str) -> None:
        nonlocal t
        t = time.monotonic()
        if on_step:
            on_step(key, STEPS[key])

    def done(key: str) -> None:
        timings[key] = round(time.monotonic() - t, 1)

    duration = probe_duration(path)
    if scan is None and duration > SCAN_THRESHOLD_S:
        step("scan")
        scan = coarse_scan(path, duration)
        done("scan")
    segs = segments(scan, duration) if scan else []
    if not segs:  # short video, or the scan found no exercise: whole video, one segment
        segs = [Segment(name="", start_s=0.0, end_s=round(duration, 2), frame_count=0)]
    chosen = segs[min(segment, len(segs) - 1)]

    step("frames")
    frames = extract_window(path, chosen.start_s, chosen.end_s)
    done("frames")

    step("understand")
    understanding = understand(frames, scan.on_screen_text if scan else None)
    done("understand")

    step("exercise")
    claim, profile = identify(understanding, caption, load_exercises())
    done("exercise")

    step("evidence")
    cards, web = find_evidence(claim, profile, load_cards())
    done("evidence")

    step("verdict")
    others = [s.name for s in segs if s is not chosen and s.name]
    verdict = judge(understanding, caption, claim, profile, cards, web, user, swap=None, other_exercises=others)
    done("verdict")

    step("citations")
    verdict, removed = check_citations(verdict, cards, web)
    done("citations")
    if removed:
        logger.info("Citation check removed %d of %d citations", removed, removed + len(verdict.citations))

    timings["total"] = round(time.monotonic() - t_start, 1)
    return AnalysisResult(
        duration_s=round(duration, 1),
        segments=segs,
        selected_segment=segs.index(chosen),
        scan=scan,
        understanding=understanding,
        claim=claim,
        profile=profile,
        cards=cards,
        web=web,
        verdict=verdict,
        removed_citations=removed,
        timings_s=timings,
    )
