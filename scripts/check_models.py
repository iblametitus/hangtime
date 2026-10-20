"""M0 risk check: which Nemotron candidates from docs/SPEC.md section 2 actually work
on this Token Factory account?

For every candidate that appears in GET /v1/models, tries a plain JSON-schema call,
and for vision candidates an additional call with 12 images (the real pipeline sends
12 frames per video, see docs/SPEC.md section 2-3).

Usage: uv run python scripts/check_models.py
Needs NEBIUS_API_KEY in .env. Prints a table; does not write anywhere.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel

from app.config import get_settings
from app.llm import get_client, image_content, timed_call_json_schema

# A 1x1 transparent PNG, used as a stand-in for real video frames: cheap and
# enough to prove the API accepts multiple image parts in one call.
_PLACEHOLDER_PNG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

CANDIDATES = {
    "FAST": [
        "nvidia/Nemotron-3_5-Lightning",
        "nvidia/nemotron-3-nano-30b-a3b",
    ],
    "VISION": [
        "nvidia/Nemotron-3.5-Super-VL",
        "nvidia/nemotron-3-nano-omni",
        "nvidia/nemotron-3-nano-2-vl",
    ],
    "REASON": [
        "nvidia/Nemotron-3-Ultra-550b-a55b",
        "nvidia/nemotron-3-super-120b-a12b",
    ],
}


class _JsonProbe(BaseModel):
    answer: str


class _VisionProbe(BaseModel):
    images_seen: int
    answer: str


def check_json(model: str) -> tuple[bool, float, str]:
    try:
        _, seconds = timed_call_json_schema(
            model=model,
            system_prompt="Reply with a short JSON object.",
            user_content="Set answer to the word 'ok'.",
            schema_model=_JsonProbe,
            max_retries=0,
        )
        return True, seconds, ""
    except Exception as exc:  # noqa: BLE001 - this script reports every failure mode as a row
        return False, 0.0, str(exc)[:120]


def check_vision(model: str) -> tuple[bool, float, str]:
    content = [{"type": "text", "text": "Count the images below, they may be identical."}]
    content += [image_content(_PLACEHOLDER_PNG) for _ in range(12)]
    try:
        _, seconds = timed_call_json_schema(
            model=model,
            system_prompt="Reply with a short JSON object.",
            user_content=content,
            schema_model=_VisionProbe,
            max_retries=0,
        )
        return True, seconds, ""
    except Exception as exc:  # noqa: BLE001
        return False, 0.0, str(exc)[:120]


def main() -> None:
    settings = get_settings()
    if not settings.nebius_api_key:
        print("NEBIUS_API_KEY is empty. Put it in .env (see .env.example) and rerun.")
        sys.exit(1)

    client = get_client()
    try:
        available = {m.id for m in client.models.list().data}
    except Exception as exc:  # noqa: BLE001
        print(f"Could not reach Token Factory / list models: {exc}")
        sys.exit(1)

    print(f"{len(available)} models visible on this account.\n")

    rows: list[tuple[str, str, str, str, str]] = []
    for role, candidates in CANDIDATES.items():
        for model in candidates:
            if model not in available:
                rows.append((role, model, "not on account", "-", "-"))
                continue

            json_ok, json_s, json_err = check_json(model)
            json_cell = "ok" if json_ok else f"FAIL ({json_err})"

            if role == "VISION":
                vision_ok, vision_s, vision_err = check_vision(model)
                vision_cell = "ok" if vision_ok else f"FAIL ({vision_err})"
                latency = f"{json_s:.1f}s / {vision_s:.1f}s"
            else:
                vision_cell = "-"
                latency = f"{json_s:.1f}s"

            rows.append((role, model, json_cell, vision_cell, latency))

    header = ("Role", "Model ID", "JSON ok", "Vision ok", "Latency")
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(header)]
    print(" | ".join(h.ljust(w) for h, w in zip(header, widths)))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(" | ".join(cell.ljust(w) for cell, w in zip(row, widths)))

    print("\nCopy the confirmed model IDs into .env (MODEL_FAST / MODEL_VISION / MODEL_REASON).")


if __name__ == "__main__":
    main()
