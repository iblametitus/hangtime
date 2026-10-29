"""Running analyses for the web app: one background thread per upload, progress kept in memory.

In memory on purpose: the Render free instance has one process and an ephemeral disk, so SQLite
would not survive a restart either. The uploaded video stays on disk while its job is kept, so
"Check this one" can analyse another exercise of the same video without a new upload.
"""

import logging
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.models import CoarseScan, TrainingPlan, UserProfile
from app.pipeline import run
from app.pipeline.video import VideoError, probe_duration

logger = logging.getLogger(__name__)

MAX_DURATION_S = 180  # the coarse scan takes 16 frames regardless of length
MAX_JOBS = 20  # oldest jobs (and their videos) are dropped beyond this
_RUNNING = threading.Semaphore(2)  # Render free has 512 MB RAM; ffmpeg + images per run


@dataclass
class Job:
    id: str
    video: Path
    user: UserProfile
    plan: TrainingPlan
    caption: str | None
    segment: int = 0
    scan: CoarseScan | None = None
    status: str = "queued"  # queued | running | done | error
    steps: list[str] = field(default_factory=list)  # step keys in the order they started
    result: run.AnalysisResult | None = None
    error: str | None = None
    session_id: str = ""  # browser session that owns the plan
    applied: bool = False


_jobs: dict[str, Job] = {}
_lock = threading.Lock()
_dir = Path(tempfile.gettempdir()) / "hangtime-uploads"


def new_video_path(suffix: str) -> Path:
    _dir.mkdir(parents=True, exist_ok=True)
    return _dir / f"{uuid.uuid4().hex}{suffix}"


def get(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def start(video: Path, user: UserProfile, plan: TrainingPlan, caption: str | None = None,
          segment: int = 0, scan: CoarseScan | None = None, session_id: str = "") -> Job:
    job = Job(id=uuid.uuid4().hex[:12], video=video, user=user, plan=plan, caption=caption, segment=segment,
              scan=scan, session_id=session_id)
    with _lock:
        _jobs[job.id] = job
        _prune()
    threading.Thread(target=_work, args=(job,), daemon=True).start()
    return job


def _prune() -> None:
    """Drop the oldest jobs; delete a video once no kept job points at it."""
    while len(_jobs) > MAX_JOBS:
        old = _jobs.pop(next(iter(_jobs)))
        if all(j.video != old.video for j in _jobs.values()):
            old.video.unlink(missing_ok=True)


def _work(job: Job) -> None:
    def on_step(key: str, _label: str) -> None:
        job.steps.append(key)

    with _RUNNING:
        job.status = "running"
        try:
            if probe_duration(job.video) > MAX_DURATION_S:
                raise VideoError(f"Video is longer than {MAX_DURATION_S // 60} minutes. Please trim it.")
            job.result = run.analyse(job.video, job.user, job.plan, job.caption, job.segment, job.scan,
                                     on_step=on_step)
            job.status = "done"
        except VideoError as exc:
            job.error, job.status = str(exc), "error"
        except Exception:
            logger.exception("Analysis %s failed", job.id)
            job.error, job.status = "Something went wrong while analysing the video. Please try again.", "error"


def clear() -> None:
    """Tests only."""
    with _lock:
        _jobs.clear()
    shutil.rmtree(_dir, ignore_errors=True)
