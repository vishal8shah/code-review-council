"""Shared LiteLLM JSON transport helpers with portability fallback."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import litellm

from .schemas import ChairVerdict, OutputMode, OwnerPresentation, ReviewerOutput


@dataclass(slots=True)
class JSONCompletionResult:
    """Raw JSON-like completion payload plus transport metadata."""

    raw_content: str
    tokens_used: int
    output_mode: OutputMode


_RESPONSE_FORMAT_NATIVE_PREFIXES = (
    "openai/",
    "anthropic/",
    "gpt-",
    "o1",
    "o3",
    "o4",
    "claude-",
)

_RESPONSE_FORMAT_FALLBACK_PREFIXES = (
    "google/",
    "gemini",
    "vertex",
    "groq/",
    "mistral/",
    "ollama/",
    "bedrock/",
    "huggingface/",
    "together_ai/",
    "together/",
    "fireworks/",
    "xai/",
    "deepseek/",
)

_RESPONSE_FORMAT_UNSUPPORTED_MARKERS = (
    "response_format",
    "json_object",
    "json mode",
    "json schema",
    "json_schema",
)

_RESPONSE_FORMAT_REJECTION_MARKERS = (
    "not supported",
    "unsupported",
    "unknown parameter",
    "unrecognized request argument",
    "extra_forbidden",
    "invalid parameter",
    "unsupported parameter",
    "not enabled",
    "not allowed",
)

_STRING_DELIMITERS = {"'", '"', "`"}
# Fence tokens for code-block extraction. Two are intentional:
#   1. Real triple-backticks emitted by most models.
#   2. "[TRIPLE_BACKTICK]" sentinel used by templates/models that escape
#      backticks as a literal placeholder. Both paths are covered by tests
#      in tests/test_llm_transport.py. Do NOT remove either without breaking
#      a supported output format.
_FENCE_TOKENS = ("```", "[TRIPLE_BACKTICK]")


def classify_model_json_support(model: str) -> str:
    """Heuristically classify a model's likely JSON transport support."""
    normalized = (model or "").strip().lower()
    if not normalized:
        return "unknown"

    if normalized.startswith(_RESPONSE_FORMAT_NATIVE_PREFIXES):
        return "native"

    if normalized.startswith(_RESPONSE_FORMAT_FALLBACK_PREFIXES) or "gemini" in normalized:
        return "fallback_likely"

    return "unknown"


def provider_env_var_for_model(model: str) -> str | None:
    """Return the most likely API key env var for a configured model string."""
    normalized = (model or "").strip().lower()
    if not normalized:
        return None

    if normalized.startswith(("openai/", "gpt-", "o1", "o3", "o4")):
        return "OPENAI_API_KEY"
    if normalized.startswith(("anthropic/", "claude-")):
        return "ANTHROPIC_API_KEY"
    if normalized.startswith(("google/", "gemini")) or "gemini" in normalized:
        return "GOOGLE_API_KEY"
    return None


def is_response_format_unsupported_error(exc: Exception) -> bool:
    """Return True when an exception looks like a JSON-mode capability rejection."""
    text = str(exc).strip().lower()
    if not text:
        return False

    has_format_marker = any(marker in text for marker in _RESPONSE_FORMAT_UNSUPPORTED_MARKERS)
    has_rejection_marker = any(marker in text for marker in _RESPONSE_FORMAT_REJECTION_MARKERS)
    return has_format_marker and has_rejection_marker


def extract_json_object(text: str) -> str | None:
    """Best-effort extraction of the first balanced JSON object."""
    if not text:
        return None

    candidate = text.strip()

    def _scan_for_object(payload: str) -> str | None:
        start = payload.find("{")
        if start == -1:
            return None

        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(payload)):
            ch = payload[idx]

            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue

            if ch == "{":
                depth += 1
                continue

            if ch == "}":
                depth -= 1
                if depth == 0:
                    return payload[start : idx + 1]
        return None

    for fence in _FENCE_TOKENS:
        if fence not in candidate:
            continue

        parts = candidate.split(fence)
        for block in parts[1::2]:
            cleaned = block.strip()
            if not cleaned:
                continue
            lines = cleaned.splitlines()
            if lines and lines[0].strip().lower() in {"json", "javascript", "js"}:
                cleaned = "\n".join(lines[1:]).strip()
            extracted = _scan_for_object(cleaned)
            if extracted:
                return extracted

    return _scan_for_object(candidate)


def load_json_object(raw_json: str) -> dict[str, Any] | None:
    """Parse model JSON with fallback for fenced or wrapped payloads."""
    try:
        data = json.loads(raw_json)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass

    extracted = extract_json_object(raw_json)
    if not extracted:
        return None

    try:
        data = json.loads(extracted)
    except json.JSONDecodeError:
        return None

    return data if isinstance(data, dict) else None


def collect_transport_notes(
    verdict: ChairVerdict,
    reviewer_outputs: list[ReviewerOutput] | None = None,
) -> list[str]:
    """Return user-facing transport notes only when fallback or failure occurred."""
    notes: list[str] = []

    for reviewer in reviewer_outputs or []:
        if reviewer.output_mode == "prompt_json_fallback":
            notes.append(
                f"Reviewer `{reviewer.reviewer_id}` used prompt-only JSON fallback after JSON mode was rejected."
            )
        elif reviewer.output_mode == "failed":
            notes.append(
                f"Reviewer `{reviewer.reviewer_id}` transport failed."
            )

    if verdict.chair_output_mode == "prompt_json_fallback":
        notes.append("Chair synthesis used prompt-only JSON fallback after JSON mode was rejected.")
    elif verdict.chair_output_mode == "failed":
        notes.append("Chair synthesis transport failed and the review failed closed.")

    owner_presentation: OwnerPresentation | None = verdict.owner_presentation
    if owner_presentation is not None:
        if owner_presentation.output_mode == "prompt_json_fallback":
            notes.append("Owner presentation used prompt-only JSON fallback after JSON mode was rejected.")
        elif owner_presentation.output_mode == "failed":
            notes.append("Owner presentation used deterministic fallback because the translation transport or JSON parsing failed.")

    return notes


def output_mode_label(mode: OutputMode | None) -> str:
    """Return a short user-facing label for a transport mode."""
    if mode == "response_format":
        return "native_json"
    if mode == "prompt_json_fallback":
        return "prompt_json_fallback"
    if mode == "failed":
        return "failed"
    return ""


def _extract_message_content(response: Any) -> str:
    """Return string content from the first LiteLLM choice."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        return "{}"

    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)

    if isinstance(content, str):
        return content or "{}"

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts) or "{}"

    return "{}"


def _extract_total_tokens(response: Any) -> int:
    """Return total token usage from a LiteLLM response when available."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0

    total = getattr(usage, "total_tokens", None)
    if isinstance(total, int):
        return total

    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if isinstance(total, int):
            return total

    return 0


async def invoke_json_completion(
    *,
    model: str,
    messages: list[dict[str, str]],
    timeout: float,
    temperature: float,
    num_retries: int = 2,
    acompletion_func: Any | None = None,
) -> JSONCompletionResult:
    """Call LiteLLM with native JSON mode first, then fallback when unsupported."""
    completion_func = acompletion_func or litellm.acompletion
    request_kwargs = {
        "model": model,
        "messages": messages,
        "timeout": timeout,
        "temperature": temperature,
        "num_retries": num_retries,
    }

    try:
        response = await completion_func(
            **request_kwargs,
            response_format={"type": "json_object"},
        )
        return JSONCompletionResult(
            raw_content=_extract_message_content(response),
            tokens_used=_extract_total_tokens(response),
            output_mode="response_format",
        )
    except Exception as exc:
        if not is_response_format_unsupported_error(exc):
            raise

    response = await completion_func(**request_kwargs)
    return JSONCompletionResult(
        raw_content=_extract_message_content(response),
        tokens_used=_extract_total_tokens(response),
        output_mode="prompt_json_fallback",
    )
