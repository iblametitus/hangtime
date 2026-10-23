"""Review pages for drafted data (/admin). Only mounted when ENABLE_ADMIN=true.

Titus checks LLM-drafted exercise profiles here and ticks "reviewed".
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.config import get_settings
from app.exercises import get_exercise, load_exercises, upsert_exercise
from app.models import (
    CONTRAINDICATIONS,
    EQUIPMENT,
    SSC,
    Emphasis,
    ExerciseProfile,
    FVZone,
    HardestPoint,
    Laterality,
    Pattern,
    Resistance,
)

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

ENUM_FIELDS = {
    "pattern": Pattern,
    "fv_zone": FVZone,
    "ssc": SSC,
    "emphasis": Emphasis,
    "resistance": Resistance,
    "hardest_point": HardestPoint,
    "laterality": Laterality,
}


def require_admin() -> None:
    if not get_settings().enable_admin:
        raise HTTPException(status_code=404)


router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def _context(**extra) -> dict:
    return {
        "enum_fields": {k: [m.value for m in v] for k, v in ENUM_FIELDS.items()},
        "equipment_options": EQUIPMENT,
        "contraindication_options": CONTRAINDICATIONS,
        **extra,
    }


def _filter(exercises: list[ExerciseProfile], q: str, pattern: str, status: str):
    q = q.strip().lower()
    out = []
    for e in exercises:
        if q and q not in " ".join([e.id, e.name, *e.aliases]).lower():
            continue
        if pattern and e.pattern.value != pattern:
            continue
        if status == "reviewed" and not e.reviewed:
            continue
        if status == "open" and e.reviewed:
            continue
        out.append(e)
    return sorted(out, key=lambda e: (e.pattern.value, e.name))


def _get_or_404(exercise_id: str) -> ExerciseProfile:
    exercise = get_exercise(exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Unknown exercise")
    return exercise


def _split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


@router.get("/exercises", response_class=HTMLResponse)
def exercises_page(request: Request, q: str = "", pattern: str = "", status: str = ""):
    all_exercises = load_exercises()
    rows = _filter(all_exercises, q, pattern, status)
    ctx = _context(
        exercises=rows,
        total=len(all_exercises),
        reviewed=sum(e.reviewed for e in all_exercises),
        q=q,
        pattern=pattern,
        status=status,
    )
    name = "admin/_rows.html" if request.headers.get("HX-Request") else "admin/exercises.html"
    return templates.TemplateResponse(request, name, ctx)


@router.get("/exercises/{exercise_id}/row", response_class=HTMLResponse)
def exercise_row(request: Request, exercise_id: str):
    return templates.TemplateResponse(request, "admin/_row.html", _context(e=_get_or_404(exercise_id)))


@router.get("/exercises/{exercise_id}/edit", response_class=HTMLResponse)
def exercise_edit(request: Request, exercise_id: str):
    return templates.TemplateResponse(
        request, "admin/_edit.html", _context(e=_get_or_404(exercise_id), error=None)
    )


@router.post("/exercises/{exercise_id}", response_class=HTMLResponse)
async def exercise_save(request: Request, exercise_id: str):
    current = _get_or_404(exercise_id)
    form = await request.form()
    data = {
        "id": exercise_id,
        "name": form.get("name", "").strip(),
        "aliases": _split(form.get("aliases", "")),
        **{field: form.get(field) for field in ENUM_FIELDS},
        "load_cost": {
            "fatigue": form.get("fatigue"),
            "joint_stress": form.get("joint_stress"),
            "ground_contacts_per_rep": form.get("ground_contacts_per_rep"),
        },
        "equipment": form.getlist("equipment") or ["none"],
        "min_training_age_years": form.get("min_training_age_years"),
        "rep_min": form.get("rep_min"),
        "rep_max": form.get("rep_max"),
        "contraindications": form.getlist("contraindications"),
        "evidence_card_ids": _split(form.get("evidence_card_ids", "")),
        "reviewed": form.get("reviewed") == "on",
        "auto_profiled": current.auto_profiled,
    }
    try:
        exercise = ExerciseProfile.model_validate(data)
    except ValidationError as exc:
        error = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in exc.errors())
        return templates.TemplateResponse(
            request, "admin/_edit.html", _context(e=current, error=error), status_code=422
        )
    upsert_exercise(exercise)
    return templates.TemplateResponse(request, "admin/_row.html", _context(e=exercise))


@router.post("/exercises/{exercise_id}/reviewed", response_class=HTMLResponse)
def exercise_toggle_reviewed(request: Request, exercise_id: str):
    exercise = _get_or_404(exercise_id).model_copy()
    exercise.reviewed = not exercise.reviewed
    upsert_exercise(exercise)
    return templates.TemplateResponse(request, "admin/_row.html", _context(e=exercise))
