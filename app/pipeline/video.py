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


def extract_frame(path: Path, t: float, max_edge: int) -> bytes:
    scale = f"scale='if(gt(iw,ih),min({max_edge},iw),-2)':'if(gt(iw,ih),-2,min({max_edge},ih))'"
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
         "-vf", scale, "-q:v", "4", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
        capture_output=True, check=False, timeout=60,
    )
    if result.returncode != 0 or not result.stdout:
        raise VideoError(f"Could not extract frame at {t:.1f}s from {path.name}")
    return result.stdout


def extract_frames(path: Path, times: list[float], max_edge: int = FULL_RES) -> list[bytes]:
    return [extract_frame(path, t, max_edge) for t in times]


def to_data_uri(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
