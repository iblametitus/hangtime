"""User-facing pages: demo athlete, video upload, live progress, result card (HTMX partials)."""

import shutil
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import jobs, plans
from app.config import get_settings
from app.evidence_cards import load_cards
from app.exercises import load_exercises
from app.demo import DEMO_PROFILE
from app.pipeline.run import STEPS
from app.pipeline.swap import apply_swap

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
MAX_CAPTION_CHARS = 2000

RATINGS = {
    "well_supported": ("Well supported", "border-emerald-400/70 bg-emerald-400/10 text-emerald-300"),
    "partly_supported": ("Partly supported", "border-amber-300/70 bg-amber-300/10 text-amber-200"),
    "unsupported": ("Unsupported", "border-cream/40 bg-cream/5 text-cream/80"),
    "myth": ("Myth", "border-rose-400/70 bg-rose-400/10 text-rose-300"),
}
FITS = {
    "good_fit": ("Good fit for you", "border-emerald-400/70 bg-emerald-400/10 text-emerald-300"),
    "conditional": ("Fits with conditions", "border-amber-300/70 bg-amber-300/10 text-amber-200"),
    "not_recommended": ("Not for you right now", "border-rose-400/70 bg-rose-400/10 text-rose-300"),
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


def _session_id(request: Request) -> str:
    return request.cookies.get(plans.COOKIE) or plans.new_session_id()


def _with_cookie(response, session_id: str):
    response.set_cookie(plans.COOKIE, session_id, max_age=7 * 24 * 3600, httponly=True, samesite="lax")
    return response


@router.get("/about", response_class=HTMLResponse)
def about(request: Request):
    """Launch-style explainer for the judges. Counts come from the data, so they stay true."""
    cards, exercises, settings = load_cards(), load_exercises(), get_settings()
    ctx = {
        "nav": "about",
        "n_cards": len(cards),
        "n_meta": sum("meta" in c.study_type or "review" in c.study_type for c in cards),
        "n_exercises": len(exercises),
        "n_reviewed": sum(c.reviewed for c in cards) + sum(e.reviewed for e in exercises),
        "model_vision": settings.model_vision.split("/")[-1],
        "model_fast": settings.model_fast.split("/")[-1],
        "model_reason": settings.model_reason.split("/")[-1],
    }
    return templates.TemplateResponse(request, "about.html", ctx)


@router.get("/demo", response_class=HTMLResponse)
def demo(request: Request, reset: bool = False):
    session_id = _session_id(request)
    if reset:
        plans.reset(session_id)
    plan = plans.get_plan(session_id)
    ctx = {"profile": DEMO_PROFILE, "plan": plan, "goal_label": GOALS[DEMO_PROFILE.goal.value], "nav": "demo",
           "changed": plan != plans.get_plan("")}
    return _with_cookie(templates.TemplateResponse(request, "demo.html", ctx), session_id)


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
    session_id = _session_id(request)
    job = jobs.start(path, DEMO_PROFILE, plans.get_plan(session_id), caption.strip()[:MAX_CAPTION_CHARS] or None,
                     session_id=session_id)
    return _with_cookie(_status(request, job), session_id)


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
    new = jobs.start(job.video, job.user, plans.get_plan(job.session_id), job.caption, segment, job.result.scan,
                     session_id=job.session_id)
    return _status(request, new)


@router.post("/api/analyses/{job_id}/apply-swap", response_class=HTMLResponse)
def apply_analysis_swap(request: Request, job_id: str):
    """Write the proposed swap into this browser session's plan."""
    job = jobs.get(job_id)
    if job is None or job.result is None or job.result.swap.proposal is None:
        return _error(request, "This analysis has expired. Please upload the video again.")
    if not job.applied:
        current = plans.get_plan(job.session_id)
        updated = apply_swap(current, job.result.swap.proposal, job.result.profile.name)
        if updated == current:
            return _error(request, "Your plan changed since this analysis, so the swap no longer fits. "
                                   "Run the analysis again.")
        plans.set_plan(job.session_id, updated)
        job.applied = True
    return templates.TemplateResponse(request, "_swap.html", _result_context(job))


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
        "diff": _plan_diff(job),
        "job": job,
        "r": r,
        "v": r.verdict,
        "rating": RATINGS[r.verdict.rating.value],
        "fit": FITS[r.verdict.personal_fit.value],
        "sources": sources,
        "others": others,
    }


def _plan_diff(job: jobs.Job) -> list[dict]:
    """Rows of the next session with the swap marked: state is same | out | in."""
    swap, new = job.result.swap, job.result.profile
    if swap.proposal is None or swap.session is None:
        return []
    p = swap.proposal
    rows = []
    for e in swap.session.exercises:
        prescription = f"{e.sets}×{e.reps}" + (f" · {e.load}" if e.load else "")
        if e.exercise_id == p.replaces_exercise_id:
            rows.append({"name": e.raw_name, "prescription": prescription, "state": "out"})
            rows.append({"name": new.name, "prescription": p.new_prescription, "state": "in"})
        else:
            rows.append({"name": e.raw_name, "prescription": prescription, "state": "same"})
    return rows
