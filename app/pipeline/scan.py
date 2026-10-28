"""Coarse scan for videos longer than 20 s: which exercises does the video show, and where?

Intros, talking and outros eat most of a typical social media clip, and many clips show several
exercises ("3 drills for +10 cm"). One cheap low-res pass over the whole video lists every
exercise with the frames it appears on, so each one gets its own time window for the 8 full-res
frames. The scan also transcribes all on-screen text, because the claim is often in the intro.

MODEL_VISION takes max. 8 images per call, so the 16 scan frames go out as two batches. The
second batch gets the names from the first, so the same exercise keeps the same name.
"""

from pathlib import Path

from app.config import get_settings
from app.llm import call_json_schema, image_content
from app.models import CoarseScan, ScanPart, Segment, SeenExercise
from app.pipeline.video import FRAME_COUNT, SCAN_RES, extract_frames, frame_times, to_data_uri

SCAN_THRESHOLD_S = 20.0
SCAN_FRAMES = 2 * FRAME_COUNT
MAX_WINDOW_S = 8.0

SCAN_PROMPT = (
    "You see 8 low-resolution frames from part {part} of 2 of a fitness video, in order, indices 0-7. "
    "List every different exercise that is actually being performed (not talking, intro, outro or a "
    "static pose), each with the indices of the frames that show it. Only training exercises: ignore "
    "dunks, game play, shooting and other sport action shown as a result. Use short common exercise names. "
    "Transcribe all on-screen text exactly, from every frame."
)
KNOWN_NAMES = " Exercises already seen in part 1: {names}. If you see one of them again, use exactly that name."


# Sport action shown as the result ("look how high I dunk"), not a training exercise. The prompt
# says to skip it, but the model still lists dunks now and then (test 28.10.).
NOT_EXERCISES = ("dunk", "basketball", "game play", "gameplay", "shooting")


def _key(name: str) -> str:
    return " ".join(name.lower().split())


def is_exercise(name: str) -> bool:
    return not any(word in _key(name) for word in NOT_EXERCISES)


def merge_parts(parts: list[ScanPart], batch_size: int = FRAME_COUNT) -> CoarseScan:
    """Merge per-batch answers into global frame indices; same name (case-insensitive) = same exercise."""
    merged: dict[str, SeenExercise] = {}
    text: list[str] = []
    for offset, part in enumerate(parts):
        for ex in part.exercises:
            if not is_exercise(ex.name):
                continue
            frames = [offset * batch_size + i for i in ex.frames if 0 <= i < batch_size]
            if not frames:
                continue
            seen = merged.setdefault(_key(ex.name), SeenExercise(name=ex.name.strip(), frames=[]))
            seen.frames = sorted(set(seen.frames) | set(frames))
        text.extend(part.on_screen_text)
    return CoarseScan(exercises=list(merged.values()), on_screen_text=text)


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


def exercise_window(frames: list[int], times: list[float], duration: float) -> tuple[float, float] | None:
    """Time window for the 8 full-res frames of one exercise, or None without valid frames.

    Takes the longest consecutive block of its scan frames, padded by one frame spacing on each
    side, and caps it at MAX_WINDOW_S around its centre: 8 frames over 40 s miss every jump
    (test 28.10.: a squat jump was read as a lateral lunge), 8 frames over 8 s show the reps.
    """
    run = longest_run(sorted({i for i in frames if 0 <= i < len(times)}))
    if not run:
        return None
    step = duration / len(times)
    start = max(0.0, times[run[0]] - step)
    end = min(duration, times[run[-1]] + step)
    if end - start > MAX_WINDOW_S:
        centre = (start + end) / 2
        start, end = centre - MAX_WINDOW_S / 2, centre + MAX_WINDOW_S / 2
    return start, end


def segments(scan: CoarseScan, duration: float) -> list[Segment]:
    """One segment per exercise, main exercise (most scan frames, later wins a tie) first."""
    times = frame_times(0.0, duration, SCAN_FRAMES)
    out = []
    for ex in scan.exercises:
        window = exercise_window(ex.frames, times, duration)
        if window:
            out.append(Segment(name=ex.name, start_s=round(window[0], 2), end_s=round(window[1], 2),
                               frame_count=len(ex.frames)))
    return sorted(out, key=lambda s: (s.frame_count, s.start_s), reverse=True)


def coarse_scan(path: Path, duration: float) -> CoarseScan:
    times = frame_times(0.0, duration, SCAN_FRAMES)
    frames = extract_frames(path, times, max_edge=SCAN_RES)
    parts: list[ScanPart] = []
    for part in range(2):
        batch = frames[part * FRAME_COUNT : (part + 1) * FRAME_COUNT]
        prompt = SCAN_PROMPT.format(part=part + 1)
        if parts and parts[0].exercises:
            prompt += KNOWN_NAMES.format(names=", ".join(e.name for e in parts[0].exercises))
        content = [{"type": "text", "text": "Frames in order:"}] + [image_content(to_data_uri(f)) for f in batch]
        parts.append(
            call_json_schema(
                model=get_settings().model_vision,
                system_prompt=prompt,
                user_content=content,
                schema_model=ScanPart,
                thinking=False,
            )
        )
    return merge_parts(parts)
