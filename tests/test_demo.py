"""The demo athletes must be consistent with the exercise database, and the same video must give
each of them a different answer (that is the point of having three)."""

import pytest

from app.demo import TEMPLATES
from app.exercises import load_exercises
from app.pipeline.swap import propose_swap, user_block_reason

EXERCISES = {e.id: e for e in load_exercises()}
MONDAY = 0


@pytest.mark.parametrize("template", TEMPLATES.values(), ids=list(TEMPLATES))
def test_every_planned_exercise_exists_and_suits_its_athlete(template):
    for session in template.plan.sessions:
        for planned in session.exercises:
            exercise = EXERCISES[planned.exercise_id]
            assert user_block_reason(exercise, template.profile) is None, (template.id, exercise.id)
            assert exercise.rep_min <= planned.reps <= exercise.rep_max or planned.load == "seconds", exercise.id


def swap(template_id, exercise_id):
    t = TEMPLATES[template_id]
    return propose_swap(EXERCISES[exercise_id], t.profile, t.plan, list(EXERCISES.values()), MONDAY)


def test_depth_jump_is_blocked_for_the_beginner_only():
    assert "training" in swap("beginner", "depth-jump").blocked_reason
    assert swap("athlete", "depth-jump").proposal.replaces_exercise_id == "box-jump"
    assert swap("veteran", "depth-jump").blocked_reason is None


def test_knee_dominant_hold_is_blocked_for_the_veteran():
    assert "patellar tendinopathy" in swap("veteran", "isometric-squat-hold").blocked_reason
    assert swap("athlete", "isometric-squat-hold").blocked_reason is None


def test_alternative_equipment_is_enough():
    # goblet squat lists "dumbbell, kettlebell"; the beginner has dumbbells only
    assert user_block_reason(EXERCISES["goblet-squat"], TEMPLATES["beginner"].profile) is None
