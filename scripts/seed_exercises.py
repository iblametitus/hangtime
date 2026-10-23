"""Draft exercise profiles for data/exercises.json with a Nemotron model.

    uv run python scripts/seed_exercises.py            # add missing exercises only
    uv run python scripts/seed_exercises.py --redraft  # also redraft unreviewed ones

Every draft is written with reviewed=false. Reviewed entries are never touched.
The exercise list below is curated by hand; the model only fills in the profile.
"""

import argparse
import sys
from pathlib import Path

from pydantic import BaseModel, ValidationError, create_model

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.exercises import load_exercises, save_exercises  # noqa: E402
from app.llm import call_json_schema  # noqa: E402
from app.models import CONTRAINDICATIONS, EQUIPMENT, ExerciseProfile  # noqa: E402

BATCH_SIZE = 8

# id -> canonical English name. Jump/athleticism focus, from beginner to advanced.
EXERCISES: dict[str, str] = {
    # landing / foundation
    "drop-landing": "Drop Landing",
    "snap-down": "Snap Down",
    "single-leg-drop-landing": "Single-Leg Drop Landing",
    # low-intensity plyometrics
    "pogo-hops": "Pogo Hops",
    "line-hops": "Line Hops",
    "jump-rope": "Jump Rope",
    "squat-jump": "Squat Jump",
    "countermovement-jump": "Countermovement Jump",
    "tuck-jump": "Tuck Jump",
    "split-squat-jump": "Split Squat Jump",
    "skater-jump": "Skater Jump",
    "lateral-bound": "Lateral Bound",
    # high-intensity plyometrics
    "box-jump": "Box Jump",
    "seated-box-jump": "Seated Box Jump",
    "depth-jump": "Depth Jump",
    "drop-jump": "Drop Jump",
    "hurdle-hops": "Hurdle Hops",
    "broad-jump": "Broad Jump",
    "bounding": "Bounding",
    "single-leg-hop": "Single-Leg Hop",
    "single-leg-box-jump": "Single-Leg Box Jump",
    "approach-jump": "Approach Jump",
    "repeated-broad-jump": "Repeated Broad Jump",
    "single-leg-pogo": "Single-Leg Pogo Hops",
    # loaded jumps / ballistic
    "trap-bar-jump": "Trap Bar Jump",
    "dumbbell-squat-jump": "Dumbbell Squat Jump",
    "band-resisted-jump": "Band-Resisted Jump",
    "assisted-band-jump": "Band-Assisted Overspeed Jump",
    "kettlebell-swing": "Kettlebell Swing",
    "medicine-ball-scoop-toss": "Medicine Ball Scoop Toss",
    "medicine-ball-overhead-throw": "Medicine Ball Backward Overhead Throw",
    # Olympic lift derivatives
    "hang-power-clean": "Hang Power Clean",
    "block-power-clean": "Block Power Clean",
    "power-snatch": "Power Snatch",
    "clean-pull": "Clean Pull",
    "jump-shrug": "Jump Shrug",
    "push-press": "Push Press",
    # max strength: squat / lunge
    "back-squat": "Back Squat",
    "front-squat": "Front Squat",
    "half-squat-dead-stop": "Dead-Stop Half Squat",
    "goblet-squat": "Goblet Squat",
    "bulgarian-split-squat": "Bulgarian Split Squat",
    "reverse-lunge": "Reverse Lunge",
    "step-up": "Step-Up",
    "pistol-squat": "Pistol Squat",
    "leg-press": "Leg Press",
    "spanish-squat": "Spanish Squat",
    "isometric-squat-hold": "Isometric Squat Hold",
    # max strength: hinge
    "trap-bar-deadlift": "Trap Bar Deadlift",
    "conventional-deadlift": "Conventional Deadlift",
    "romanian-deadlift": "Romanian Deadlift",
    "single-leg-rdl": "Single-Leg Romanian Deadlift",
    "hip-thrust": "Hip Thrust",
    "nordic-hamstring-curl": "Nordic Hamstring Curl",
    "glute-ham-raise": "Glute-Ham Raise",
    # calf / ankle / knee resilience
    "standing-calf-raise": "Heavy Standing Calf Raise",
    "seated-calf-raise": "Seated Calf Raise",
    "single-leg-calf-raise": "Single-Leg Calf Raise",
    "tibialis-raise": "Tibialis Raise",
    "poliquin-step-up": "Poliquin Step-Up",
    "reverse-nordic": "Reverse Nordic",
    "copenhagen-plank": "Copenhagen Plank",
    # sprint
    "acceleration-sprint": "Acceleration Sprint (10-20 m)",
    "flying-sprint": "Flying Sprint (20-30 m)",
    "sled-push": "Sled Push",
    "sled-sprint": "Resisted Sled Sprint",
    "a-skip": "A-Skip",
    "hill-sprint": "Hill Sprint",
    # core
    "pallof-press": "Pallof Press",
    "dead-bug": "Dead Bug",
    "hanging-leg-raise": "Hanging Leg Raise",
}

SYSTEM_PROMPT = f"""You are a strength and conditioning coach building an exercise database for
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
ExerciseBatch = create_model("ExerciseBatch", exercises=(list[ExerciseDraft], ...))


def draft_batch(items: list[tuple[str, str]], model: str) -> list[ExerciseProfile]:
    user = "Profile these exercises:\n" + "\n".join(f"- id: {i}, name: {n}" for i, n in items)
    batch = call_json_schema(
        model=model, system_prompt=SYSTEM_PROMPT, user_content=user, schema_model=ExerciseBatch
    )
    names = dict(items)
    out = []
    for d in batch.exercises:
        if d.id not in names:
            print(f"  ! unexpected id from model: {d.id}")
            continue
        data = d.model_dump() | {"name": names[d.id], "evidence_card_ids": [], "reviewed": False}
        data["equipment"] = [e for e in data["equipment"] if e in EQUIPMENT] or ["none"]
        data["contraindications"] = [c for c in data["contraindications"] if c in CONTRAINDICATIONS]
        try:
            out.append(ExerciseProfile.model_validate(data))
        except ValidationError as exc:
            print(f"  ! {d.id} invalid, skipped: {exc.errors()[0]['msg']}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redraft", action="store_true", help="also redraft unreviewed entries")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.nebius_api_key:
        sys.exit("NEBIUS_API_KEY missing in .env")

    existing = {e.id: e for e in load_exercises()}
    todo = [
        (i, n)
        for i, n in EXERCISES.items()
        if i not in existing or (args.redraft and not existing[i].reviewed)
    ]
    print(f"{len(existing)} in database, {len(todo)} to draft with {settings.model_reason}")

    for start in range(0, len(todo), BATCH_SIZE):
        items = todo[start : start + BATCH_SIZE]
        print(f"batch {start // BATCH_SIZE + 1}: {', '.join(i for i, _ in items)}")
        try:
            drafts = draft_batch(items, settings.model_reason)
        except Exception as exc:  # keep going; rerun picks up what is missing
            print(f"  ! batch failed: {exc}")
            continue
        for d in drafts:
            existing[d.id] = d
        save_exercises(list(existing.values()))  # save after every batch

    missing = [i for i in EXERCISES if i not in existing]
    print(f"done: {len(existing)} exercises" + (f", missing: {missing}" if missing else ""))


if __name__ == "__main__":
    main()
