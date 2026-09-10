"""The single place aiops talks to Claude.

Three things every call gets, because they are what make an LLM safe to put in
a deploy path:

  * structured output -- the model fills a JSON Schema derived from a Pydantic
    model, so a malformed answer is a validation error rather than a surprise
    downstream;
  * refusal handling -- Claude Opus 5 runs safety classifiers, and log/metric
    analysis sits close enough to security content to trip a false positive.
    A refusal is a normal HTTP 200, so it is checked explicitly and surfaced as
    a typed failure. Server-side fallbacks re-serve a declined request on
    another model inside the same call;
  * a hard failure mode -- LlmUnavailable. Callers are expected to catch it and
    continue deterministically. No stage of this pipeline blocks on the API
    being reachable.
"""

import json
import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from aiops.config import Settings

log = logging.getLogger("aiops.llm")

T = TypeVar("T", bound=BaseModel)


class LlmUnavailable(RuntimeError):
    """The model could not be consulted, or answered unusably.

    Always recoverable: every caller has a deterministic fallback.
    """


class LlmClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self._client = None

    @property
    def available(self) -> bool:
        return not self.settings.offline

    def _ensure_client(self):
        if self._client is None:
            if self.settings.offline:
                raise LlmUnavailable("aiops is running offline (no ANTHROPIC_API_KEY)")
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - dependency is declared
                raise LlmUnavailable(f"anthropic SDK not installed: {exc}") from exc
            self._client = anthropic.Anthropic(api_key=self.settings.api_key)
        return self._client

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema_model: type[T],
        effort: str | None = None,
    ) -> T:
        """One request, one validated object of type `schema_model`."""
        client = self._ensure_client()

        try:
            response = client.beta.messages.create(
                model=self.settings.model,
                max_tokens=self.settings.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"},
                output_config={
                    "effort": effort or self.settings.effort,
                    "format": {
                        "type": "json_schema",
                        "schema": _strict_schema(schema_model),
                    },
                },
                # A policy decline is re-served by Anthropic's recommended
                # fallback model inside this same call, so a false-positive
                # classifier hit does not fail the pipeline stage.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except Exception as exc:  # noqa: BLE001 - any transport/API error is recoverable here
            raise LlmUnavailable(f"{type(exc).__name__}: {exc}") from exc

        # A refusal is HTTP 200 with an empty or partial body: check before
        # touching content.
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise LlmUnavailable(f"request declined by safety classifiers (category={category})")

        text = "".join(block.text for block in response.content if block.type == "text")
        if not text.strip():
            raise LlmUnavailable(f"empty response (stop_reason={response.stop_reason})")

        try:
            return schema_model.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LlmUnavailable(f"response failed schema validation: {exc}") from exc


def _strict_schema(model: type[BaseModel]) -> dict:
    """Pydantic JSON Schema, adjusted for the structured-outputs subset.

    The API requires `additionalProperties: false` on every object and does not
    accept numeric or string length constraints, so those are stripped here.
    Pydantic still enforces them when the response is validated -- the
    constraints move from generation-time to validation-time, they are not lost.
    """
    schema = model.model_json_schema()
    _harden(schema)
    return schema


_UNSUPPORTED_KEYWORDS = (
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "pattern",
    "format",
)


def _harden(node: object) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object":
            node["additionalProperties"] = False
            if "properties" in node:
                # Structured outputs require every property to be required;
                # optional fields keep their Pydantic defaults after validation.
                node["required"] = sorted(node["properties"].keys())
        for keyword in _UNSUPPORTED_KEYWORDS:
            node.pop(keyword, None)
        for value in node.values():
            _harden(value)
    elif isinstance(node, list):
        for value in node:
            _harden(value)
