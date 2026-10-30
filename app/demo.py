"""Demo athletes for the /demo route, the CLI and the eval script.

Three templates, each an athlete with a plan that fits them. The same video gives each of them a
different answer: the beginner is blocked from advanced plyometrics, the veteran with a sore
patellar tendon is kept away from knee-dominant holds, the basketball athlete gets a swap.
"""

from dataclasses import dataclass

from app.models import PlannedExercise, Session, TrainingPlan, UserProfile


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    tagline: str
    profile: UserProfile
    plan: TrainingPlan


def _ex(exercise_id: str, name: str, sets: int, reps: int, load: str | None = None) -> PlannedExercise:
    return PlannedExercise(exercise_id=exercise_id, raw_name=name, sets=sets, reps=reps, load=load)


# --- Basketball athlete: two years in the gym, three sessions a week -------------------------

DEMO_PROFILE = UserProfile(
    goal="vertical_jump",
    training_age_years=2,
    sessions_per_week=3,
    injuries=[],
    equipment=["none", "box", "barbell", "trap_bar", "dumbbell", "band", "bench", "rack", "step", "hurdle", "machine"],
)

DEMO_PLAN = TrainingPlan(
    sessions=[
        Session(
            id="mon",
            label="Monday - Lower power",
            weekday=0,
            exercises=[
                _ex("box-jump", "Box Jump", 4, 4, "60 cm box"),
                _ex("back-squat", "Back Squat", 4, 5, "80% 1RM"),
                _ex("romanian-deadlift", "Romanian Deadlift", 3, 8, "60% 1RM"),
                _ex("standing-calf-raise", "Standing Calf Raise", 3, 12),
            ],
        ),
        Session(
            id="wed",
            label="Wednesday - Reactive and unilateral",
            weekday=2,
            exercises=[
                _ex("pogo-hops", "Pogo Hops", 3, 20),
                _ex("bulgarian-split-squat", "Bulgarian Split Squat", 3, 8, "2 x 16 kg"),
                _ex("single-leg-rdl", "Single-Leg RDL", 3, 8),
                _ex("nordic-hamstring-curl", "Nordic Hamstring Curl", 3, 5),
            ],
        ),
        Session(
            id="fri",
            label="Friday - Max strength",
            weekday=4,
            exercises=[
                _ex("countermovement-jump", "Countermovement Jump", 3, 5),
                _ex("trap-bar-deadlift", "Trap Bar Deadlift", 4, 4, "85% 1RM"),
                _ex("front-squat", "Front Squat", 3, 5, "75% 1RM"),
                _ex("copenhagen-plank", "Copenhagen Plank", 3, 20, "seconds"),
            ],
        ),
    ]
)

# --- Beginner: half a year of training, home setup, two sessions a week ----------------------

BEGINNER_PROFILE = UserProfile(
    goal="vertical_jump",
    training_age_years=0.5,
    sessions_per_week=2,
    injuries=[],
    equipment=["none", "box", "dumbbell", "band", "step", "bench"],
)

BEGINNER_PLAN = TrainingPlan(
    sessions=[
        Session(
            id="tue",
            label="Tuesday - Jump basics",
            weekday=1,
            exercises=[
                _ex("countermovement-jump", "Countermovement Jump", 3, 5),
                _ex("pogo-hops", "Pogo Hops", 2, 10),
                _ex("goblet-squat", "Goblet Squat", 3, 8, "16 kg dumbbell"),
                _ex("reverse-lunge", "Reverse Lunge", 3, 8),
            ],
        ),
        Session(
            id="fri",
            label="Friday - Strength basics",
            weekday=4,
            exercises=[
                _ex("squat-jump", "Squat Jump", 3, 5),
                _ex("step-up", "Step-Up", 3, 8, "40 cm box"),
                _ex("glute-ham-raise", "Glute-Ham Raise", 3, 8),
                _ex("single-leg-calf-raise", "Single-Leg Calf Raise", 3, 12),
            ],
        ),
    ]
)

# --- Veteran: five years, full gym, patellar tendinopathy (jumper's knee) --------------------

VETERAN_PROFILE = UserProfile(
    goal="vertical_jump",
    training_age_years=5,
    sessions_per_week=3,
    injuries=["patellar_tendinopathy"],
    equipment=["none", "box", "barbell", "trap_bar", "dumbbell", "kettlebell", "band", "bench", "rack", "step",
               "medicine_ball", "machine"],
)

VETERAN_PLAN = TrainingPlan(
    sessions=[
        Session(
            id="mon",
            label="Monday - Strength, tendon-friendly",
            weekday=0,
            exercises=[
                _ex("spanish-squat", "Spanish Squat", 4, 8, "band + 20 kg"),
                _ex("trap-bar-deadlift", "Trap Bar Deadlift", 4, 4, "85% 1RM"),
                _ex("hip-thrust", "Hip Thrust", 3, 8, "100 kg"),
                _ex("single-leg-calf-raise", "Single-Leg Calf Raise", 3, 10),
            ],
        ),
        Session(
            id="wed",
            label="Wednesday - Power",
            weekday=2,
            exercises=[
                _ex("hang-power-clean", "Hang Power Clean", 4, 3, "70% 1RM"),
                _ex("broad-jump", "Broad Jump", 4, 4),
                _ex("medicine-ball-scoop-toss", "Med Ball Scoop Toss", 3, 6, "5 kg"),
                _ex("nordic-hamstring-curl", "Nordic Hamstring Curl", 3, 4),
            ],
        ),
        Session(
            id="sat",
            label="Saturday - Speed",
            weekday=5,
            exercises=[
                _ex("acceleration-sprint", "Acceleration Sprint", 5, 4, "20 m"),
                _ex("isometric-mid-thigh-pull", "Isometric Mid-Thigh Pull", 3, 4, "5 s"),
                _ex("copenhagen-plank", "Copenhagen Plank", 3, 20, "seconds"),
            ],
        ),
    ]
)

TEMPLATES = {
    t.id: t
    for t in [
        Template("beginner", "Beginner", "Half a year of training, home setup, 2 sessions a week", BEGINNER_PROFILE, BEGINNER_PLAN),
        Template("athlete", "Athlete", "Basketball player, two years in the gym, 3 sessions a week", DEMO_PROFILE, DEMO_PLAN),
        Template("veteran", "Veteran", "Five years in the gym, living with jumper's knee", VETERAN_PROFILE, VETERAN_PLAN),
    ]
}
DEFAULT_TEMPLATE = "athlete"
