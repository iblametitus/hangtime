"""User-facing pages: demo athlete, video upload, live progress, result card (HTMX partials)."""

import shutil
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import jobs
from app.demo import DEMO_PLAN, DEMO_PROFILE
from app.pipeline.run import STEPS

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
MAX_CAPTION_CHARS = 2000

RATINGS = {
    "well_supported": ("Well supported", "bg-emerald-100 text-emerald-800 ring-emerald-300"),
    "partly_supported": ("Partly supported", "bg-amber-100 text-amber-800 ring-amber-300"),
    "unsupported": ("Unsupported", "bg-slate-200 text-slate-700 ring-slate-300"),
    "myth": ("Myth", "bg-rose-100 text-rose-800 ring-rose-300"),
}
FITS = {
    "good_fit": ("Good fit for you", "bg-emerald-100 text-emerald-800 ring-emerald-300"),
    "conditional": ("Fits with conditions", "bg-amber-100 text-amber-800 ring-amber-300"),
    "not_recommended": ("Not for you right now", "bg-rose-100 text-rose-800 ring-rose-300"),
}
GOALS = {
    "vertical_jump": "Vertical jump",
    "sprint_speed": "Sprint speed",
    "injury_resilience": "Injury resilience",
    "general_athleticism": "General athleticism",
}

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {})


@router.get("/demo", response_class=HTMLResponse)
def demo(request: Request):
    ctx = {"profile": DEMO_PROFILE, "plan": DEMO_PLAN, "goal_label": GOALS[DEMO_PROFILE.goal.value]}
    return templates.TemplateResponse(request, "demo.html", ctx)


def _error(request: Request, message: str, status_code: int = 200):
    # 200, not 4xx: HTMX only swaps 2xx (and 422) responses with our config in base.html
    return templates.TemplateResponse(request, "_error.html", {"message": message}, status_code=status_code)


@router.post("/api/analyses", response_class=HTMLResponse)
def create_analysis(request: Request, video: UploadFile, caption: str = Form("")):
    suffix = Path(video.filename or "").suffix.lower()
    if suffix not in VIDEO_SUFFIXES:
        return _error(request, "Please upload a video file (mp4, mov or webm).")
    path = jobs.new_video_path(suffix)
    with path.open("wb") as out:
        shutil.copyfileobj(video.file, out, length=1024 * 1024)
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        path.unlink(missing_ok=True)
        return _error(request, "The video is larger than 100 MB. Please upload a shorter clip.")
    job = jobs.start(path, DEMO_PROFILE, caption.strip()[:MAX_CAPTION_CHARS] or None)
    return _status(request, job)


@router.get("/api/analyses/{job_id}", response_class=HTMLResponse)
def analysis_status(request: Request, job_id: str):
    job = jobs.get(job_id)
    if job is None:
        return _error(request, "This analysis has expired. Please upload the video again.")
    return _status(request, job)


@router.post("/api/analyses/{job_id}/segments/{segment}", response_class=HTMLResponse)
def analyse_other_exercise(request: Request, job_id: str, segment: int):
    """'Check this one': analyse another exercise of the same video, reusing its scan."""
    job = jobs.get(job_id)
    if job is None or job.result is None or not job.video.exists():
        return _error(request, "This analysis has expired. Please upload the video again.")
    if not 0 <= segment < len(job.result.segments):
        raise HTTPException(status_code=404)
    new = jobs.start(job.video, job.user, job.caption, segment, job.result.scan)
    return _status(request, new)


def _status(request: Request, job: jobs.Job):
    if job.status == "error":
        return _error(request, job.error or "Something went wrong.")
    if job.status != "done":
        return templates.TemplateResponse(request, "_progress.html", {"job": job, "steps": _progress(job)})
    return templates.TemplateResponse(request, "_result.html", _result_context(job))


def _progress(job: jobs.Job) -> list[tuple[str, str]]:
    """(label, state) per step; state is done | current | pending. The scan step only shows
    when the pipeline ran it (videos longer than the scan threshold)."""
    keys = [k for k in STEPS if k != "scan" or "scan" in job.steps]
    started = len(job.steps)
    out = []
    for key in keys:
        if key in job.steps:
            state = "current" if key == job.steps[-1] else "done"
        else:
            state = "pending"
        out.append((STEPS[key], state))
    if started == 0:
        out.insert(0, ("Uploading and reading the video", "current"))
    return out


def _result_context(job: jobs.Job) -> dict:
    r = job.result
    sources = {c.id: {"title": c.citation, "url": c.url, "curated": True, "type": c.study_type} for c in r.cards}
    sources |= {w.id: {"title": w.title, "url": w.url, "curated": False, "type": "web source"} for w in r.web}
    others = [(i, s.name) for i, s in enumerate(r.segments) if i != r.selected_segment and s.name]
    return {
        "job": job,
        "r": r,
        "v": r.verdict,
        "rating": RATINGS[r.verdict.rating.value],
        "fit": FITS[r.verdict.personal_fit.value],
        "sources": sources,
        "others": others,
    }
