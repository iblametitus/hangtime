from app.models import Citation, Claim, EvidenceCard, Verdict
from app.pipeline import evidence as evidence_step
from app.pipeline.evidence import CardSelection, find_evidence, prefilter
from tests.test_exercises import make_exercise

CLAIM = Claim(exercise_name="Box Jump", promised_effect="+10 cm vertical", target_audience="",
              matched_exercise_id="box-jump", match_confidence=0.9)


def make_card(card_id: str, tags: list[str], **overrides) -> EvidenceCard:
    data = {
        "id": card_id,
        "citation": "Doe J (2020). A study. Journal.",
        "url": "https://doi.org/10/x",
        "study_type": "meta-analysis",
        "population": "athletes",
        "intervention": "plyometrics",
        "duration_weeks": 8,
        "outcome_measures": ["CMJ"],
        "summary": "Plyometric training improved countermovement jump height in athletes.",
        "key_findings": ["Plyometric training improved CMJ height (ES = 0.84).", "Effects were larger after 10 weeks."],
        "effect_direction": "positive",
        "effect_size": "ES = 0.84",
        "exercise_tags": tags,
        "evidence_path": "direct",
        "limitations": "Heterogeneous studies.",
    }
    return EvidenceCard.model_validate(data | overrides)


def make_verdict(citations: list[Citation]) -> Verdict:
    return Verdict(
        promise="+10 cm", rating="well_supported", headline="Works.", reasoning="Plyometrics help.", citations=citations,
        personal_fit="good_fit", personal_fit_reason="Fits.", swap_explanation=None, safety_notes=[],
    )


def test_prefilter_puts_exact_exercise_first_and_skips_unrelated():
    profile = make_exercise()  # box-jump, jump_vertical, speed_strength
    exact = make_card("exact", ["box-jump"])
    broad = make_card("broad", ["jump_vertical"])
    other = make_card("other", ["sprint", "max_strength"])
    assert [c.id for c in prefilter(profile, [broad, other, exact])] == ["exact", "broad"]


def test_find_evidence_uses_tavily_only_when_cards_are_thin(monkeypatch):
    profile = make_exercise()
    cards = [make_card("a", ["box-jump"]), make_card("b", ["jump_vertical"]), make_card("c", ["jump_vertical"])]
    searches = []
    monkeypatch.setattr(evidence_step, "search_research", lambda q: searches.append(q) or [])

    monkeypatch.setattr(evidence_step, "call_json_schema", lambda **_: CardSelection(card_ids=["b", "a", "zzz"]))
    selected, web = find_evidence(CLAIM, profile, cards)
    assert [c.id for c in selected] == ["b", "a"] and searches == []

    monkeypatch.setattr(evidence_step, "call_json_schema", lambda **_: CardSelection(card_ids=["c"]))
    selected, web = find_evidence(CLAIM, profile, cards)
    assert [c.id for c in selected] == ["c"] and len(searches) == 1
