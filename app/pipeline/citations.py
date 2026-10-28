"""Citation check: every quote in a verdict must be copied verbatim from the evidence it names.

A quote passes if, after normalising whitespace, case and dash/quote variants, it occurs in the
summary or a key finding of the named evidence card, or in the snippet of the named web source.
Failing quotes are removed. If none is left, the verdict drops to "unsupported".
"""

import logging
import re

from app.models import EvidenceCard, ExternalSource, Rating, Verdict

logger = logging.getLogger(__name__)

NO_EVIDENCE_HEADLINE = "No verifiable evidence found"

_TRANSLATE = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "−": "-"})


def normalise(text: str) -> str:
    text = text.translate(_TRANSLATE).lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" .\"'")


def _source_texts(cards: list[EvidenceCard], web: list[ExternalSource]) -> dict[str, list[str]]:
    texts = {c.id: [normalise(c.summary)] + [normalise(f) for f in c.key_findings] for c in cards}
    texts.update({s.id: [normalise(s.snippet)] for s in web})
    return texts


def check_citations(
    verdict: Verdict, cards: list[EvidenceCard], web: list[ExternalSource]
) -> tuple[Verdict, int]:
    """Return a cleaned copy of the verdict and the number of removed citations."""
    texts = _source_texts(cards, web)
    kept = []
    for citation in verdict.citations:
        quote = normalise(citation.quote)
        sources = texts.get(citation.source_id)
        if quote and sources and any(quote in t for t in sources):
            kept.append(citation)
        else:
            reason = "unknown source" if sources is None else "quote not found"
            logger.info("Removed citation %s (%s): %r", citation.source_id, reason, citation.quote[:80])

    removed = len(verdict.citations) - len(kept)
    cleaned = verdict.model_copy(update={"citations": kept})
    if not kept:
        cleaned = cleaned.model_copy(
            update={
                "rating": Rating.unsupported,
                "headline": NO_EVIDENCE_HEADLINE,
                "reasoning": f"{NO_EVIDENCE_HEADLINE}. {verdict.reasoning}".strip(),
            }
        )
    return cleaned, removed
