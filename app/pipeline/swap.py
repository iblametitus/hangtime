"""Swap algorithm (docs/SPEC.md section 5). Deterministic, no LLM: same input, same swap.

The new exercise replaces exactly one exercise in the next session, the one with the most similar
training stimulus and load, and keeps the volume comparable (ground contacts or fatigue).
"""

from pydantic import BaseModel

from app.models import (
    SSC,
    Emphasis,
    ExerciseProfile,
    FVZone,
    Pattern,
    PlannedExercise,
    Session,
    SwapProposal,
    TrainingPlan,
    UserProfile,
)

MIN_SIMILARITY = 0.60

FAMILIES = [
    {Pattern.squat, Pattern.lunge},
    {Pattern.hinge},
    {Pattern.jump_vertical, Pattern.jump_horizontal, Pattern.bound, Pattern.hop_unilateral, Pattern.landing},
    {Pattern.calf_ankle},
    {Pattern.sprint},
    {Pattern.core},
]

WEIGHTS = {"fv_zone": 0.30, "pattern": 0.25, "ssc": 0.15, "laterality": 0.10, "emphasis": 0.10, "load": 0.10}

_FV_ORDER = list(FVZone)
_SSC_ORDER = list(SSC)


class SwapResult(BaseModel):
    proposal: SwapProposal | None
    session: Session | None  # the session the swap was searched in
    blocked_reason: str | None  # the athlete must not do the new exercise -> personal_fit = not_recommended
    note: str | None  # why there is no swap, shown to the user


def family(pattern: Pattern) -> int | None:
    for i, members in enumerate(FAMILIES):
        if pattern in members:
            return i
    return None  # "other" belongs to no family and never matches


def user_block_reason(new: ExerciseProfile, user: UserProfile) -> str | None:
    """Step 1, athlete filters. None = the athlete may do the exercise."""
    missing = [e for e in new.equipment if e != "none" and e not in user.equipment]
    if missing:
        return f"needs equipment you don't have: {', '.join(missing).replace('_', ' ')}"
    if new.min_training_age_years > user.training_age_years:
        return (f"needs at least {new.min_training_age_years:g} years of strength training "
                f"(you have {user.training_age_years:g})")
    clash = [c for c in new.contraindications if c in user.injuries]
    if clash:
        return f"not advised with {', '.join(clash).replace('_', ' ')}"
    return None


def _ordered(a, b, order: list) -> float:
    gap = abs(order.index(a) - order.index(b))
    return 1.0 if gap == 0 else 0.5 if gap == 1 else 0.0


def similarity(new: ExerciseProfile, old: ExerciseProfile) -> tuple[float, list[str]]:
    """Step 2: weighted similarity 0-1 and the features that matched fully."""
    pattern = 1.0 if new.pattern == old.pattern else 0.6 if family(new.pattern) == family(old.pattern) else 0.0
    if Emphasis.mixed in (new.emphasis, old.emphasis) and new.emphasis != old.emphasis:
        emphasis = 0.5
    else:
        emphasis = 1.0 if new.emphasis == old.emphasis else 0.0
    delta = abs(new.load_cost.fatigue - old.load_cost.fatigue) + abs(new.load_cost.joint_stress - old.load_cost.joint_stress)
    points = {
        "fv_zone": _ordered(new.fv_zone, old.fv_zone, _FV_ORDER),
        "pattern": pattern,
        "ssc": _ordered(new.ssc, old.ssc, _SSC_ORDER),
        "laterality": 1.0 if new.laterality == old.laterality else 0.0,
        "emphasis": emphasis,
        "load": 1 - delta / 4,
    }
    score = round(sum(WEIGHTS[k] * v for k, v in points.items()), 3)
    return score, [k for k, v in points.items() if v == 1.0]


def next_session(plan: TrainingPlan, today: int) -> Session | None:
    """First session with weekday >= today (0 = Monday), otherwise the first session of the plan."""
    if not plan.sessions:
        return None
    upcoming = [s for s in plan.sessions if s.weekday is not None and s.weekday >= today]
    return min(upcoming, key=lambda s: s.weekday) if upcoming else plan.sessions[0]


def convert_volume(new: ExerciseProfile, old: ExerciseProfile, planned: PlannedExercise) -> tuple[int, str]:
    """Step 3: same sets; same total ground contacts for jumps, otherwise same total fatigue."""
    old_gc, new_gc = old.load_cost.ground_contacts_per_rep, new.load_cost.ground_contacts_per_rep
    if old_gc > 0 and new_gc > 0:
        raw = round(planned.reps * old_gc / new_gc)
        basis = (f"keeps ground contacts equal ({planned.sets}×{planned.reps}×{old_gc} = "
                 f"{planned.sets * planned.reps * old_gc} before)")
    else:
        raw = round(planned.reps * old.load_cost.fatigue / new.load_cost.fatigue)
        basis = (f"keeps total fatigue similar (fatigue {old.load_cost.fatigue} → {new.load_cost.fatigue} "
                 f"of 3 per rep)")
    reps = min(max(raw, new.rep_min), new.rep_max)
    note = f"Same {planned.sets} sets, {reps} reps: {basis}."
    if reps != raw:
        note += f" Capped to the {new.rep_min}–{new.rep_max} rep range of {new.name}."
    return reps, note


def propose_swap(new: ExerciseProfile, user: UserProfile, plan: TrainingPlan,
                 exercises: list[ExerciseProfile], today: int) -> SwapResult:
    session = next_session(plan, today)
    blocked = user_block_reason(new, user)
    if blocked:
        return SwapResult(proposal=None, session=session, blocked_reason=blocked, note=f"No swap: {new.name} {blocked}.")
    if any(p.exercise_id == new.id for s in plan.sessions for p in s.exercises):
        return SwapResult(proposal=None, session=session, blocked_reason=None,
                          note=f"{new.name} is already in your plan.")
    if session is None:
        return SwapResult(proposal=None, session=None, blocked_reason=None, note="No training plan yet.")

    by_id = {e.id: e for e in exercises}
    candidates = []
    for position, planned in enumerate(session.exercises):
        old = by_id.get(planned.exercise_id or "")
        if old is None or family(old.pattern) is None or family(old.pattern) != family(new.pattern):
            continue  # unknown plan entry, or different pattern family: hard filter
        score, matched = similarity(new, old)
        if score >= MIN_SIMILARITY:
            load = old.load_cost.fatigue + old.load_cost.joint_stress
            candidates.append((score, load, -position, planned, old, matched))
    if not candidates:
        return SwapResult(proposal=None, session=session, blocked_reason=None,
                          note=f"No equivalent slot in your next session ({session.label}).")

    # highest similarity; on a tie the exercise with the higher load is replaced (conservative)
    score, _, _, planned, old, matched = max(candidates, key=lambda c: c[:3])
    reps, volume_note = convert_volume(new, old, planned)
    proposal = SwapProposal(
        session_id=session.id,
        replaces_exercise_id=old.id,
        replaces_raw_name=planned.raw_name,
        new_exercise_id=new.id,
        old_prescription=f"{planned.sets}×{planned.reps}",
        new_prescription=f"{planned.sets}×{reps}",
        similarity=score,
        matched_on=matched,
        volume_note=volume_note,
    )
    return SwapResult(proposal=proposal, session=session, blocked_reason=None, note=None)


def apply_swap(plan: TrainingPlan, proposal: SwapProposal, new_name: str) -> TrainingPlan:
    """Plan with the swap applied; the input plan is not changed."""
    plan = plan.model_copy(deep=True)
    sets, reps = (int(x) for x in proposal.new_prescription.split("×"))
    for session in plan.sessions:
        if session.id != proposal.session_id:
            continue
        for i, planned in enumerate(session.exercises):
            if planned.exercise_id == proposal.replaces_exercise_id:
                session.exercises[i] = PlannedExercise(
                    exercise_id=proposal.new_exercise_id, raw_name=new_name, sets=sets, reps=reps, load=None
                )
                return plan
    return plan
