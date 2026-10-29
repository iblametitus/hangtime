from fastapi import FastAPI

from app import admin, web
from app.exercises import load_exercises
from app.models import ExerciseProfile

app = FastAPI(title="Hangtime")
app.include_router(web.router)
app.include_router(admin.router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/api/exercises")
def list_exercises() -> list[ExerciseProfile]:
    return load_exercises()
