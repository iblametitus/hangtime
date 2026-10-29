"""Demo athlete for the /demo route, the CLI and the eval script: a basketball player who
trains for vertical jump, two years of strength training, three sessions a week."""

from app.models import PlannedExercise, Session, TrainingPlan, UserProfile

DEMO_PROFILE = UserProfile(
    goal="vertical_jump",
    training_age_years=2,
    sessions_per_week=3,
    injuries=[],
    equipment=["none", "box", "barbell", "trap_bar", "dumbbell", "band", "bench", "rack", "step", "hurdle", "machine"],
)


def _ex(exercise_id: str, name: str, sets: int, reps: int, load: str | None = None) -> PlannedExercise:
    return PlannedExercise(exercise_id=exercise_id, raw_name=name, sets=sets, reps=reps, load=load)


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
