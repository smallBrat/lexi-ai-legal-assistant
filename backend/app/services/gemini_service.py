"""Gemini API integration for legal document analysis."""

import asyncio
import json
import random
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from google.genai import types
from google.genai.errors import ClientError, ServerError

from app.core.logging import error, info, warning
from app.schemas.analysis_schema import LegalAnalysis
from app.services import gemini_provider
# MODEL_NAME / MODEL_PRIORITY are re-exported for backwards compatibility
# (analysis_service and tests import them from this module).
from app.services.gemini_provider import MODEL_NAME, MODEL_PRIORITY  # noqa: F401
from app.utils.schema_utils import build_gemini_schema

PROMPT_VERSION = "legal-analysis-v3"
PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "legal_analysis.txt"

SANITIZED_ANALYSIS_SCHEMA: dict = build_gemini_schema(LegalAnalysis)

# Per-model retry policy: one retry per model on 503/429/timeout.
# Exponential backoff base (2s, doubling per attempt) plus uniform jitter.
# Model list and retry constants are shared with the provider so analysis
# and chat can never drift apart.
_RETRY_BASE_SECONDS = 2.0
_MAX_ATTEMPTS_PER_MODEL = 2  # initial attempt + one retry
_TIMEOUT_SECONDS = 60.0
_JITTER_MAX = 1.5


@dataclass
class GeminiResult:
    """Successful Gemini response with execution metadata."""

    text: str
    model: str
    latency_ms: float
    retry_count: int
    fallback_used: bool


class GeminiServiceError(Exception):
    """Base exception for Gemini failures."""


class GeminiTimeoutError(GeminiServiceError):
    """Raised when Gemini does not respond before the timeout."""


class ModelUnavailableError(GeminiServiceError):
    """Raised when every model is exhausted by retryable overload errors.

    Carries the failure context the API layer and the persistence layer
    need to return a structured HTTP 503 and to mark the document as
    ``analysis_failed`` without leaking stack traces.
    """

    def __init__(
        self,
        message: str,
        *,
        attempted_models: list[str] | None = None,
        last_model: str | None = None,
        last_status_code: int | None = None,
        failure_reason: str = "unknown",
    ) -> None:
        """Capture overload context alongside the error message."""
        super().__init__(message)
        self.attempted_models: list[str] = list(attempted_models or [])
        self.last_model = last_model
        self.last_status_code = last_status_code
        self.failure_reason = failure_reason
        self.retryable = True


class GeminiInvalidJSONError(GeminiServiceError):
    """Raised when Gemini returns invalid JSON after one retry."""


class GeminiService:
    """Centralize Gemini configuration and document analysis requests."""

    def __init__(self, timeout_seconds: float = _TIMEOUT_SECONDS) -> None:
        """Initialize the Gemini client with a low-temperature JSON config."""
        # Shared singleton from the provider — never `genai.Client(...)` here.
        # Accessed via the module so tests can patch the factory.
        self._client = gemini_provider.get_gemini_client()
        self._timeout_seconds = timeout_seconds

    def _build_system_instruction(self) -> str:
        """Load the shared legal analysis system instruction."""
        try:
            return PROMPT_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            raise GeminiServiceError("Analysis prompt is unavailable") from exc

    def _backoff_with_jitter(self, attempt: int) -> float:
        """Return exponential backoff (base * 2**attempt) plus jitter."""
        return _RETRY_BASE_SECONDS * (2**attempt) + random.uniform(0, _JITTER_MAX)

    async def _generate(
        self, document_text: str, correction: str | None = None
    ) -> GeminiResult:
        """Generate a JSON response from Gemini with multi-model fallback.

        Iterates through ``MODEL_PRIORITY``. Each model is retried once on
        HTTP 503 / 429 / timeout with backoff (2s then 5s + jitter). On a
        second failure the next model is tried. HTTP 400/401/403 errors are
        never retried — they propagate immediately.
        """
        info(
            "Gemini schema prepared",
            schema_top_level_keys=list(SANITIZED_ANALYSIS_SCHEMA.keys()),
        )
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SANITIZED_ANALYSIS_SCHEMA,
            system_instruction=self._build_system_instruction(),
            # We never use tools/function-calling: disable automatic function
            # calling so the SDK skips the AFC path (and its
            # "Direct use of automatic function calling ..." warning).
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )
        contents = document_text if correction is None else [document_text, correction]
        doc_length = len(document_text)

        last_exc: Exception | None = None
        attempted_models: list[str] = []
        last_status_code: int | None = None
        last_reason = "unknown"
        total_retries = 0

        for model_index, model_name in enumerate(MODEL_PRIORITY):
            attempted_models.append(model_name)
            for attempt in range(_MAX_ATTEMPTS_PER_MODEL):  # initial + one retry
                started = perf_counter()
                info(
                    "model_attempt_started",
                    model=model_name,
                    attempt=attempt + 1,
                    doc_length=doc_length,
                )
                try:
                    response = await asyncio.wait_for(
                        self._client.aio.models.generate_content(
                            model=model_name,
                            contents=contents,
                            config=config,
                        ),
                        timeout=self._timeout_seconds,
                    )
                    text = getattr(response, "text", None)
                    if not text:
                        raise GeminiInvalidJSONError("Gemini returned an empty response")
                    latency_ms = round((perf_counter() - started) * 1000, 2)
                    info(
                        "model_success",
                        model=model_name,
                        attempt=attempt + 1,
                        latency_ms=latency_ms,
                        doc_length=doc_length,
                    )
                    return GeminiResult(
                        text=str(text).strip(),
                        model=model_name,
                        latency_ms=latency_ms,
                        retry_count=total_retries,
                        fallback_used=(model_index > 0),
                    )
                except asyncio.TimeoutError as exc:
                    last_exc = exc
                    last_status_code = None
                    last_reason = "timeout"
                    latency_ms = round((perf_counter() - started) * 1000, 2)
                    warning(
                        "model_attempt_failed",
                        model=model_name,
                        attempt=attempt + 1,
                        latency_ms=latency_ms,
                        reason="timeout",
                        status_code=None,
                        exc_type=type(exc).__name__,
                        doc_length=doc_length,
                        exc_repr=repr(exc),
                    )
                    if attempt + 1 < _MAX_ATTEMPTS_PER_MODEL:
                        total_retries += 1
                        await asyncio.sleep(self._backoff_with_jitter(attempt))
                        continue
                    if model_name != MODEL_PRIORITY[-1]:
                        next_model = MODEL_PRIORITY[model_index + 1]
                        info(
                            "model_switched",
                            from_model=model_name,
                            to_model=next_model,
                            reason="timeout",
                            attempt=attempt + 1,
                            latency_ms=latency_ms,
                            status_code=None,
                            exc_type=type(exc).__name__,
                        )
                        break
                    break
                except ServerError as exc:
                    last_exc = exc
                    status_code = getattr(exc, "code", None)
                    status = getattr(exc, "status", None)
                    last_status_code = status_code if isinstance(status_code, int) else None
                    last_reason = "server_error"
                    latency_ms = round((perf_counter() - started) * 1000, 2)
                    warning(
                        "model_attempt_failed",
                        model=model_name,
                        attempt=attempt + 1,
                        latency_ms=latency_ms,
                        reason="server_error",
                        status_code=status_code,
                        status=status,
                        exc_type=type(exc).__name__,
                        doc_length=doc_length,
                        exc_repr=repr(exc),
                    )
                    if status_code == 503 and attempt + 1 < _MAX_ATTEMPTS_PER_MODEL:
                        total_retries += 1
                        await asyncio.sleep(self._backoff_with_jitter(attempt))
                        continue
                    if model_name != MODEL_PRIORITY[-1]:
                        next_model = MODEL_PRIORITY[model_index + 1]
                        info(
                            "model_switched",
                            from_model=model_name,
                            to_model=next_model,
                            reason="server_error",
                            status_code=status_code,
                            attempt=attempt + 1,
                            latency_ms=latency_ms,
                            exc_type=type(exc).__name__,
                        )
                        break
                    break
                except ClientError as exc:
                    last_exc = exc
                    latency_ms = round((perf_counter() - started) * 1000, 2)
                    status_code = getattr(exc, "code", None)
                    if status_code in (400, 401, 403):
                        # Never retried: configuration/credential errors.
                        error_details = {
                            "exc_type": type(exc).__name__,
                            "exc_message": str(exc),
                            "model": model_name,
                            "doc_length": doc_length,
                            "retry_attempt": attempt,
                            "latency_ms": latency_ms,
                            "exc_repr": repr(exc),
                            "status_code": status_code,
                        }
                        if hasattr(exc, "message"):
                            error_details["api_message"] = exc.message
                        error("Gemini API error", **error_details)
                        raise GeminiServiceError("Gemini request failed") from exc
                    last_status_code = status_code if isinstance(status_code, int) else None
                    last_reason = "client_error"
                    warning(
                        "model_attempt_failed",
                        model=model_name,
                        attempt=attempt + 1,
                        latency_ms=latency_ms,
                        reason="client_error",
                        status_code=status_code,
                        exc_type=type(exc).__name__,
                        doc_length=doc_length,
                        exc_repr=repr(exc),
                    )
                    if status_code == 429 and attempt + 1 < _MAX_ATTEMPTS_PER_MODEL:
                        total_retries += 1
                        await asyncio.sleep(self._backoff_with_jitter(attempt))
                        continue
                    if model_name != MODEL_PRIORITY[-1]:
                        next_model = MODEL_PRIORITY[model_index + 1]
                        info(
                            "model_switched",
                            from_model=model_name,
                            to_model=next_model,
                            reason="client_error",
                            status_code=status_code,
                            attempt=attempt + 1,
                            latency_ms=latency_ms,
                            exc_type=type(exc).__name__,
                        )
                        break
                    break
                except Exception as exc:
                    last_exc = exc
                    last_status_code = None
                    last_reason = "unexpected"
                    latency_ms = round((perf_counter() - started) * 1000, 2)
                    error(
                        "model_attempt_failed",
                        model=model_name,
                        attempt=attempt + 1,
                        latency_ms=latency_ms,
                        reason="unexpected",
                        status_code=None,
                        exc_type=type(exc).__name__,
                        doc_length=doc_length,
                        exc_repr=repr(exc),
                    )
                    if model_name != MODEL_PRIORITY[-1]:
                        next_model = MODEL_PRIORITY[model_index + 1]
                        info(
                            "model_switched",
                            from_model=model_name,
                            to_model=next_model,
                            reason="unexpected_error",
                            attempt=attempt + 1,
                            latency_ms=latency_ms,
                            status_code=None,
                            exc_type=type(exc).__name__,
                        )
                        break
                    break

        error(
            "Gemini all models exhausted",
            attempted_models=attempted_models,
            last_status_code=last_status_code,
            retryable=True,
            failure_reason=last_reason,
        )
        raise ModelUnavailableError(
            "Gemini temporarily unavailable after retries: " + ", ".join(attempted_models),
            attempted_models=attempted_models,
            last_model=attempted_models[-1] if attempted_models else None,
            last_status_code=last_status_code,
            failure_reason=last_reason,
        ) from last_exc

    async def analyze_document(
        self, document_text: str, correction: str | None = None
    ) -> GeminiResult:
        """Return the model's JSON response with execution metadata."""
        result = await self._generate(document_text, correction)
        try:
            parsed = json.loads(result.text)
            if not isinstance(parsed, dict):
                raise TypeError("Response is not a JSON object")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise GeminiInvalidJSONError("Gemini returned malformed JSON") from exc
        return result
