from app.models import Citation, ExternalSource
from app.pipeline.citations import NO_EVIDENCE_HEADLINE, check_citations, normalise
from tests.test_evidence import make_card, make_verdict


def test_verbatim_quote_stays_invented_quote_is_removed():
    card = make_card("doe-2020", [])
    verdict = make_verdict([
        Citation(source_id="doe-2020", quote="plyometric training improved  CMJ height (ES = 0.84)"),
        Citation(source_id="doe-2020", quote="Box jumps add 10 cm in four weeks."),
    ])
    cleaned, removed = check_citations(verdict, [card], [])
    assert removed == 1
    assert [c.quote for c in cleaned.citations] == ["plyometric training improved  CMJ height (ES = 0.84)"]
    assert cleaned.rating.value == "well_supported"


def test_quote_from_wrong_or_unknown_source_is_removed():
    a = make_card("a", [], key_findings=["Squats improved sprint time.", "Second finding."])
    b = make_card("b", [])
    verdict = make_verdict([
        Citation(source_id="b", quote="Squats improved sprint time."),  # real text, wrong card
        Citation(source_id="made-up-2024", quote="Plyometric training improved CMJ height"),
    ])
    cleaned, removed = check_citations(verdict, [a, b], [])
    assert removed == 2 and cleaned.citations == []


def test_no_citation_left_downgrades_to_unsupported():
    verdict = make_verdict([Citation(source_id="x", quote="anything")])
    cleaned, _ = check_citations(verdict, [], [])
    assert cleaned.rating.value == "unsupported"
    assert cleaned.headline == NO_EVIDENCE_HEADLINE


def test_web_snippet_quotes_are_checked_too():
    web = ExternalSource(id="web-1", title="t", url="u", snippet="Depth jumps increased jump height by 4.5 cm.")
    verdict = make_verdict([Citation(source_id="web-1", quote="depth jumps increased jump height by 4.5 cm")])
    cleaned, removed = check_citations(verdict, [], [web])
    assert removed == 0 and len(cleaned.citations) == 1


def test_normalise_unifies_dashes_quotes_and_case():
    assert normalise("ES – 0.8 “large”.") == normalise('es - 0.8 "large"')
