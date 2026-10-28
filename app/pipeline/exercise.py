"""Identify the exercise and the claim, and get a profile for it.

Known exercise -> profile from data/exercises.json. Unknown exercise -> REASON drafts a full profile
(auto_profiled=True, reviewed=False). It is not written to the database: drafts only enter the
database after Titus reviewed them.
"""

import re

from app.config import get_settings
from app.llm import call_json_schema
from app.models import Claim, ExerciseProfile, VideoUnderstanding
from app.profiling import PROFILE_PROMPT, ExerciseDraft, to_profile

EXERCISE_PROMPT = (
    "Identify the exercise and the claim. The claim may be in the on-screen text, the caption, or both; "
    "prefer the most specific promise. If it matches a known exercise, return its id as "
    "matched_exercise_id. Otherwise return null. match_confidence is between 0 and 1. If there is no "
    "promise, set promised_effect to an empty string."
)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unknown-exercise"


def exercise_list(exercises: list[ExerciseProfile]) -> str:
    return "\n".join(
        f"{e.id}: {e.name}" + (f" ({', '.join(e.aliases)})" if e.aliases else "") for e in exercises
    )


def build_user_message(
    understanding: VideoUnderstanding, caption: str | None, exercises: list[ExerciseProfile]
) -> str:
    text = "\n".join(f"- {t}" for t in understanding.on_screen_text) or "(none)"
    return "\n".join([
        "VIDEO",
        f"Movement: {understanding.movement_description}",
        f"Execution: {understanding.execution_notes}",
        f"Equipment seen: {', '.join(understanding.equipment_seen) or 'none'}",
        f"On-screen text:\n{text}",
        "",
        "CAPTION",
        caption.strip() if caption and caption.strip() else "(none)",
        "",
        "KNOWN EXERCISES (id: name (aliases))",
        exercise_list(exercises),
    ])


def identify(
    understanding: VideoUnderstanding, caption: str | None, exercises: list[ExerciseProfile]
) -> tuple[Claim, ExerciseProfile]:
    settings = get_settings()
    claim = call_json_schema(
        model=settings.model_fast,
        system_prompt=EXERCISE_PROMPT,
        user_content=build_user_message(understanding, caption, exercises),
        schema_model=Claim,
    )
    by_id = {e.id: e for e in exercises}
    if claim.matched_exercise_id in by_id:
        return claim, by_id[claim.matched_exercise_id]

    # Model returned null or an id that does not exist: profile the exercise from scratch.
    # REASON, like scripts/seed_exercises.py: FAST returned empty output for this large schema.
    claim.matched_exercise_id = None
    new_id = slugify(claim.exercise_name)
    draft = call_json_schema(
        model=settings.model_reason,
        system_prompt=PROFILE_PROMPT,
        user_content=(
            f"Profile this exercise:\n- id: {new_id}, name: {claim.exercise_name}\n\n"
            f"What the video shows: {understanding.movement_description}"
        ),
        schema_model=ExerciseDraft,
    )
    draft.id = new_id
    return claim, to_profile(draft, name=claim.exercise_name, auto_profiled=True)
