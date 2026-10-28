"""Draft exercise profiles for data/exercises.json with a Nemotron model.

    uv run python scripts/seed_exercises.py            # add missing exercises only
    uv run python scripts/seed_exercises.py --redraft  # also redraft unreviewed ones

Every draft is written with reviewed=false. Reviewed entries are never touched.
The exercise list below is curated by hand; the model only fills in the profile.
"""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError, create_model

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.exercises import load_exercises, save_exercises  # noqa: E402
from app.llm import call_json_schema  # noqa: E402
from app.models import ExerciseProfile  # noqa: E402
from app.profiling import PROFILE_PROMPT, ExerciseDraft, to_profile  # noqa: E402

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
    # social media favourites and research protocols
    "atg-split-squat": "ATG Split Squat",
    "sissy-squat": "Sissy Squat",
    "heel-elevated-squat": "Heel-Elevated Squat",
    "lateral-step-down": "Lateral Step-Down",
    "backward-sled-drag": "Backward Sled Drag",
    "weighted-vest-jump": "Weighted Vest Jump",
    "barbell-jump-squat": "Barbell Jump Squat",
    "flywheel-squat": "Flywheel Squat",
    "single-leg-depth-jump": "Single-Leg Depth Jump",
    "isometric-mid-thigh-pull": "Isometric Mid-Thigh Pull",
    "power-skip": "Power Skip",
}

ExerciseBatch = create_model("ExerciseBatch", exercises=(list[ExerciseDraft], ...))


def draft_batch(items: list[tuple[str, str]], model: str) -> list[ExerciseProfile]:
    user = "Profile these exercises:\n" + "\n".join(f"- id: {i}, name: {n}" for i, n in items)
    batch = call_json_schema(
        model=model, system_prompt=PROFILE_PROMPT, user_content=user, schema_model=ExerciseBatch
    )
    names = dict(items)
    out = []
    for d in batch.exercises:
        if d.id not in names:
            print(f"  ! unexpected id from model: {d.id}")
            continue
        try:
            out.append(to_profile(d, name=names[d.id]))
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
