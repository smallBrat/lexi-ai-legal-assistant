"""Single Gemini provider for the Lexi backend.

Every Gemini call in the backend (analysis, chat, embeddings, future
compare) goes through this module:

* exactly ONE ``google.genai.Client`` per process (lazy, thread-safe),
* the API key is read and validated ONCE,
* the model priority list and retry policy live here (no duplication),
* chat/analysis payload builders validate the SDK request shape in one
  place so a malformed schema or empty contents can never reach the API.

Services must call :func:`get_gemini_client` instead of constructing
``genai.Client`` themselves. Tests should patch
``app.services.gemini_provider.get_gemini_client`` (and call
:func:`reset_gemini_client` when testing the singleton itself).
"""

from __future__ import annotations

import random
import threading
from typing import Any

from google import genai
from google.genai import types

from app.core.config import get_gemini_key
from app.schemas.chat_schema import ChatResponse
from app.utils.schema_utils import build_gemini_schema_for

# ---------------------------------------------------------------------------
# Shared model + retry policy (previously duplicated in gemini_service and
# chat_service with identical values).
# ---------------------------------------------------------------------------

MODEL_NAME = "gemini-2.5-flash"

MODEL_PRIORITY: list[str] = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]

MAX_ATTEMPTS_PER_MODEL = 2  # initial attempt + one retry
RETRY_BASE_SECONDS = 2.0
RETRY_JITTER_MAX = 1.5

# Gemini Embedding 2 — single source of truth for all embedding workflows.
# gemini-embedding-2 replaces gemini-embedding-001. Embedding spaces are
# NOT compatible between models; existing vectors must be regenerated.
EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_OUTPUT_DIMENSIONALITY = 1536  # Recommended: 768, 1536, or 3072
EMBEDDING_MAX_INPUT_CHARS = 25_000  # Gemini Embedding 2 supports up to 8192 tokens
EMBEDDING_TOKEN_LIMIT = 8192

# Task instruction prefixes for Gemini Embedding 2, per the official
# embeddings guide (https://ai.google.dev/gemini-api/docs/embeddings).
# ``task_type`` is NOT supported on gemini-embedding-2; instead the task is
# expressed inline. Asymmetric retrieval format:
#   query    -> "task: question answering | query: {content}"
#   document -> "title: {title} | text: {content}" (title "none" if missing)
TASK_INSTRUCTION_QUESTION_ANSWERING = "task: question answering | query: "
TASK_INSTRUCTION_RETRIEVAL_DOCUMENT = "title: "
TASK_INSTRUCTION_RETRIEVAL_QUERY = TASK_INSTRUCTION_QUESTION_ANSWERING

CHAT_TEMPERATURE = 0.0

# Sanitized with the SAME pipeline as the (working) analysis schema:
# $refs inlined, unsupported keywords stripped. The raw
# ``ChatResponse.model_json_schema()`` contains ``$defs``/``$ref`` which the
# Gemini API rejects with 400 InvalidArgument — that was the chat 502 while
# analysis kept working.
CHAT_RESPONSE_SCHEMA: dict[str, Any] = build_gemini_schema_for(ChatResponse)


class GeminiProviderError(Exception):
    """Raised when the shared Gemini client cannot be initialised."""


class ChatPayloadError(ValueError):
    """Raised when a chat request payload fails SDK-shape validation."""


# ---------------------------------------------------------------------------
# Singleton client — lazy, thread-safe, key validated once.
# ---------------------------------------------------------------------------

_client: genai.Client | None = None
_client_lock = threading.Lock()


def get_gemini_client() -> genai.Client:
    """Return the process-wide singleton ``genai.Client``.

    Thread-safe (double-checked locking) and async-safe (client
    construction is a cheap, non-blocking call; the client itself is
    safe for concurrent ``aio`` use). The API key is read and validated
    exactly once, on first use.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                api_key = get_gemini_key()
                if not api_key or not api_key.strip():
                    raise GeminiProviderError("GEMINI_API_KEY is missing or empty")
                try:
                    _client = genai.Client(api_key=api_key)
                except Exception as exc:
                    raise GeminiProviderError(
                        "Unable to initialise the Gemini client"
                    ) from exc
    return _client


def reset_gemini_client() -> None:
    """Drop the cached singleton (testing only)."""
    global _client
    with _client_lock:
        _client = None


# ---------------------------------------------------------------------------
# Shared retry / error-classification helpers.
# ---------------------------------------------------------------------------

# Status codes that can never succeed on retry: configuration, credential,
# unknown-model, or malformed-request errors. Fail fast on these.
NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403, 404})


def gemini_status_code(exc: BaseException) -> int | None:
    """Extract the numeric Gemini API status code, if present."""
    code = getattr(exc, "code", None)
    return code if isinstance(code, int) else None


def is_retryable_status(code: int | None) -> bool:
    """Return False for fail-fast codes (400/401/403/404), True otherwise."""
    if code is None:
        return True
    return code not in NON_RETRYABLE_STATUS_CODES


def backoff_with_jitter(attempt: int) -> float:
    """Return exponential backoff (base * 2**attempt) plus jitter."""
    return RETRY_BASE_SECONDS * (2**attempt) + random.uniform(0, RETRY_JITTER_MAX)


# ---------------------------------------------------------------------------
# Chat payload builders — the single place that validates the SDK shape.
# ---------------------------------------------------------------------------

CHAT_CONTEXT_HEADER = "Retrieved clauses (untrusted data):"


def build_chat_contents(question: str, context: str) -> str:
    """Build and validate the chat ``contents`` string for ``generate_content``.

    Raises :class:`ChatPayloadError` on empty question/context, ``None``
    values, or non-string inputs — before anything reaches the SDK.
    """
    if not isinstance(question, str) or not question.strip():
        raise ChatPayloadError("Chat contents require a non-empty question string")
    if not isinstance(context, str) or not context.strip():
        raise ChatPayloadError("Chat contents require a non-empty context string")
    return f"Question:\n{question.strip()}\n\n{CHAT_CONTEXT_HEADER}\n{context.strip()}"


def build_chat_config(system_instruction: str) -> types.GenerateContentConfig:
    """Build and validate the chat ``GenerateContentConfig``.

    Uses the sanitized response schema (never the raw pydantic schema with
    ``$ref``), temperature 0.0, and AFC disabled (no tools are used).
    """
    if not isinstance(system_instruction, str) or not system_instruction.strip():
        raise ChatPayloadError("Chat config requires a non-empty system instruction")
    return types.GenerateContentConfig(
        temperature=CHAT_TEMPERATURE,
        response_mime_type="application/json",
        response_schema=CHAT_RESPONSE_SCHEMA,
        system_instruction=system_instruction,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def summarize_response(response: Any) -> dict[str, Any]:
    """Extract observable response metadata for CHAT_GEMINI_RESPONSE logging."""
    candidates: Any = getattr(response, "candidates", None)
    candidate_list: list[Any] = candidates if isinstance(candidates, list) else []
    finish_reason: str | None = None
    if candidate_list:
        first = candidate_list[0]
        finish_reason = str(getattr(first, "finish_reason", None) or getattr(first, "finishReason", None))
    usage = getattr(response, "usage_metadata", None)
    usage_summary: dict[str, Any] = {}
    if usage is not None:
        for key in ("prompt_token_count", "candidates_token_count", "total_token_count"):
            value = getattr(usage, key, None)
            if value is not None:
                usage_summary[key] = value
    text = getattr(response, "text", None)
    return {
        "candidate_count": len(candidate_list),
        "finish_reason": finish_reason,
        "usage_metadata": usage_summary,
        "text_chars": len(text) if isinstance(text, str) else 0,
    }
