"""Find evidence for an exercise and its claim (docs/SPEC.md "Evidenz-Auswahl", no vector DB).

1. Tag prefilter: cards tagged with the exercise id, its pattern or its force-velocity zone.
2. FAST picks the 1-5 most relevant prefiltered cards (sees only id, citation and summary).
3. Tavily only if fewer than 2 cards are left.
"""

from pydantic import BaseModel

from app.config import get_settings
from app.llm import call_json_schema
from app.models import Claim, EvidenceCard, ExerciseProfile, ExternalSource
from app.tavily_client import search_research

MIN_CARDS = 2
MAX_CARDS = 5

SELECT_PROMPT = (
    "You select research for checking a fitness claim. From the candidate studies, return the ids of "
    "the 1-5 studies that are most relevant to this exercise and this claim, best first. Return an "
    "empty list if none is relevant. Only use ids from the list."
)


class CardSelection(BaseModel):
    card_ids: list[str]


def prefilter(profile: ExerciseProfile, cards: list[EvidenceCard]) -> list[EvidenceCard]:
    """Cards about this exact exercise first, then cards matching its pattern or F-V zone."""
    exact = [c for c in cards if profile.id in c.exercise_tags]
    broad = [
        c for c in cards
        if c not in exact and (profile.pattern.value in c.exercise_tags or profile.fv_zone.value in c.exercise_tags)
    ]
    return exact + broad


def select_cards(claim: Claim, profile: ExerciseProfile, candidates: list[EvidenceCard]) -> list[EvidenceCard]:
    if len(candidates) <= 1:
        return candidates
    listing = "\n".join(f"- {c.id}: {c.citation} | {c.summary}" for c in candidates)
    selection = call_json_schema(
        model=get_settings().model_fast,
        system_prompt=SELECT_PROMPT,
        user_content=(
            f"Exercise: {profile.name} (pattern {profile.pattern.value}, zone {profile.fv_zone.value})\n"
            f"Claim: {claim.promised_effect or '(no specific promise)'}\n\nCandidates:\n{listing}"
        ),
        schema_model=CardSelection,
        thinking=False,
    )
    by_id = {c.id: c for c in candidates}
    picked = [by_id[i] for i in dict.fromkeys(selection.card_ids) if i in by_id]
    return picked[:MAX_CARDS]


def web_query(claim: Claim, profile: ExerciseProfile) -> str:
    effect = claim.promised_effect or "jump height performance"
    return f"{profile.name} training effect on {effect} study"


def find_evidence(
    claim: Claim, profile: ExerciseProfile, cards: list[EvidenceCard]
) -> tuple[list[EvidenceCard], list[ExternalSource]]:
    selected = select_cards(claim, profile, prefilter(profile, cards))
    web = search_research(web_query(claim, profile)) if len(selected) < MIN_CARDS else []
    return selected, web
