import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import get_settings
from app.exercises import load_exercises, save_exercises
from app.main import app
from app.models import CONTRAINDICATIONS, EQUIPMENT, ExerciseProfile

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "exercises.json"


def make_exercise(**overrides) -> ExerciseProfile:
    data = {
        "id": "box-jump",
        "name": "Box Jump",
        "aliases": ["box jumps"],
        "pattern": "jump_vertical",
        "laterality": "bilateral",
        "fv_zone": "speed_strength",
        "ssc": "slow",
        "emphasis": "concentric",
        "resistance": "bodyweight",
        "hardest_point": "bottom",
        "load_cost": {"fatigue": 2, "joint_stress": 1, "ground_contacts_per_rep": 1},
        "equipment": ["box"],
        "min_training_age_years": 0,
        "rep_min": 3,
        "rep_max": 5,
        "contraindications": [],
        "evidence_card_ids": [],
    }
    return ExerciseProfile.model_validate(data | overrides)


# --- schema ---------------------------------------------------------------


def test_new_profile_defaults_to_unreviewed():
    assert make_exercise().reviewed is False


def test_rep_range_must_be_ordered():
    with pytest.raises(ValidationError):
        make_exercise(rep_min=8, rep_max=3)


def test_load_cost_bounds():
    with pytest.raises(ValidationError):
        make_exercise(load_cost={"fatigue": 4, "joint_stress": 1, "ground_contacts_per_rep": 0})


# --- data/exercises.json ----------------------------------------------------


@pytest.mark.skipif(not DATA_FILE.exists(), reason="data/exercises.json not seeded yet")
def test_exercise_database_is_valid():
    exercises = load_exercises(DATA_FILE)
    assert 60 <= len(exercises) <= 80
    ids = [e.id for e in exercises]
    assert len(ids) == len(set(ids))
    for e in exercises:
        assert set(e.equipment) <= set(EQUIPMENT), e.id
        assert set(e.contraindications) <= set(CONTRAINDICATIONS), e.id


def test_save_rejects_duplicate_ids(tmp_path):
    with pytest.raises(ValueError):
        save_exercises([make_exercise(), make_exercise()], tmp_path / "ex.json")


# --- admin review page ------------------------------------------------------


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    path = tmp_path / "exercises.json"
    save_exercises([make_exercise(), make_exercise(id="back-squat", name="Back Squat", pattern="squat")], path)
    monkeypatch.setenv("ENABLE_ADMIN", "true")
    monkeypatch.setenv("EXERCISES_PATH", str(path))
    get_settings.cache_clear()
    yield TestClient(app), path
    get_settings.cache_clear()


def test_admin_hidden_when_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_ADMIN", "false")  # env wins over a local .env
    get_settings.cache_clear()
    try:
        assert TestClient(app).get("/admin/exercises").status_code == 404
    finally:
        get_settings.cache_clear()


def test_admin_lists_and_filters(admin_client):
    client, _ = admin_client
    page = client.get("/admin/exercises")
    assert page.status_code == 200
    assert "Box Jump" in page.text and "Back Squat" in page.text

    filtered = client.get("/admin/exercises?pattern=squat", headers={"HX-Request": "true"})
    assert "Back Squat" in filtered.text and "Box Jump" not in filtered.text


def test_admin_toggle_reviewed(admin_client):
    client, path = admin_client
    assert client.post("/admin/exercises/box-jump/reviewed").status_code == 200
    saved = {e["id"]: e for e in json.loads(path.read_text(encoding="utf-8"))}
    assert saved["box-jump"]["reviewed"] is True
    assert saved["back-squat"]["reviewed"] is False


def test_admin_edit_saves_and_validates(admin_client):
    client, path = admin_client
    form = {
        "name": "Box Jump", "aliases": "box jumps, jump onto box",
        "pattern": "jump_vertical", "fv_zone": "speed_strength", "ssc": "slow", "emphasis": "concentric",
        "resistance": "bodyweight", "hardest_point": "bottom", "laterality": "bilateral",
        "fatigue": "2", "joint_stress": "1", "ground_contacts_per_rep": "1",
        "equipment": ["box"], "min_training_age_years": "0", "rep_min": "3", "rep_max": "6",
        "evidence_card_ids": "", "reviewed": "on",
    }
    ok = client.post("/admin/exercises/box-jump", data=form)
    assert ok.status_code == 200
    saved = next(e for e in load_exercises(path) if e.id == "box-jump")
    assert saved.rep_max == 6 and saved.reviewed and saved.aliases == ["box jumps", "jump onto box"]

    bad = client.post("/admin/exercises/box-jump", data=form | {"rep_min": "9"})
    assert bad.status_code == 422
    assert next(e for e in load_exercises(path) if e.id == "box-jump").rep_max == 6
