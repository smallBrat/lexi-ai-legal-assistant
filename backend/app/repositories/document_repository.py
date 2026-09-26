"""Supabase repository for user-owned document records."""

from typing import Any
from uuid import UUID

from supabase import Client


class DocumentRepositoryError(Exception):
    """Raised when a document database operation fails."""


class DocumentRepository:
    """Encapsulate all PostgreSQL access for documents."""

    def __init__(self, client: Client) -> None:
        """Initialize the repository with a Supabase client."""
        self._client = client

    def list_documents(
        self,
        user_id: str,
        page: int,
        page_size: int,
        search: str | None,
        document_type: str | None,
        risk_level: str | None,
        status: str | None,
        sort: str,
        order: str,
    ) -> tuple[list[dict[str, Any]], int]:
        """List a user's documents with filters and pagination."""
        try:
            query = self._client.table("documents").select(
                "id,title,document_type,status,pages,created_at,updated_at,storage_path,analysis",
                count="exact",
            ).eq("user_id", user_id)
            if search:
                query = query.ilike("title", f"%{search}%")
            if document_type:
                query = query.eq("document_type", document_type)
            if status:
                query = query.eq("status", status)
            if risk_level:
                query = query.eq("analysis->>risk_level", risk_level)
            query = query.order(sort, desc=order == "desc")
            start = (page - 1) * page_size
            response = query.range(start, start + page_size - 1).execute()
            return response.data or [], int(response.count or 0)
        except Exception as exc:
            raise DocumentRepositoryError("Unable to list documents") from exc

    def get_document(self, document_id: UUID) -> dict[str, Any] | None:
        """Fetch a document by UUID without applying ownership."""
        try:
            response = (
                self._client.table("documents")
                .select(
                    "id,title,document_type,status,pages,created_at,updated_at,storage_path,analysis,"
                    "extracted_text,user_id"
                )
                .eq("id", str(document_id))
                .limit(1)
                .execute()
            )
            records = response.data or []
            return records[0] if records else None
        except Exception as exc:
            raise DocumentRepositoryError("Unable to fetch document") from exc

    def update_document(
        self, document_id: UUID, user_id: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an owned document and return the updated row."""
        try:
            response = (
                self._client.table("documents")
                .update(values)
                .eq("id", str(document_id))
                .eq("user_id", user_id)
                .select(
                    "id,title,document_type,status,pages,created_at,updated_at,storage_path,analysis"
                )
                .single()
                .execute()
            )
            if not response.data:
                raise DocumentRepositoryError("Document update returned no row")
            return response.data
        except DocumentRepositoryError:
            raise
        except Exception as exc:
            raise DocumentRepositoryError("Unable to update document") from exc

    def delete_document(self, document_id: UUID, user_id: str) -> None:
        """Delete child records and the owned document row."""
        try:
            for table, column in (
                ("clauses", "document_id"),
                ("chat_history", "document_id"),
                ("comparisons", "document_a_id"),
                ("comparisons", "document_b_id"),
            ):
                self._client.table(table).delete().eq(column, str(document_id)).execute()
            response = (
                self._client.table("documents")
                .delete()
                .eq("id", str(document_id))
                .eq("user_id", user_id)
                .execute()
            )
            if response.data is not None and not response.data:
                raise DocumentRepositoryError("Document deletion returned no row")
        except DocumentRepositoryError:
            raise
        except Exception as exc:
            raise DocumentRepositoryError("Unable to delete document") from exc
