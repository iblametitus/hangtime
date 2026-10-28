"""Verdict: is the exercise backed by evidence, does it fit this athlete, why the swap.

REASON with thinking on: this is the one step where reasoning pays off. The model also decides
what the video promises, from all on-screen text and the caption: the FAST claim extraction
mixes up promises with set/rep instructions (test 28.10.), and the promise usually refers to
the whole routine, not the one exercise analysed.
"""

import json

from app.config import get_settings
from app.llm import call_json_schema
from app.models import (
    Claim,
    EvidenceCard,
    ExerciseProfile,
    ExternalSource,
    SwapProposal,
    UserProfile,
    Verdict,
    VideoUnderstanding,
)

VERDICT_PROMPT = """You are an evidence-based strength and conditioning coach. An athlete sent a training video.
Judge ONE exercise from it: whether it is backed by evidence, and whether it fits this athlete.

promise: what the video promises (a result or benefit, e.g. "+6 inches vertical"), taken from the on-screen
text or caption. Sets, reps, exercise names and instructions are not promises. If the video shows a routine,
the promise usually refers to the whole routine: then judge what THIS exercise can contribute and say so.
Empty string if there is no promise.

rating:
- well_supported: good direct evidence that the exercise does what is promised (or, without a promise,
  that it develops the athlete's goal)
- partly_supported: evidence for the direction, but the promise is exaggerated (size, speed) or the
  evidence is thin or indirect
- unsupported: no usable evidence either way
- myth: evidence contradicts the promise

Rules:
- Only cite by source_id. Every quote must be copied verbatim from key_findings, summary or snippet.
- Do not invent studies. If evidence is thin, say so.
- Evidence marked indirect (injury prevention, tendon health, pain, availability) can support a long-term
  benefit, never a specific performance promise such as '+10 cm in 4 weeks'.
- Web sources are not curated: prefer evidence cards, and name web sources as web sources.
- headline: one direct sentence. reasoning: max. 4 sentences.
- personal_fit: good_fit | conditional | not_recommended for this athlete's goal, level, injuries and
  equipment. personal_fit_reason: one or two sentences.
- swap_explanation: explain the given swap in one or two sentences; never propose a different swap.
  null if no swap is given.
- safety_notes: short, concrete, only if relevant (max. 3)."""


def _cards_block(cards: list[EvidenceCard]) -> list[dict]:
    return [
        {
            "source_id": c.id,
            "citation": c.citation,
            "evidence_path": c.evidence_path.value,
            "summary": c.summary,
            "key_findings": c.key_findings,
            "limitations": c.limitations,
        }
        for c in cards
    ]


def build_user_message(
    understanding: VideoUnderstanding,
    caption: str | None,
    claim: Claim,
    profile: ExerciseProfile,
    cards: list[EvidenceCard],
    web: list[ExternalSource],
    user: UserProfile,
    swap: SwapProposal | None,
    other_exercises: list[str],
) -> str:
    data = {
        "video": {
            "on_screen_text": understanding.on_screen_text,
            "caption": caption or "",
            "movement": understanding.movement_description,
            "other_exercises_in_video": other_exercises,
        },
        "exercise_judged": profile.model_dump(
            mode="json", include={"name", "pattern", "fv_zone", "ssc", "emphasis", "load_cost",
                                  "min_training_age_years", "contraindications"}
        ),
        "claim_extraction_hint": claim.promised_effect,
        "athlete": user.model_dump(mode="json"),
        "evidence_cards": _cards_block(cards),
        "web_sources_not_curated": [w.model_dump() for w in web],
        "swap": swap.model_dump() if swap else None,
    }
    return json.dumps(data, indent=1, ensure_ascii=False)


def judge(
    understanding: VideoUnderstanding,
    caption: str | None,
    claim: Claim,
    profile: ExerciseProfile,
    cards: list[EvidenceCard],
    web: list[ExternalSource],
    user: UserProfile,
    swap: SwapProposal | None = None,
    other_exercises: list[str] | None = None,
) -> Verdict:
    return call_json_schema(
        model=get_settings().model_reason,
        system_prompt=VERDICT_PROMPT,
        user_content=build_user_message(
            understanding, caption, claim, profile, cards, web, user, swap, other_exercises or []
        ),
        schema_model=Verdict,
    )
