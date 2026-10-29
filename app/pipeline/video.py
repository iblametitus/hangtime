"""Frame extraction with ffmpeg.

Token Factory takes images, not video, and MODEL_VISION accepts at most 8 images per call
(M0 test). So every vision step works on 8 evenly spaced JPEG frames, either across the whole
video or inside a time window found by the coarse scan.
"""

import base64
import subprocess
from pathlib import Path

FRAME_COUNT = 8
FULL_RES = 768  # max edge for the understanding step
SCAN_RES = 384  # max edge for the coarse scan


class VideoError(RuntimeError):
    """The file is not a readable video (shown to the user as a clean error)."""


def probe_duration(path: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout.strip()
        duration = float(out)
    except (subprocess.CalledProcessError, ValueError) as exc:
        raise VideoError(f"Could not read video: {path.name}") from exc
    if duration <= 0:
        raise VideoError(f"Video has no duration: {path.name}")
    return duration


def frame_times(start: float, end: float, count: int = FRAME_COUNT) -> list[float]:
    """Timestamps at the centre of `count` equal slices of [start, end]. Never hits the exact end,
    where ffmpeg often returns no frame."""
    step = (end - start) / count
    return [round(start + (i + 0.5) * step, 3) for i in range(count)]


# Cheaper decoding for the coarse scan: no deblocking, skip non-reference frames (the next
# reference frame is shown instead). ~2x faster; fine for 384 px "which exercise is this" frames.
FAST_DECODE = ["-skip_loop_filter:v", "all", "-skip_frame:v", "noref"]


def _scale(max_edge: int) -> str:
    return f"scale='if(gt(iw,ih),min({max_edge},iw),-2)':'if(gt(iw,ih),-2,min({max_edge},ih))'"


def extract_frame(path: Path, t: float, max_edge: int, fast: bool = False) -> bytes:
    result = subprocess.run(
        ["ffmpeg", "-v", "error", *(FAST_DECODE if fast else []), "-ss", f"{t:.3f}", "-i", str(path),
         "-frames:v", "1", "-vf", _scale(max_edge), "-q:v", "4", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
        capture_output=True, check=False, timeout=60,
    )
    if result.returncode != 0 or not result.stdout:
        raise VideoError(f"Could not extract frame at {t:.1f}s from {path.name}")
    return result.stdout


def extract_frames(path: Path, times: list[float], max_edge: int = FULL_RES, fast: bool = False) -> list[bytes]:
    return [extract_frame(path, t, max_edge, fast) for t in times]


def extract_window(path: Path, start: float, end: float, count: int = FRAME_COUNT,
                   max_edge: int = FULL_RES) -> list[bytes]:
    """The `count` frames of frame_times(start, end) in ONE decode pass instead of one seek per
    frame (each seek decodes again from the previous keyframe, 3-8 s back in TikTok videos).
    ~3.5x faster on Render's small CPU. Falls back to single seeks if a frame is missing."""
    fps = count / (end - start)
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start + 0.5 / fps:.3f}", "-t", f"{end - start:.3f}", "-i", str(path),
         "-vf", f"fps={fps:.5f}:round=up,{_scale(max_edge)}", "-frames:v", str(count), "-q:v", "4",
         "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
        capture_output=True, check=False, timeout=60,
    )
    frames = [f + b"\xff\xd9" for f in result.stdout.split(b"\xff\xd9") if f.startswith(b"\xff\xd8")]
    if result.returncode != 0 or len(frames) != count:
        return extract_frames(path, frame_times(start, end, count), max_edge)
    return frames


def to_data_uri(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
