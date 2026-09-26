"""Reindex workflow for Gemini Embedding 2 migration.

Usage:
    python -m backend.scripts.reindex_cli --document-id <uuid> --user-id <user>
    python -m backend.scripts.reindex_cli --full

This script safely detects old gemini-embedding-001 vectors,
invalidates them, and rebuilds all embeddings with gemini-embedding-2.
"""

import argparse
import sys
import traceback
from typing import Any
from uuid import UUID

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

from app.core.logging import error, info
from app.services.embedding_service import (
    EmbeddingService,
    EmbeddingServiceError,
    get_embedding_service,
    reset_embedding_service,
)


def reindex_single_document(
    service: EmbeddingService, user_id: str, document_id: UUID
) -> dict[str, Any]:
    """Re-index a single document."""
    info(
        "REINDEX_START",
        document_id=str(document_id),
        user_id=user_id,
        scope="single",
    )
    # In production, fetch clauses from Supabase.
    # This is a template - the actual implementation depends on
    # the document storage layer.
    try:
        from app.core.supabase import get_supabase
        from app.repositories.document_repository import DocumentRepository

        client = get_supabase()
        repo = DocumentRepository(client)
        document = repo.get_document(document_id)
        if document is None:
            raise ValueError(f"Document {document_id} not found")
        analysis = document.get("analysis")
        clauses = analysis.get("clauses", []) if analysis else []
        result = service.reindex_document(user_id, document_id, clauses)
        info(
            "REINDEX_DONE",
            document_id=str(document_id),
            user_id=user_id,
            scope="single",
            **result,
        )
        return result
    except Exception as exc:
        error(
            "REINDEX_FAILED",
            document_id=str(document_id),
            user_id=user_id,
            scope="single",
            exc_type=type(exc).__name__,
            exc_message=str(exc),
            traceback=traceback.format_exc(),
        )
        raise


def reindex_all(user_id: str) -> dict[str, Any]:
    """Re-index all documents for a user."""
    info(
        "REINDEX_START",
        user_id=user_id,
        scope="full",
    )
    service = get_embedding_service()
    # In production, fetch all document IDs from Supabase.
    # This is a template implementation.
    try:
        from app.core.supabase import get_supabase
        from app.repositories.document_repository import DocumentRepository

        client = get_supabase()
        repo = DocumentRepository(client)
        # Get all documents for the user
        documents = repo.list_documents(user_id, 1, 100, None, None, None, None, "created_at", "asc")
        total_reindexed = 0
        for doc in documents[0]:
            doc_id = UUID(str(doc["id"]))
            analysis = doc.get("analysis")
            clauses = analysis.get("clauses", []) if analysis else []
            if not clauses:
                continue
            service.reindex_document(user_id, doc_id, clauses)
            total_reindexed += 1
        info(
            "REINDEX_DONE",
            user_id=user_id,
            scope="full",
            documents_reindexed=total_reindexed,
        )
        return {"user_id": user_id, "documents_reindexed": total_reindexed, "scope": "full"}
    except Exception as exc:
        error(
            "REINDEX_FAILED",
            user_id=user_id,
            scope="full",
            exc_type=type(exc).__name__,
            exc_message=str(exc),
            traceback=traceback.format_exc(),
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Reindex documents for Gemini Embedding 2")
    parser.add_argument("--document-id", type=str, help="Re-index a single document")
    parser.add_argument("--user-id", type=str, required=True, help="User ID")
    parser.add_argument("--full", action="store_true", help="Re-index all documents")
    parser.add_argument("--reset-singleton", action="store_true", help="Reset the embedding service singleton")
    args = parser.parse_args()

    if args.reset_singleton:
        reset_embedding_service()

    service = get_embedding_service()

    try:
        if args.full:
            reindex_all(args.user_id)
        elif args.document_id:
            reindex_single_document(service, args.user_id, UUID(args.document_id))
        else:
            parser.print_help()
            sys.exit(1)
    except EmbeddingServiceError as exc:
        error("Reindex failed", error=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
