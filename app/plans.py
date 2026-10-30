"""Chosen demo athlete and training plan per browser session (cookie `ht_session`), in memory
like the jobs.

Every session starts with the default template; picking another template starts its plan fresh.
"Apply swap" changes only that session's copy.
"""

import threading
import uuid

from app.demo import DEFAULT_TEMPLATE, TEMPLATES, Template
from app.models import TrainingPlan

COOKIE = "ht_session"
MAX_SESSIONS = 500

_state: dict[str, tuple[str, TrainingPlan]] = {}  # session id -> (template id, plan)
_lock = threading.Lock()


def new_session_id() -> str:
    return uuid.uuid4().hex


def get_template(session_id: str) -> Template:
    with _lock:
        template_id = _state.get(session_id, (DEFAULT_TEMPLATE, None))[0]
    return TEMPLATES[template_id]


def get_plan(session_id: str) -> TrainingPlan:
    with _lock:
        entry = _state.get(session_id)
    plan = entry[1] if entry else TEMPLATES[DEFAULT_TEMPLATE].plan
    return plan.model_copy(deep=True)


def set_plan(session_id: str, plan: TrainingPlan) -> None:
    _store(session_id, get_template(session_id).id, plan)


def select(session_id: str, template_id: str) -> None:
    """Switch the athlete; the plan starts fresh from the template."""
    _store(session_id, template_id, TEMPLATES[template_id].plan.model_copy(deep=True))


def reset(session_id: str) -> None:
    select(session_id, get_template(session_id).id)


def _store(session_id: str, template_id: str, plan: TrainingPlan) -> None:
    with _lock:
        _state.pop(session_id, None)  # re-insert so the oldest sessions are dropped first
        _state[session_id] = (template_id, plan)
        while len(_state) > MAX_SESSIONS:
            _state.pop(next(iter(_state)))
