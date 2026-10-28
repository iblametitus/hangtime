"""Turn studies in data/raw/ (PDF, PMC JATS XML, Markdown abstracts) into evidence card drafts.

    uv run python scripts/ingest_studies.py            # ingest files without a card yet
    uv run python scripts/ingest_studies.py FILE ...   # (re)ingest specific files

Every card is written with reviewed=false. A card that Titus already reviewed is never
overwritten. data/evidence_cards/_ingested.json maps raw file name -> card id, so reruns
skip what is done. Only the card (own summary + citation) goes into the repo, never the study.
"""

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pydantic import create_model

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.evidence_cards import load_cards, save_card  # noqa: E402
from app.exercises import load_exercises  # noqa: E402
from app.llm import call_json_schema  # noqa: E402
from app.models import EvidenceCard, FVZone, Pattern  # noqa: E402

RAW_DIR = Path("data/raw")
MAX_CHARS = 24_000  # abstract, methods and results fit; reference lists are cut anyway
WORKERS = 4

CardDraft = create_model(
    "CardDraft",
    **{n: (f.annotation, f) for n, f in EvidenceCard.model_fields.items() if n != "reviewed"},
)

SYSTEM_PROMPT = """You are a sports scientist writing evidence cards for an app that checks fitness claims.
From the study text, write one card. Be strictly faithful to the study; never add numbers it does not report.

- id: lowercase slug "firstauthor-year-short-topic", e.g. "markovic-2007-plyo-meta".
- citation: "Author A, Author B, et al. (Year). Title. Journal." Use the real authors.
- url: the DOI as https://doi.org/... if present, else the PubMed or journal link from the text, else "".
- study_type: "meta-analysis", "systematic review", "network meta-analysis", "RCT", "review", "cross-sectional", ...
- population: who was studied (age, sex, training level, sport).
- intervention: what was done (exercise, volume, duration).
- duration_weeks: typical intervention length in weeks, null if not applicable.
- summary: 2-3 sentences in your own words.
- key_findings: 2-5 short, checkable statements (one fact each, with the effect size or numbers the study
  reports). These are quoted verbatim later, so make each one self-contained.
- effect_direction: "positive" | "no_effect" | "mixed" | "negative".
- effect_size: verbatim from the study (e.g. "ES = 0.84, 95% CI 0.60-1.08"), null if none reported.
- exercise_tags: only from the allowed tag list below: movement patterns, force-velocity zones and
  exercise ids the study is directly about. 2-8 tags.
- evidence_path: "direct" if outcomes are jump, sprint, strength or power performance; "indirect" if
  outcomes are injury risk, tendon health, pain or availability.
- limitations: 1-2 sentences (sample size, population, risk of bias, heterogeneity)."""


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "card"


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    elif suffix == ".xml":
        raw = path.read_text(encoding="utf-8", errors="ignore")
        raw = re.sub(r"<ref-list.*?</ref-list>", " ", raw, flags=re.S)  # drop references
        raw = re.sub(r"<(table-wrap|fig)\b.*?</\1>", " ", raw, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", raw)
    else:
        text = path.read_text(encoding="utf-8", errors="ignore")
    # Cut the reference list of PDFs, then collapse whitespace.
    text = re.split(r"\n\s*(References|REFERENCES|Bibliography)\s*\n", text)[0]
    return re.sub(r"\s+", " ", text).strip()[:MAX_CHARS]


def allowed_tags() -> list[str]:
    return [p.value for p in Pattern] + [z.value for z in FVZone] + [e.id for e in load_exercises()]


def draft_card(path: Path, tags: list[str], model: str) -> EvidenceCard:
    text = extract_text(path)
    if len(text) < 500:
        raise ValueError(f"only {len(text)} characters of text extracted")
    draft = call_json_schema(
        model=model,
        system_prompt=SYSTEM_PROMPT + "\n\nAllowed exercise_tags:\n" + ", ".join(tags),
        user_content=f"Study file: {path.name}\n\n{text}",
        schema_model=CardDraft,
    )
    data = draft.model_dump() | {"reviewed": False}
    data["id"] = slugify(data["id"])
    data["exercise_tags"] = [t for t in data["exercise_tags"] if t in tags]
    return EvidenceCard.model_validate(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", type=Path, help="specific raw files to (re)ingest")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.nebius_api_key:
        sys.exit("NEBIUS_API_KEY missing in .env")

    out_dir = Path(settings.evidence_dir)
    index_path = out_dir / "_ingested.json"
    index: dict[str, str] = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    reviewed = {c.id for c in load_cards() if c.reviewed}

    sources = args.files or sorted(p for p in RAW_DIR.iterdir() if p.suffix.lower() in {".pdf", ".xml", ".md"})
    todo = [p for p in sources if args.files or p.name not in index]
    tags = allowed_tags()
    print(f"{len(index)} already ingested, {len(todo)} to do with {settings.model_reason}")

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(draft_card, p, tags, settings.model_reason): p for p in todo}
        for future in as_completed(futures):
            path = futures[future]
            try:
                card = future.result()
            except Exception as exc:  # keep going; rerun picks up what failed
                print(f"  ! {path.name}: {exc}")
                continue
            if card.id in reviewed:
                print(f"  = {path.name}: card {card.id} is reviewed, not overwritten")
            else:
                # Two studies can get the same slug; never overwrite a card from another file.
                if card.id in index.values() and index.get(path.name) != card.id:
                    card.id = f"{card.id}-{slugify(path.stem)[:12]}"
                save_card(card, out_dir)
                print(f"  + {path.name} -> {card.id} ({card.evidence_path.value}, {len(card.key_findings)} findings)")
            index[path.name] = card.id
            index_path.write_text(json.dumps(dict(sorted(index.items())), indent=2) + "\n", encoding="utf-8")

    print(f"done: {len(load_cards())} cards in {out_dir}")


if __name__ == "__main__":
    main()
