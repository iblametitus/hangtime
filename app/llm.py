"""Token Factory client: JSON-schema structured calls with one retry on validation failure.

Every LLM call in the pipeline goes through call_json_schema() so there is exactly
one place that talks to Token Factory, one retry policy, and one schema-validation path.
"""

import json
import logging
import time
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = OpenAI(base_url=settings.token_factory_base_url, api_key=settings.nebius_api_key)
    return _client


def image_content(image_url_or_data_uri: str) -> dict:
    """One image part for a vision message content list. Accepts an http(s) URL or a data: URI."""
    return {"type": "image_url", "image_url": {"url": image_url_or_data_uri}}


def _response_format(schema_model: type[T]) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_model.__name__,
            "schema": schema_model.model_json_schema(),
            "strict": True,
        },
    }


def call_json_schema(
    *,
    model: str,
    system_prompt: str,
    user_content: str | list[dict],
    schema_model: type[T],
    max_retries: int = 1,
    temperature: float = 0.2,
    thinking: bool = True,
) -> T:
    """Call Token Factory and return a validated instance of schema_model.

    thinking=False switches off the model's reasoning trace. Use it for simple extraction steps:
    Nemotron Lightning wrote ~3,000 reasoning tokens (27-94 s) for a 70-token answer, and
    answered the same in ~1 s without (test 28.10.).

    On a schema-validation failure, retries once by feeding the broken output
    and the error back to the model and asking for a corrected JSON object.
    Raises pydantic.ValidationError if every attempt fails.
    """
    client = get_client()
    schema_json = json.dumps(schema_model.model_json_schema())
    messages: list[dict] = [
        {
            "role": "system",
            "content": f"{system_prompt}\n\nRespond with JSON matching this schema:\n{schema_json}",
        },
        {"role": "user", "content": user_content},
    ]

    last_error: ValidationError | None = None
    for attempt in range(max_retries + 1):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            response_format=_response_format(schema_model),
            **({} if thinking else {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}),
        )
        raw = response.choices[0].message.content
        if not raw:
            # Empty content (seen with reasoning models): nothing to correct, so just ask again.
            logger.warning(
                "Empty response from %s (attempt %d/%d, finish_reason=%s)",
                model,
                attempt + 1,
                max_retries + 1,
                response.choices[0].finish_reason,
            )
            last_error = ValidationError.from_exception_data(
                schema_model.__name__,
                [{"type": "missing", "loc": ("response",), "input": None}],
            )
            continue
        try:
            return schema_model.model_validate_json(raw)
        except ValidationError as exc:
            last_error = exc
            logger.warning(
                "Schema validation failed for %s (attempt %d/%d): %s",
                model,
                attempt + 1,
                max_retries + 1,
                exc,
            )
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": f"That response did not match the schema: {exc}. Return corrected JSON only.",
                }
            )

    assert last_error is not None
    raise last_error


def timed_call_json_schema(**kwargs) -> tuple[T, float]:
    """Same as call_json_schema but also returns wall-clock seconds. Used by scripts/check_models.py."""
    start = time.monotonic()
    result = call_json_schema(**kwargs)
    return result, time.monotonic() - start
