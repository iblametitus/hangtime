"""Exercise database: one JSON file (data/exercises.json), list of ExerciseProfile.

Small enough to load whole on every read. Writes go through a temp file so a crash
never leaves a half-written database.
"""

import json
import os
import threading
from pathlib import Path

from pydantic import TypeAdapter

from app.config import get_settings
from app.models import ExerciseProfile

_adapter = TypeAdapter(list[ExerciseProfile])
_lock = threading.Lock()


def _path(path: Path | None) -> Path:
    return path or Path(get_settings().exercises_path)


def load_exercises(path: Path | None = None) -> list[ExerciseProfile]:
    p = _path(path)
    if not p.exists():
        return []
    return _adapter.validate_json(p.read_bytes())


def save_exercises(exercises: list[ExerciseProfile], path: Path | None = None) -> None:
    p = _path(path)
    ids = [e.id for e in exercises]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate exercise ids")
    data = [e.model_dump(mode="json") for e in sorted(exercises, key=lambda e: e.id)]
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with _lock:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, p)


def get_exercise(exercise_id: str, path: Path | None = None) -> ExerciseProfile | None:
    return next((e for e in load_exercises(path) if e.id == exercise_id), None)


def upsert_exercise(exercise: ExerciseProfile, path: Path | None = None) -> None:
    exercises = [e for e in load_exercises(path) if e.id != exercise.id]
    exercises.append(exercise)
    save_exercises(exercises, path)
