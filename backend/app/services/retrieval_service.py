"""Document-clause retrieval orchestration."""

import asyncio
import json
import traceback
from typing import Any
from uuid import UUID

from app.core.logging import error, info
from app.services.embedding_service import (
    ClauseMatch,
    EmbeddingService,
    EmbeddingServiceError,
)


class RetrievalServiceError(Exception):
    """Raised when document clauses cannot be retrieved."""


class RetrievalService:
    """Index and retrieve clauses for one authenticated document."""

    def __init__(self, embedding_service: EmbeddingService) -> None:
        """Initialize retrieval with the embedding cache."""
        self._embedding_service = embedding_service

    async def retrieve(
        self,
        user_id: str,
        document_id: UUID,
        analysis: dict[str, Any] | None,
        question: str,
        top_k: int = 5,
    ) -> list[ClauseMatch]:
        """Retrieve relevant clauses from the pre-indexed collection."""
        clauses = list((analysis or {}).get("clauses") or [])

        # ---- Stage: Similarity search only (indexing happens at analysis time) ----
        info("CHAT_VECTOR_SEARCH_START", user_id=user_id, document_id=str(document_id), clause_count=len(clauses), query=question[:500])
        try:
            matches = await asyncio.to_thread(
                self._embedding_service.retrieve,
                user_id,
                document_id,
                question,
                top_k,
            )
        except EmbeddingServiceError as exc:
            error(
                "CHAT_VECTOR_SEARCH_FAILED",
                stage="vector_search",
                document_id=str(document_id),
                user_id=user_id,
                exc_type=type(exc).__name__,
                exc_message=str(exc),
                traceback=traceback.format_exc(),
            )
            return []
        except Exception as exc:
            error(
                "CHAT_VECTOR_SEARCH_FAILED",
                stage="vector_search",
                document_id=str(document_id),
                user_id=user_id,
                exc_type=type(exc).__name__,
                exc_message=str(exc),
                traceback=traceback.format_exc(),
            )
            return []

        info("CHAT_VECTOR_SEARCH_DONE", user_id=user_id, document_id=str(document_id), matches=len(matches))
        if matches:
            info(
                "chat_retrieval_scores",
                document_id=str(document_id),
                user_id=user_id,
                matches_count=len(matches),
                similarity_scores=[round(match.similarity_score, 4) for match in matches],
                clause_titles=[match.title for match in matches][:top_k],
            )
        else:
            # Only log fallback when Chroma truly has zero documents.
            # If the collection is empty (no vectors at all), use summary fallback.
            # If the collection has vectors but none match the query, that's a
            # normal retrieval outcome — the chat layer handles similarity filtering.
            collection = self._embedding_service._collection(user_id, document_id)
            if collection.count() == 0:
                info(
                    "chat_retrieval_empty_fallback",
                    document_id=str(document_id),
                    user_id=user_id,
                    query=question[:500],
                    fallback="document_summary",
                    reason="collection_empty",
                )
        return matches

    @staticmethod
    def format_context(matches: list[ClauseMatch]) -> str:
        """Format retrieved clauses as bounded, untrusted context."""
        return json.dumps(
            [
                {
                    "title": match.title,
                    "excerpt": match.excerpt,
                    "page_number": match.page_number,
                    "similarity_score": round(match.similarity_score, 4),
                }
                for match in matches
            ],
            ensure_ascii=False,
        )
