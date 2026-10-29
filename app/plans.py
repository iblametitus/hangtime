"""Training plan per browser session (cookie `ht_session`), in memory like the jobs.

Every new session starts from the demo plan; "Apply swap" changes only that session's copy.
"""

import threading
import uuid

from app.demo import DEMO_PLAN
from app.models import TrainingPlan

COOKIE = "ht_session"
MAX_SESSIONS = 500

_plans: dict[str, TrainingPlan] = {}
_lock = threading.Lock()


def new_session_id() -> str:
    return uuid.uuid4().hex


def get_plan(session_id: str) -> TrainingPlan:
    with _lock:
        return _plans.get(session_id, DEMO_PLAN).model_copy(deep=True)


def set_plan(session_id: str, plan: TrainingPlan) -> None:
    with _lock:
        _plans[session_id] = plan
        while len(_plans) > MAX_SESSIONS:
            _plans.pop(next(iter(_plans)))


def reset(session_id: str) -> None:
    with _lock:
        _plans.pop(session_id, None)
