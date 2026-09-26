"""Authenticated document-grounded chat endpoints."""

import asyncio
import traceback
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthenticatedUser, get_current_user
from app.core.logging import error, info
from app.core.supabase import get_supabase
from app.repositories.chat_repository import ChatRepository
from app.schemas.chat_schema import (
    ChatDeleteResponse,
    ChatHistoryItem,
    ChatHistoryResponse,
    ChatQuestionRequest,
    ChatRequest,
    ChatResponse,
)
from app.services.chat_service import (
    ChatDocumentNotFoundError,
    ChatEmptyQuestionError,
    ChatForbiddenError,
    ChatGeminiError,
    ChatPersistenceError,
    ChatService,
    ChatServiceError,
    ChatTimeoutError,
)
from app.services.embedding_service import EmbeddingServiceError, get_embedding_service
from app.services.retrieval_service import RetrievalService

router = APIRouter(tags=["chat"])

# Total chat timeout budget: 150s.  The frontend CHAT_REQUEST_TIMEOUT_MS is
# 120s; the backend adds a 30s safety margin for persistence and overhead.
CHAT_TOTAL_TIMEOUT_SECONDS = 150.0


def get_chat_service() -> ChatService:
    """Build the chat service from configured dependencies.

    Uses the singleton ``EmbeddingService`` so ChromaDB and the Gemini
    embedding client are initialised once per process, not per request.
    """
    return ChatService(
        ChatRepository(get_supabase()),
        RetrievalService(get_embedding_service()),
    )


# ------------------------------------------------------------------
# Structured error mapping — every chat error produces a JSON body
# with ``detail``, ``error_code``, and ``retryable``.
# ------------------------------------------------------------------

def _service_error(exc: Exception) -> HTTPException:
    """Map internal chat errors to structured HTTP responses."""
    if isinstance(exc, ChatEmptyQuestionError):
        return HTTPException(
            status_code=422,
            detail={
                "detail": "Question cannot be empty.",
                "error_code": "EMPTY_QUESTION",
                "retryable": False,
            },
        )
    if isinstance(exc, ChatDocumentNotFoundError):
        return HTTPException(
            status_code=404,
            detail={
                "detail": "Document not found.",
                "error_code": "DOCUMENT_NOT_FOUND",
                "retryable": False,
            },
        )
    if isinstance(exc, ChatForbiddenError):
        return HTTPException(
            status_code=403,
            detail={
                "detail": "You do not have access to this document.",
                "error_code": "FORBIDDEN",
                "retryable": False,
            },
        )
    if isinstance(exc, ChatGeminiError):
        # 502 only for upstream Gemini failures. Fail-fast config errors
        # (400/401/403/404) are NOT retryable; transient ones are.
        return HTTPException(
            status_code=502,
            detail={
                "detail": "The analysis provider returned an invalid response.",
                "error_code": "GEMINI_ERROR",
                "retryable": bool(exc.retryable),
            },
        )
    if isinstance(exc, ChatTimeoutError):
        return HTTPException(
            status_code=504,
            detail={
                "detail": "Gemini chat request timed out.",
                "error_code": "CHAT_TIMEOUT",
                "retryable": True,
            },
        )
    if isinstance(exc, ChatPersistenceError):
        return HTTPException(
            status_code=503,
            detail={
                "detail": "Chat history is temporarily unavailable.",
                "error_code": "PERSISTENCE_ERROR",
                "retryable": True,
            },
        )
    if isinstance(exc, EmbeddingServiceError):
        return HTTPException(
            status_code=503,
            detail={
                "detail": "Chat retrieval service is temporarily unavailable.",
                "error_code": "RETRIEVAL_UNAVAILABLE",
                "retryable": True,
            },
        )
    if isinstance(exc, asyncio.TimeoutError):
        return HTTPException(
            status_code=504,
            detail={
                "detail": "Chat response timed out.",
                "error_code": "CHAT_TIMEOUT",
                "retryable": True,
            },
        )
    if isinstance(exc, ChatServiceError):
        return HTTPException(
            status_code=503,
            detail={
                "detail": "Chat service is temporarily unavailable.",
                "error_code": "CHAT_SERVICE_ERROR",
                "retryable": True,
            },
        )
    # Unexpected internal error — never leak traceback to the client.
    error(
        "CHAT_STAGE_FAILED",
        stage="unknown",
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        traceback=traceback.format_exc(),
    )
    return HTTPException(
        status_code=500,
        detail={
            "detail": "An unexpected internal error occurred.",
            "error_code": "INTERNAL_ERROR",
            "retryable": False,
        },
    )


async def _answer(
    document_id: UUID,
    question: str,
    current_user: AuthenticatedUser,
    route: str,
) -> ChatResponse:
    """Run the shared answer flow with an overall timeout guard.

    The outer ``asyncio.wait_for`` ensures that no single chat request can
    block the event loop for longer than ``CHAT_TOTAL_TIMEOUT_SECONDS``.
    If the inner pipeline (ChromaDB init, embedding, Gemini, persistence)
    exceeds the budget the request returns a structured 504.
    """
    info(
        "CHAT_REQUEST_RECEIVED",
        route=route,
        document_id=str(document_id),
        user_id=current_user.id,
        question_length=len(question),
    )
    try:
        result = await asyncio.wait_for(
            get_chat_service().answer(document_id, current_user.id, question),
            timeout=CHAT_TOTAL_TIMEOUT_SECONDS,
        )
        return result
    except asyncio.TimeoutError:
        error(
            "CHAT_STAGE_FAILED",
            stage="total_timeout",
            document_id=str(document_id),
            user_id=current_user.id,
            timeout_seconds=CHAT_TOTAL_TIMEOUT_SECONDS,
        )
        raise
    except Exception as exc:
        raise _service_error(exc) from exc


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ChatResponse:
    """Answer a question using only retrieved clauses from the document."""
    return await _answer(request.document_id, request.question, current_user, route="POST /chat")


async def _history_rows(
    document_id: UUID,
    current_user: AuthenticatedUser,
    route: str,
) -> list[dict]:
    """Fetch + validate history with per-stage logging (never swallow errors).

    Stages: CHAT_HISTORY_REQUEST → CHAT_HISTORY_FETCH_START →
    CHAT_HISTORY_FETCH_DONE → CHAT_HISTORY_SERIALIZE_START →
    CHAT_HISTORY_SERIALIZE_DONE. Any throw logs exception class, failing
    line/value, and full traceback before mapping to an HTTP error.
    """
    info(
        "CHAT_HISTORY_REQUEST",
        route=route,
        document_id=str(document_id),
        user_id=current_user.id,
    )
    info(
        "CHAT_HISTORY_FETCH_START",
        document_id=str(document_id),
        user_id=current_user.id,
    )
    try:
        rows = await get_chat_service().history(document_id, current_user.id)
    except Exception as exc:
        error(
            "CHAT_STAGE_FAILED",
            stage="history_fetch",
            document_id=str(document_id),
            user_id=current_user.id,
            exc_type=type(exc).__name__,
            exc_message=str(exc),
            traceback=traceback.format_exc(),
        )
        raise
    info(
        "CHAT_HISTORY_FETCH_DONE",
        document_id=str(document_id),
        user_id=current_user.id,
        row_count=len(rows),
    )
    info(
        "CHAT_HISTORY_SERIALIZE_START",
        document_id=str(document_id),
        user_id=current_user.id,
        row_count=len(rows),
    )
    try:
        items: list[ChatHistoryItem] = []
        skipped = 0
        for index, row in enumerate(rows):
            try:
                items.append(ChatHistoryItem.model_validate(row))
            except Exception as row_exc:
                # A malformed row must never 500 the whole history: skip it
                # with full context for operators (DB/infra errors still
                # raise above and map to 500/503).
                skipped += 1
                error(
                    "CHAT_STAGE_FAILED",
                    stage="history_serialize_row",
                    document_id=str(document_id),
                    user_id=current_user.id,
                    row_index=index,
                    row_value=repr(row)[:2000],
                    exc_type=type(row_exc).__name__,
                    exc_message=str(row_exc),
                    traceback=traceback.format_exc(),
                )
    except Exception as exc:
        error(
            "CHAT_STAGE_FAILED",
            stage="history_serialize",
            document_id=str(document_id),
            user_id=current_user.id,
            exc_type=type(exc).__name__,
            exc_message=str(exc),
            traceback=traceback.format_exc(),
        )
        raise
    info(
        "CHAT_HISTORY_SERIALIZE_DONE",
        document_id=str(document_id),
        user_id=current_user.id,
        item_count=len(items),
        skipped_rows=skipped,
    )
    return items


@router.get("/chat/{document_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    document_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ChatHistoryResponse:
    """Return the authenticated user's conversation history."""
    try:
        items = await _history_rows(document_id, current_user, route="GET /chat/{document_id}")
        return ChatHistoryResponse(items=items)
    except Exception as exc:
        raise _service_error(exc) from exc


@router.delete("/chat/{document_id}", response_model=ChatDeleteResponse)
async def delete_chat_history(
    document_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ChatDeleteResponse:
    """Delete the authenticated user's conversation history."""
    try:
        await get_chat_service().delete_history(document_id, current_user.id)
        return ChatDeleteResponse(document_id=document_id, deleted=True, message="Chat history deleted.")
    except Exception as exc:
        raise _service_error(exc) from exc


@router.post("/documents/{document_id}/chat", response_model=ChatResponse)
async def compatibility_chat(
    document_id: UUID,
    request: ChatQuestionRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ChatResponse:
    """Preserve the existing frontend chat URL without changing its UI.

    Contract (PART 6): POST, path UUID, JSON body `{ question }` only
    (extra="forbid"), Content-Type: application/json, Bearer auth, no query
    params. The frontend sends exactly this shape.
    """
    return await _answer(document_id, request.question, current_user, route="POST /documents/{document_id}/chat")


@router.get("/documents/{document_id}/chat", response_model=list[ChatHistoryItem])
async def compatibility_chat_history(
    document_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> list[ChatHistoryItem]:
    """Preserve the existing frontend history URL."""
    try:
        return await _history_rows(
            document_id, current_user, route="GET /documents/{document_id}/chat"
        )
    except Exception as exc:
        raise _service_error(exc) from exc
