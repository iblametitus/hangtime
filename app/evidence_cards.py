"""Evidence cards: one JSON file per study in data/evidence_cards/<id>.json.

Files whose name starts with "_" are bookkeeping (e.g. _ingested.json), not cards.
"""

import json
import os
from pathlib import Path

from app.config import get_settings
from app.models import EvidenceCard


def _dir(directory: Path | None) -> Path:
    return directory or Path(get_settings().evidence_dir)


def load_cards(directory: Path | None = None) -> list[EvidenceCard]:
    d = _dir(directory)
    if not d.exists():
        return []
    return [
        EvidenceCard.model_validate_json(p.read_bytes())
        for p in sorted(d.glob("*.json"))
        if not p.name.startswith("_")
    ]


def save_card(card: EvidenceCard, directory: Path | None = None) -> Path:
    d = _dir(directory)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{card.id}.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(card.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return p
