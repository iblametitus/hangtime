from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import admin, web
from app.exercises import load_exercises
from app.models import ExerciseProfile

app = FastAPI(title="Hangtime")
app.include_router(web.router)
app.include_router(admin.router)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/api/exercises")
def list_exercises() -> list[ExerciseProfile]:
    return load_exercises()
