"""Exercise profiling with a Nemotron model: shared by scripts/seed_exercises.py (curated list)
and the video pipeline (exercises that are not in the database yet).

Profiles are always drafts (reviewed=false). Equipment and contraindications are clamped to the
fixed vocabularies so the swap algorithm can compare them.
"""

from pydantic import BaseModel, create_model

from app.models import CONTRAINDICATIONS, EQUIPMENT, ExerciseProfile

PROFILE_PROMPT = f"""You are a strength and conditioning coach building an exercise database for
athletes who train for vertical jump, sprint speed and injury resilience.
For each exercise you get (id + name), fill in a complete, realistic profile. Return the id exactly as given.

Field guide:
- aliases: common alternative names people use in videos and plans (English, max. 4).
- pattern: the main movement pattern. Plyometric jumps for height = jump_vertical (also depth/drop jumps),
  for distance = jump_horizontal, alternating single-leg = bound, repeated single-leg = hop_unilateral,
  absorbing force only = landing. Split squats, step-ups and lunges = lunge. Olympic lifts = hinge.
  Sprint drills and sprints = sprint. Anti-rotation and trunk work = core.
- fv_zone: position on the force-velocity curve. max_strength (heavy, slow, >80% 1RM, also heavy
  eccentric/isometric strength work like Nordics), strength_speed (heavy-ish but fast: Olympic lifts, loaded
  jumps, sled sprints), speed_strength (light/bodyweight, maximal intent: squat jumps, box jumps, med ball
  throws), reactive (fast stretch-shortening, ground contact < 250 ms: pogos, depth jumps, hurdle hops).
- ssc: stretch-shortening cycle. none = starts from a dead stop or has no rebound (strength lifts, seated box
  jump, squat jump), slow = countermovement > 250 ms (countermovement jump, box jump), fast = rebound < 250 ms.
- emphasis: which muscle action the exercise mainly trains. Use mixed only for genuinely mixed actions.
- resistance: main external resistance.
- hardest_point: where in the range of motion the exercise is hardest.
- load_cost.fatigue and load_cost.joint_stress: 1 (low), 2 (moderate), 3 (high). Use the full range.
- load_cost.ground_contacts_per_rep: foot contacts with impact per rep (depth jump = 1, one bound = 1,
  one sprint rep = roughly its number of steps). 0 for exercises without impact.
- equipment: only from {EQUIPMENT}. Use ["none"] if nothing is needed. Only what is required, not optional.
- min_training_age_years: years of structured strength training needed to do it safely (0 to 3).
- rep_min / rep_max: typical reps per set in athletic training. For isometric holds, seconds per set.
- contraindications: only from {CONTRAINDICATIONS}. An athlete with this condition is filtered away from
  the exercise, so list a condition ONLY if the exercise is clearly a bad idea with it. Most exercises have
  0 or 1, never more than 2. Low-impact strength and rehab exercises usually have none.
- evidence_card_ids: always []."""


def _draft_model() -> type[BaseModel]:
    """ExerciseProfile without the fields the model must not decide."""
    skip = {"reviewed", "auto_profiled"}
    fields = {
        name: (info.annotation, info)
        for name, info in ExerciseProfile.model_fields.items()
        if name not in skip
    }
    return create_model("ExerciseDraft", **fields)


ExerciseDraft = _draft_model()


def to_profile(draft: BaseModel, *, name: str | None = None, auto_profiled: bool = False) -> ExerciseProfile:
    """Turn a model draft into a validated ExerciseProfile. Raises ValidationError if it is unusable."""
    data = draft.model_dump() | {"evidence_card_ids": [], "reviewed": False, "auto_profiled": auto_profiled}
    if name:
        data["name"] = name
    data["equipment"] = [e for e in data["equipment"] if e in EQUIPMENT] or ["none"]
    data["contraindications"] = [c for c in data["contraindications"] if c in CONTRAINDICATIONS]
    return ExerciseProfile.model_validate(data)
