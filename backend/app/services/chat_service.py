"""Document-grounded chat orchestration for Lexi."""

import asyncio
import json
import random
import traceback
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

from google.genai.errors import ClientError, ServerError
from pydantic import ValidationError

from app.core.logging import error, info, warning
from app.repositories.chat_repository import ChatRepository, ChatRepositoryError
from app.schemas.chat_schema import ChatResponse, Citation
from app.services import gemini_provider
from app.services.embedding_service import ClauseMatch
from app.services.gemini_provider import (
    CHAT_TEMPERATURE,
    MODEL_PRIORITY,
    build_chat_config,
    build_chat_contents,
    gemini_status_code,
    is_retryable_status,
    summarize_response,
)
from app.services.retrieval_service import RetrievalService, RetrievalServiceError

CHAT_PROMPT_VERSION = "chat-system-v1"
CHAT_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "chat_system.txt"
MIN_SIMILARITY = 0.35

# Timeout/retry policy mirrors `gemini_service` (analyze path) so chat has
# the same overload resilience. Per-attempt Gemini budget is 120s to match
# the frontend CHAT_REQUEST_TIMEOUT_MS=120_000 (PART 5).
CHAT_GEMINI_TIMEOUT_SECONDS = 120.0
_MAX_ATTEMPTS_PER_MODEL = 2  # initial attempt + one retry
# Mutable aliases kept in this namespace: the retry tests tune them via
# monkeypatch to eliminate backoff sleeps.
_RETRY_BASE_SECONDS = 2.0
_JITTER_MAX = 1.5


class ChatServiceError(Exception):
    """Base exception for chat workflow failures."""


class ChatDocumentNotFoundError(ChatServiceError):
    """Raised when a document cannot be found for the authenticated user."""


class ChatForbiddenError(ChatServiceError):
    """Raised when a document belongs to another user."""


class ChatEmptyQuestionError(ChatServiceError):
    """Raised when a question is empty after trimming."""


class ChatGeminiError(ChatServiceError):
    """Raised when Gemini returns an unusable response.

    ``retryable`` is False for fail-fast configuration/credential errors
    (400/401/403/404) and True for transient upstream failures.
    """

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        """Capture the message and whether the caller should retry."""
        super().__init__(message)
        self.retryable = retryable


class ChatTimeoutError(ChatServiceError):
    """Raised when every Gemini attempt times out (maps to HTTP 504)."""


class ChatPersistenceError(ChatServiceError):
    """Raised when chat history cannot be persisted."""


class ChatService:
    """Coordinate ownership, retrieval, Gemini generation, and history."""

    def __init__(self, repository: ChatRepository, retrieval: RetrievalService) -> None:
        """Initialize the service with repository and retrieval boundaries."""
        self._repository = repository
        self._retrieval = retrieval
        # Single shared client from the provider — never `genai.Client(...)`
        # here (that duplication caused per-service key/model drift).
        # Accessed via the module so tests can patch the factory.
        self._gemini = gemini_provider.get_gemini_client()

    @staticmethod
    def _confidence(matches: list[ClauseMatch], citations: list[Citation]) -> int:
        """Compute confidence from retrieval similarity and citation coverage."""
        if not matches:
            return 0
        similarity = sum(match.similarity_score for match in matches) / len(matches)
        coverage = min(1.0, len(citations) / len(matches))
        return max(0, min(100, round((similarity * 0.6 + coverage * 0.4) * 100)))

    @staticmethod
    def _fallback_answer() -> ChatResponse:
        """Return a deterministic answer when no clause is relevant."""
        return ChatResponse(
            answer="This is not found in the uploaded document.",
            confidence_score=0,
            citations=[],
            follow_up_questions=[],
        )

    @staticmethod
    def _fallback_matches(analysis: dict[str, Any] | None) -> list[ClauseMatch]:
        """Build OCR-derived context when vector retrieval returns nothing.

        Uses the stored analysis (summary + clause excerpts — both derived
        from the document's OCR text) so Gemini can still answer instead of
        being skipped. Returns [] only when there is genuinely no context.
        """
        data = analysis or {}
        clauses = list(data.get("clauses") or [])[:5]
        matches: list[ClauseMatch] = []
        for clause in clauses:
            if isinstance(clause, dict):
                title = str(clause.get("title") or "Clause")
                excerpt = str(clause.get("original_text") or clause.get("excerpt") or "").strip()
                page_raw = clause.get("page_number")
            else:  # pydantic ClauseAnalysis or similar
                title = str(getattr(clause, "title", None) or "Clause")
                excerpt = str(
                    getattr(clause, "original_text", None)
                    or getattr(clause, "excerpt", None)
                    or ""
                ).strip()
                page_raw = getattr(clause, "page_number", None)
            if not excerpt:
                continue
            try:
                page_number = int(str(page_raw)) if page_raw not in (None, "") else None
            except (TypeError, ValueError):
                page_number = None
            matches.append(
                ClauseMatch(
                    title=title,
                    excerpt=excerpt,
                    page_number=page_number,
                    similarity_score=0.5,
                )
            )
        if not matches:
            summary = str(
                data.get("summary") or data.get("plain_english_summary") or ""
            ).strip()
            if summary:
                matches.append(
                    ClauseMatch(
                        title="Document summary",
                        excerpt=summary,
                        page_number=None,
                        similarity_score=0.5,
                    )
                )
        return matches

    def _system_instruction(self) -> str:
        """Load the chat system instruction from the shared prompt file."""
        try:
            return CHAT_PROMPT_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            raise ChatGeminiError("Chat prompt is unavailable") from exc

    def _backoff_with_jitter(self, attempt: int) -> float:
        """Return exponential backoff (base * 2**attempt) plus jitter."""
        return _RETRY_BASE_SECONDS * (2**attempt) + random.uniform(0, _JITTER_MAX)

    async def _save_history(
        self, document_id: UUID, user_id: str, question: str, result: ChatResponse
    ) -> bool:
        """Persist one exchange; return True only when the write succeeded.

        Persistence never blocks the answer, but callers must not log
        CHAT_RESPONSE_SENT unless this returns True — otherwise GET history
        would miss an exchange we claimed was sent.
        """
        info("CHAT_SAVE_HISTORY_START", user_id=user_id, document_id=str(document_id))
        try:
            await asyncio.to_thread(
                self._repository.save_message,
                document_id,
                user_id,
                question,
                result.model_dump(mode="json"),
                datetime.now(timezone.utc),
            )
        except ChatRepositoryError as exc:
            warning(
                "CHAT_PERSISTENCE_FAILED",
                user_id=user_id,
                document_id=str(document_id),
                error=str(exc),
            )
            return False
        info("CHAT_SAVE_HISTORY_DONE", user_id=user_id, document_id=str(document_id))
        return True

    def _log_response_sent(
        self, document_id: UUID, user_id: str, result: ChatResponse, started: float
    ) -> None:
        """Log CHAT_RESPONSE_SENT for a validated, persisted answer only."""
        latency_ms = round((perf_counter() - started) * 1000, 2)
        info(
            "CHAT_RESPONSE_SENT",
            user_id=user_id,
            document_id=str(document_id),
            citations=len(result.citations),
            latency_ms=latency_ms,
        )

    async def _generate_once(self, model_name: str, question: str, context: str) -> ChatResponse:
        """Run one bounded Gemini attempt and validate the structured answer.

        The request payload is built (and validated) by the shared provider:
        non-empty question/context, non-empty system instruction, and the
        SANITIZED response schema — never the raw pydantic schema whose
        ``$ref`` entries the Gemini API rejects with 400.
        """
        contents = build_chat_contents(question, context)
        system_instruction = self._system_instruction()
        config = build_chat_config(system_instruction)
        info(
            "CHAT_GEMINI_REQUEST",
            model=model_name,
            temperature=CHAT_TEMPERATURE,
            max_output_tokens=getattr(config, "max_output_tokens", None),
            system_instruction_present=bool(system_instruction.strip()),
            context_chars=len(context),
            question_chars=len(question),
            history_length=0,
        )
        try:
            response = await asyncio.wait_for(
                self._gemini.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                ),
                timeout=CHAT_GEMINI_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            error(
                "CHAT_GEMINI_REQUEST_FAILED",
                model=model_name,
                exc_type=type(exc).__name__,
                exc_message=str(exc),
                gemini_status_code=gemini_status_code(exc),
                traceback=traceback.format_exc(),
            )
            raise
        info("CHAT_GEMINI_RESPONSE", model=model_name, **summarize_response(response))
        raw = getattr(response, "text", None)
        if not raw:
            raise ChatGeminiError("Gemini returned an empty response")
        try:
            return ChatResponse.model_validate_json(str(raw))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            raise ChatGeminiError("Gemini returned malformed chat JSON") from exc

    async def _generate(
        self, question: str, matches: list[ClauseMatch]
    ) -> ChatResponse:
        """Generate a validated Gemini answer with timeout + model fallback.

        Same policy as the analyze path: iterate MODEL_PRIORITY, retrying
        once per model on timeout / 503 / 429 with backoff. 400/401/403/404
        fail fast as non-retryable (retrying those can never succeed), as do
        empty/malformed payloads. If every attempt times out, raises
        ChatTimeoutError (HTTP 504) instead of a generic 502.
        """
        context = json.dumps(
            [
                {
                    "clause_title": match.title,
                    "excerpt": match.excerpt,
                    "page_number": match.page_number,
                    "similarity_score": round(match.similarity_score, 4),
                }
                for match in matches
            ],
            ensure_ascii=False,
        )
        last_exc: Exception | None = None
        timeout_count = 0
        total_attempts = 0
        for model_index, model_name in enumerate(MODEL_PRIORITY):
            for attempt in range(_MAX_ATTEMPTS_PER_MODEL):
                started = perf_counter()
                total_attempts += 1
                info(
                    "CHAT_GEMINI_START",
                    model=model_name,
                    attempt=attempt + 1,
                    question_length=len(question),
                    context_clauses=len(matches),
                )
                try:
                    result = await self._generate_once(model_name, question, context)
                    latency_ms = round((perf_counter() - started) * 1000, 2)
                    info(
                        "CHAT_GEMINI_SUCCESS",
                        model=model_name,
                        attempt=attempt + 1,
                        latency_ms=latency_ms,
                    )
                    return result
                except asyncio.TimeoutError as exc:
                    last_exc = exc
                    timeout_count += 1
                    latency_ms = round((perf_counter() - started) * 1000, 2)
                    warning(
                        "chat_model_attempt_failed",
                        model=model_name,
                        attempt=attempt + 1,
                        latency_ms=latency_ms,
                        reason="timeout",
                    )
                    if attempt + 1 < _MAX_ATTEMPTS_PER_MODEL:
                        await asyncio.sleep(self._backoff_with_jitter(attempt))
                        continue
                    if model_name != MODEL_PRIORITY[-1]:
                        info("chat_model_switched", from_model=model_name, reason="timeout")
                        break
                    break
                except ServerError as exc:
                    last_exc = exc
                    status_code = gemini_status_code(exc)
                    latency_ms = round((perf_counter() - started) * 1000, 2)
                    warning(
                        "chat_model_attempt_failed",
                        model=model_name,
                        attempt=attempt + 1,
                        latency_ms=latency_ms,
                        reason="server_error",
                        status_code=status_code,
                    )
                    if status_code == 503 and attempt + 1 < _MAX_ATTEMPTS_PER_MODEL:
                        await asyncio.sleep(self._backoff_with_jitter(attempt))
                        continue
                    if model_name != MODEL_PRIORITY[-1]:
                        info("chat_model_switched", from_model=model_name, reason="server_error")
                        break
                    break
                except ClientError as exc:
                    status_code = gemini_status_code(exc)
                    if not is_retryable_status(status_code):
                        error(
                            "chat_gemini_client_error",
                            status_code=status_code,
                            model=model_name,
                            retryable=False,
                        )
                        raise ChatGeminiError(
                            "Gemini chat request failed", retryable=False
                        ) from exc
                    last_exc = exc
                    latency_ms = round((perf_counter() - started) * 1000, 2)
                    warning(
                        "chat_model_attempt_failed",
                        model=model_name,
                        attempt=attempt + 1,
                        latency_ms=latency_ms,
                        reason="client_error",
                        status_code=status_code,
                    )
                    if status_code == 429 and attempt + 1 < _MAX_ATTEMPTS_PER_MODEL:
                        await asyncio.sleep(self._backoff_with_jitter(attempt))
                        continue
                    if model_name != MODEL_PRIORITY[-1]:
                        info("chat_model_switched", from_model=model_name, reason="client_error")
                        break
                    break
                except ChatGeminiError:
                    # Empty/malformed payload: deterministic failure, no retry.
                    raise
                except Exception as exc:
                    last_exc = exc
                    latency_ms = round((perf_counter() - started) * 1000, 2)
                    error(
                        "chat_model_attempt_failed",
                        model=model_name,
                        attempt=attempt + 1,
                        latency_ms=latency_ms,
                        reason="unexpected",
                        exc_type=type(exc).__name__,
                    )
                    if model_name != MODEL_PRIORITY[-1]:
                        info("chat_model_switched", from_model=model_name, reason="unexpected_error")
                        break
                    break
        if total_attempts > 0 and timeout_count == total_attempts and last_exc is not None:
            raise ChatTimeoutError("Gemini chat request timed out") from last_exc
        raise ChatGeminiError("Gemini chat request failed") from last_exc

    async def answer(
        self, document_id: UUID, user_id: str, question: str
    ) -> ChatResponse:
        """Answer a question using only relevant clauses from an owned document.

        Every major stage is bracketed by structured log markers so
        production logs show exactly where a stall or failure occurs.
        """
        started = perf_counter()
        question = question.strip()
        if not question:
            raise ChatEmptyQuestionError("Question cannot be empty")

        # ---- Stage: Document Fetch ----
        info("CHAT_DOCUMENT_FETCH_START", user_id=user_id, document_id=str(document_id))
        try:
            document = await asyncio.to_thread(
                self._repository.get_document, document_id, user_id
            )
        except Exception as exc:
            error(
                "CHAT_STAGE_FAILED",
                stage="document_fetch",
                document_id=str(document_id),
                user_id=user_id,
                exc_type=type(exc).__name__,
                exc_message=str(exc),
                traceback=traceback.format_exc(),
            )
            raise
        if document is None:
            raise ChatDocumentNotFoundError("Document not found")
        if str(document.get("user_id")) != user_id:
            raise ChatForbiddenError("Document access denied")
        info("CHAT_DOCUMENT_FETCH_DONE", user_id=user_id, document_id=str(document_id))

        # ---- Stage: Retrieval (index + vector search) ----
        info("CHAT_ANALYSIS_FETCH_START", user_id=user_id, document_id=str(document_id))
        try:
            matches = await self._retrieval.retrieve(
                user_id, document_id, document.get("analysis"), question
            )
        except RetrievalServiceError as exc:
            error(
                "CHAT_STAGE_FAILED",
                stage="retrieval",
                document_id=str(document_id),
                user_id=user_id,
                exc_type=type(exc).__name__,
                exc_message=str(exc),
                traceback=traceback.format_exc(),
            )
            raise ChatServiceError("Retrieval is unavailable") from exc
        except Exception as exc:
            error(
                "CHAT_STAGE_FAILED",
                stage="retrieval",
                document_id=str(document_id),
                user_id=user_id,
                exc_type=type(exc).__name__,
                exc_message=str(exc),
                traceback=traceback.format_exc(),
            )
            raise
        info("CHAT_ANALYSIS_FETCH_DONE", user_id=user_id, document_id=str(document_id), matches_found=len(matches))
        # Retrieval instrumentation: never crash, always observable.
        info(
            "chat_retrieval_detail",
            user_id=user_id,
            document_id=str(document_id),
            query=question[:500],
            matches_count=len(matches),
            similarity_scores=[round(match.similarity_score, 4) for match in matches],
            clause_titles=[match.title for match in matches][:5],
        )

        # ---- Stage: Context Build ----
        info("CHAT_CONTEXT_BUILD_START", user_id=user_id, document_id=str(document_id))
        matches = [match for match in matches if match.similarity_score >= MIN_SIMILARITY]
        info(
            "CHAT_CONTEXT_BUILD_DONE",
            user_id=user_id,
            document_id=str(document_id),
            matches_after_filter=len(matches),
            min_similarity=MIN_SIMILARITY,
        )

        # ---- Stage: Gemini Generation (or genuine no-context fallback) ----
        # CHAT_GEMINI_SKIPPED fires ONLY when there is no context at all
        # (empty vector matches AND empty analysis/OCR text). When vector
        # search is empty but the document has OCR-derived analysis text,
        # Gemini is still called with that fallback context — never skipped
        # silently.
        if not matches:
            fallback_matches = self._fallback_matches(
                document.get("analysis") if isinstance(document.get("analysis"), dict) else None
            )
            if fallback_matches:
                info(
                    "CHAT_GEMINI_FALLBACK_CONTEXT",
                    reason="vector_empty_use_summary",
                    user_id=user_id,
                    document_id=str(document_id),
                    fallback_clauses=len(fallback_matches),
                )
                matches = fallback_matches
            else:
                info("CHAT_GEMINI_SKIPPED", reason="no_context_available", user_id=user_id, document_id=str(document_id))
                result = self._fallback_answer()
                # No CHAT_RESPONSE_SENT unless the exchange was actually
                # persisted — otherwise GET history would miss it.
                if await self._save_history(document_id, user_id, question, result):
                    self._log_response_sent(document_id, user_id, result, started)
                return result
        info("CHAT_GEMINI_START", user_id=user_id, document_id=str(document_id), matches=len(matches))
        try:
            result = await self._generate(question, matches)
        except ChatTimeoutError as exc:
            # All Gemini attempts timed out: propagate for HTTP 504 mapping.
            error(
                "CHAT_STAGE_FAILED",
                stage="gemini_generation",
                document_id=str(document_id),
                user_id=user_id,
                exc_type=type(exc).__name__,
                exc_message=str(exc),
                traceback=traceback.format_exc(),
            )
            raise
        except ChatGeminiError as exc:
            error(
                "CHAT_STAGE_FAILED",
                stage="gemini_generation",
                document_id=str(document_id),
                user_id=user_id,
                exc_type=type(exc).__name__,
                exc_message=str(exc),
                traceback=traceback.format_exc(),
            )
            raise
        except Exception as exc:
            error(
                "CHAT_STAGE_FAILED",
                stage="gemini_generation",
                document_id=str(document_id),
                user_id=user_id,
                exc_type=type(exc).__name__,
                exc_message=str(exc),
                traceback=traceback.format_exc(),
            )
            raise ChatServiceError("Chat generation failed") from exc
        info("CHAT_GEMINI_SUCCESS", user_id=user_id, document_id=str(document_id))

        # ---- Post-process: citation validation ----
        valid_excerpts = {match.excerpt for match in matches}
        citations = [citation for citation in result.citations if citation.excerpt in valid_excerpts]
        result = result.model_copy(
            update={"citations": citations, "confidence_score": self._confidence(matches, citations)}
        )

        # ---- Stage: Persistence (must succeed before CHAT_RESPONSE_SENT) ----
        # Persistence never blocks the answer, but SENT is logged only when
        # the validated response was actually persisted.
        saved = await self._save_history(document_id, user_id, question, result)
        if saved:
            self._log_response_sent(document_id, user_id, result, started)
        return result

    async def history(self, document_id: UUID, user_id: str) -> list[dict[str, Any]]:
        """Return history for an owned document."""
        document = await asyncio.to_thread(self._repository.get_document, document_id, user_id)
        if document is None:
            raise ChatDocumentNotFoundError("Document not found")
        if str(document.get("user_id")) != user_id:
            raise ChatForbiddenError("Document access denied")
        try:
            return await asyncio.to_thread(self._repository.get_history, document_id, user_id)
        except ChatRepositoryError as exc:
            raise ChatPersistenceError("Chat history is unavailable") from exc

    async def delete_history(self, document_id: UUID, user_id: str) -> None:
        """Delete history for an owned document."""
        document = await asyncio.to_thread(self._repository.get_document, document_id, user_id)
        if document is None:
            raise ChatDocumentNotFoundError("Document not found")
        if str(document.get("user_id")) != user_id:
            raise ChatForbiddenError("Document access denied")
        try:
            await asyncio.to_thread(self._repository.delete_history, document_id, user_id)
        except ChatRepositoryError as exc:
            raise ChatPersistenceError("Chat history could not be deleted") from exc
