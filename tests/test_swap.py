"""Swap algorithm (SPEC section 5). Profiles copy the values of data/exercises.json (29.10.) so the
tests stay stable when the database changes. Cases drafted by Claude, Titus checks them off."""

from app.models import PlannedExercise, Session, TrainingPlan, UserProfile
from app.pipeline.swap import apply_swap, next_session, propose_swap, similarity
from tests.test_exercises import make_exercise


def ex(id, pattern, fv, ssc, emphasis, fatigue, joint, gc, equipment=("none",), age=0, reps=(3, 8),
       contra=(), laterality="bilateral"):
    return make_exercise(
        id=id, name=id.replace("-", " ").title(), pattern=pattern, fv_zone=fv, ssc=ssc, emphasis=emphasis,
        laterality=laterality, load_cost={"fatigue": fatigue, "joint_stress": joint, "ground_contacts_per_rep": gc},
        equipment=list(equipment), min_training_age_years=age, rep_min=reps[0], rep_max=reps[1],
        contraindications=list(contra),
    )


BOX_JUMP = ex("box-jump", "jump_vertical", "speed_strength", "slow", "concentric", 2, 2, 1, ["box"], 1, (3, 6))
BACK_SQUAT = ex("back-squat", "squat", "max_strength", "none", "concentric", 3, 3, 0, ["barbell", "rack"], 1, (3, 8))
FRONT_SQUAT = ex("front-squat", "squat", "max_strength", "none", "concentric", 3, 3, 0, ["barbell", "rack"], 1, (3, 8))
RDL = ex("romanian-deadlift", "hinge", "max_strength", "none", "eccentric", 3, 3, 0, ["barbell", "rack"], 2, (4, 8))
POGO = ex("pogo-hops", "jump_vertical", "reactive", "fast", "mixed", 2, 2, 1, ["none"], 0, (10, 20))
CMJ = ex("countermovement-jump", "jump_vertical", "speed_strength", "slow", "mixed", 2, 2, 1, ["none"], 0, (3, 6))
DEPTH_JUMP = ex("depth-jump", "jump_vertical", "reactive", "fast", "mixed", 3, 3, 1, ["box"], 2, (3, 5),
                ["knee_pain", "achilles_tendinopathy"])
SINGLE_LEG_HOP = ex("single-leg-hop", "hop_unilateral", "reactive", "fast", "mixed", 3, 3, 1, ["none"], 2, (6, 10),
                    ["ankle_instability", "achilles_tendinopathy"], laterality="unilateral")
HIP_THRUST = ex("hip-thrust", "hinge", "max_strength", "none", "concentric", 2, 2, 0, ["barbell", "bench"], 0, (6, 12))
ISO_SQUAT = ex("isometric-squat-hold", "squat", "max_strength", "none", "isometric", 2, 2, 0, ["none"], 0, (20, 60))
DB = [BOX_JUMP, BACK_SQUAT, FRONT_SQUAT, RDL, POGO, CMJ, DEPTH_JUMP, SINGLE_LEG_HOP, HIP_THRUST, ISO_SQUAT]

ATHLETE = UserProfile(goal="vertical_jump", training_age_years=2, sessions_per_week=3, injuries=[],
                      equipment=["none", "box", "barbell", "rack", "bench"])


def planned(e, sets, reps):
    return PlannedExercise(exercise_id=e.id, raw_name=e.name, sets=sets, reps=reps, load=None)


PLAN = TrainingPlan(sessions=[
    Session(id="mon", label="Monday", weekday=0, exercises=[planned(BOX_JUMP, 4, 4), planned(BACK_SQUAT, 4, 5), planned(RDL, 3, 8)]),
    Session(id="wed", label="Wednesday", weekday=2, exercises=[planned(POGO, 3, 20)]),
    Session(id="fri", label="Friday", weekday=4, exercises=[planned(CMJ, 3, 5), planned(FRONT_SQUAT, 3, 5)]),
])
MONDAY, WEDNESDAY, THURSDAY, SATURDAY = 0, 2, 3, 5


def swap(new, user=ATHLETE, today=MONDAY, plan=PLAN):
    return propose_swap(new, user, plan, DB, today)


# 1
def test_depth_jump_replaces_box_jump_not_back_squat():
    p = swap(DEPTH_JUMP).proposal
    assert p.replaces_exercise_id == "box-jump"
    assert p.session_id == "mon"


# 2
def test_single_leg_hop_is_rejected_with_ankle_instability():
    r = swap(SINGLE_LEG_HOP, user=ATHLETE.model_copy(update={"injuries": ["ankle_instability"]}), today=WEDNESDAY)
    assert r.proposal is None
    assert "ankle instability" in r.blocked_reason


# 3
def test_too_little_training_age_blocks_depth_jump():
    r = swap(DEPTH_JUMP, user=ATHLETE.model_copy(update={"training_age_years": 1}))
    assert r.proposal is None and "2 years" in r.blocked_reason


# 4
def test_missing_equipment_blocks():
    r = swap(DEPTH_JUMP, user=ATHLETE.model_copy(update={"equipment": ["none", "barbell", "rack"]}))
    assert r.proposal is None and "box" in r.blocked_reason


# 5
def test_no_swap_across_pattern_families():
    r = swap(HIP_THRUST, today=WEDNESDAY)  # Wednesday has only pogo hops
    assert r.proposal is None and r.blocked_reason is None
    assert "No equivalent slot" in r.note


# 6
def test_jumps_keep_ground_contacts_and_cap_to_rep_range():
    p = swap(DEPTH_JUMP, today=WEDNESDAY).proposal  # 3x20 pogo hops = 60 contacts
    assert p.replaces_exercise_id == "pogo-hops"
    assert (p.old_prescription, p.new_prescription) == ("3×20", "3×5")  # 20 -> capped to 5
    assert "Capped to the 3–5 rep range" in p.volume_note


# 7
def test_strength_exercises_keep_total_fatigue():
    p = swap(HIP_THRUST).proposal  # RDL 3x8, fatigue 3 -> hip thrust fatigue 2
    assert p.replaces_exercise_id == "romanian-deadlift"
    assert p.new_prescription == "3×12"
    assert "fatigue 3 → 2" in p.volume_note


# 8
def test_next_session_is_the_next_weekday_then_wraps_to_the_first():
    assert next_session(PLAN, THURSDAY).id == "fri"
    assert next_session(PLAN, SATURDAY).id == "mon"
    assert next_session(PLAN, WEDNESDAY).id == "wed"
    assert swap(ISO_SQUAT, today=THURSDAY).proposal.replaces_exercise_id == "front-squat"


# 9
def test_on_a_tie_the_exercise_with_more_load_is_replaced():
    heavy = ex("heavy", "squat", "max_strength", "none", "concentric", 3, 3, 0)
    light = ex("light", "squat", "max_strength", "none", "concentric", 1, 1, 0)
    new = ex("new", "squat", "max_strength", "none", "concentric", 2, 2, 0)
    assert similarity(new, heavy)[0] == similarity(new, light)[0]
    plan = TrainingPlan(sessions=[Session(id="s", label="S", weekday=0, exercises=[planned(light, 3, 5), planned(heavy, 3, 5)])])
    assert propose_swap(new, ATHLETE, plan, [heavy, light, new], MONDAY).proposal.replaces_exercise_id == "heavy"


# 10
def test_below_threshold_means_no_swap():
    sprint_like = ex("odd-squat", "lunge", "reactive", "fast", "eccentric", 1, 1, 0, laterality="unilateral")
    assert similarity(sprint_like, BACK_SQUAT)[0] < 0.6
    assert swap(sprint_like).proposal is None


# 11
def test_exercise_already_in_plan_is_not_swapped():
    r = swap(CMJ)
    assert r.proposal is None and "already in your plan" in r.note


# 12
def test_same_input_same_output_and_apply_does_not_mutate():
    a, b = swap(DEPTH_JUMP), swap(DEPTH_JUMP)
    assert a == b
    new_plan = apply_swap(PLAN, a.proposal, DEPTH_JUMP.name)
    assert [e.exercise_id for e in new_plan.sessions[0].exercises] == ["depth-jump", "back-squat", "romanian-deadlift"]
    assert (new_plan.sessions[0].exercises[0].sets, new_plan.sessions[0].exercises[0].reps) == (4, 4)
    assert PLAN.sessions[0].exercises[0].exercise_id == "box-jump"
