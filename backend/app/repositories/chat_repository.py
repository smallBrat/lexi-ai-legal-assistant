"""Supabase repository for authenticated document conversations."""

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from supabase import Client

try:
    from postgrest.exceptions import APIError
except ImportError:  # pragma: no cover
    APIError = None  # type: ignore[assignment,misc]

from app.core.logging import error


class ChatRepositoryError(Exception):
    """Raised when chat persistence fails."""


class ChatRepository:
    """Encapsulate chat history and document ownership queries."""

    def __init__(self, client: Client) -> None:
        """Initialize with a Supabase client."""
        self._client = client

    def get_document(self, document_id: UUID, user_id: str) -> dict[str, Any] | None:
        """Fetch a document for ownership verification and chat context."""
        try:
            response = (
                self._client.table("documents")
                .select("id,user_id,analysis,status")
                .eq("id", str(document_id))
                .limit(1)
                .execute()
            )
            rows = cast("list[dict[str, Any]]", response.data or [])
            return rows[0] if rows else None
        except Exception as exc:
            raise ChatRepositoryError("Unable to fetch chat document") from exc

    def save_message(
        self,
        document_id: UUID,
        user_id: str,
        question: str,
        answer: dict[str, Any],
        timestamp: datetime,
    ) -> None:
        """Persist one authenticated conversation exchange."""
        try:
            self._client.table("chat_history").insert(
                {
                    "document_id": str(document_id),
                    "user_id": user_id,
                    "question": question,
                    "answer": answer["answer"],
                    "citations": answer["citations"],
                    "confidence_score": answer["confidence_score"],
                    "timestamp": timestamp.isoformat(),
                }
            ).execute()
        except Exception as exc:
            if APIError is not None and isinstance(exc, APIError):
                error(
                    "Chat persistence PostgREST error",
                    api_message=exc.message,
                    api_code=exc.code,
                    api_details=exc.details,
                    api_hint=exc.hint,
                    document_id=str(document_id),
                    user_id=user_id,
                    exc_repr=repr(exc),
                )
            else:
                error(
                    "Chat persistence failed",
                    exc_type=type(exc).__name__,
                    exc_message=str(exc),
                    document_id=str(document_id),
                    user_id=user_id,
                    exc_repr=repr(exc),
                )
            raise ChatRepositoryError("Unable to save chat message") from exc

    def get_history(self, document_id: UUID, user_id: str) -> list[dict[str, Any]]:
        """Return conversation history for an owned document.

        Single normalization place for the history contract: guarantees
        every row carries the exact ``ChatHistoryItem`` fields. Legacy
        rows lack ``follow_up_questions`` (never persisted by
        ``save_message``), so it is defaulted here — never in the API
        layer or the frontend. NULL columns are coerced to safe defaults
        so a nullable field can never 500 history serialization.
        """
        try:
            response = (
                self._client.table("chat_history")
                .select(
                    "document_id,user_id,question,answer,citations,confidence_score,timestamp"
                )
                .eq("document_id", str(document_id))
                .eq("user_id", user_id)
                .order("timestamp", desc=False)
                .limit(200)
                .execute()
            )
            rows = cast("list[dict[str, Any]]", response.data or [])
            for row in rows:
                row["question"] = row.get("question") or ""
                row["answer"] = row.get("answer") or ""
                row["citations"] = row.get("citations") or []
                row["confidence_score"] = row.get("confidence_score")
                if not isinstance(row["confidence_score"], int):
                    row["confidence_score"] = 0
                row["timestamp"] = row.get("timestamp") or datetime.now().isoformat()
                row["follow_up_questions"] = row.get("follow_up_questions") or []
            return rows
        except Exception as exc:
            if APIError is not None and isinstance(exc, APIError):
                error(
                    "Chat history fetch PostgREST error",
                    api_message=exc.message,
                    api_code=exc.code,
                    api_details=exc.details,
                    api_hint=exc.hint,
                    document_id=str(document_id),
                    user_id=user_id,
                    exc_repr=repr(exc),
                )
            else:
                error(
                    "Chat history fetch failed",
                    exc_type=type(exc).__name__,
                    exc_message=str(exc),
                    document_id=str(document_id),
                    user_id=user_id,
                    exc_repr=repr(exc),
                )
            raise ChatRepositoryError("Unable to fetch chat history") from exc

    def delete_history(self, document_id: UUID, user_id: str) -> None:
        """Delete chat history belonging to an authenticated user."""
        try:
            self._client.table("chat_history").delete().eq(
                "document_id", str(document_id)
            ).eq("user_id", user_id).execute()
        except Exception as exc:
            raise ChatRepositoryError("Unable to delete chat history") from exc
