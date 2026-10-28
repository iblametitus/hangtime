"""Describe the movement from 8 full-res frames. Pure observation, no judgement."""

from app.config import get_settings
from app.llm import call_json_schema, image_content
from app.models import VideoUnderstanding
from app.pipeline.video import to_data_uri

UNDERSTAND_PROMPT = (
    "You see 8 frames from a short fitness video in order. Describe the movement precisely (start "
    "position, action, landing, tempo, ground contact time if visible). Transcribe all on-screen text "
    "exactly. List equipment. Do not judge the exercise."
)


def merge_text(*groups: list[str]) -> list[str]:
    """Merge on-screen text from several passes, keeping order, dropping case-insensitive duplicates."""
    seen: set[str] = set()
    out = []
    for group in groups:
        for line in group:
            key = " ".join(line.split()).lower()
            if key and key not in seen:
                seen.add(key)
                out.append(line.strip())
    return out


def understand(frames: list[bytes], scan_text: list[str] | None = None) -> VideoUnderstanding:
    content = [{"type": "text", "text": "Frames in order:"}] + [image_content(to_data_uri(f)) for f in frames]
    result = call_json_schema(
        model=get_settings().model_vision,
        system_prompt=UNDERSTAND_PROMPT,
        user_content=content,
        schema_model=VideoUnderstanding,
    )
    # Text from the intro (found by the coarse scan) must survive even if the window cut it off.
    result.on_screen_text = merge_text(scan_text or [], result.on_screen_text)
    return result
