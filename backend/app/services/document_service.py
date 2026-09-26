"""Business logic for the authenticated documents API."""

import asyncio
from math import ceil
from time import perf_counter
from typing import Any
from uuid import UUID

from app.core.logging import error, info
from app.repositories.document_repository import (
    DocumentRepository,
    DocumentRepositoryError,
)
from app.schemas.analysis_schema import LegalAnalysis
from app.schemas.document_schema import (
    DocumentDeleteResponse,
    DocumentDetail,
    DocumentListItem,
    DocumentListResponse,
    DocumentStatus,
    DocumentType,
    SignedUrlResponse,
)
from app.services.storage_service import StorageService, StorageServiceError


class DocumentServiceError(Exception):
    """Base exception for document service failures."""


class DocumentNotFoundError(DocumentServiceError):
    """Raised when a document does not exist."""


class DocumentForbiddenError(DocumentServiceError):
    """Raised when a document belongs to another user."""


class DocumentService:
    """Coordinate ownership, repository, and storage operations."""

    def __init__(self, repository: DocumentRepository, storage: StorageService) -> None:
        """Initialize the document service."""
        self._repository = repository
        self._storage = storage

    @staticmethod
    def _risk(analysis: Any) -> tuple[int, str | None]:
        """Extract or safely default risk values from stored analysis."""
        if not isinstance(analysis, dict):
            return 0, None
        score = int(analysis.get("risk_score") or 0)
        level = analysis.get("risk_level")
        return max(0, min(score, 100)), str(level) if level else None

    @classmethod
    def _list_item(cls, row: dict[str, Any], signed_url: str | None = None) -> DocumentListItem:
        """Map a database row to the list response model."""
        score, level = cls._risk(row.get("analysis"))
        analysis = row.get("analysis") or {}
        summary = str(analysis.get("summary") or "")[:300]
        clauses = analysis.get("clauses") or []
        flag_count = sum(1 for c in clauses if c.get("risk_level", "low") != "low")
        return DocumentListItem(
            id=UUID(str(row["id"])), title=str(row["title"]),
            document_type=DocumentType(str(row["document_type"])),
            status=DocumentStatus(str(row["status"])), risk_score=score,
            risk_level=level, flag_count=flag_count, pages=int(row.get("pages") or 0),
            created_at=row["created_at"], updated_at=row.get("updated_at"),
            summary_preview=summary, storage_path=str(row["storage_path"]),
            signed_preview_url=signed_url,
        )

    @classmethod
    def _detail(cls, row: dict[str, Any]) -> DocumentDetail:
        """Map a database row to the detail response model."""
        analysis_data = row.get("analysis")
        analysis = LegalAnalysis.model_validate(analysis_data) if analysis_data else None
        item = cls._list_item(row)
        return DocumentDetail(
            **item.model_dump(), analysis=analysis,
            clauses=analysis.clauses if analysis else [],
            timeline=analysis.timeline if analysis else [],
            obligations=analysis.obligations if analysis else [],
            glossary=analysis.glossary if analysis else [],
            questions_for_lawyer=analysis.questions_for_lawyer if analysis else [],
            reading_difficulty=analysis.reading_difficulty if analysis else None,
        )

    async def list_documents(self, user_id: str, **filters: Any) -> DocumentListResponse:
        """List documents with validated filters and signed preview URLs."""
        started = perf_counter()
        rows, total = await asyncio.to_thread(self._repository.list_documents, user_id, **filters)

        async def _signed_url(row: dict[str, Any]) -> str | None:
            try:
                return await asyncio.to_thread(
                    self._storage.get_signed_url, str(row["storage_path"]), 900
                )
            except StorageServiceError as exc:
                error("Document preview URL failed", user_id=user_id, error=str(exc))
                return None

        # Phase 15 efficiency: create all signed URLs concurrently instead
        # of serially — one storage round-trip of latency per page, not N.
        signed_urls = await asyncio.gather(*(_signed_url(row) for row in rows))
        items = [
            self._list_item(row, signed_url)
            for row, signed_url in zip(rows, signed_urls)
        ]
        page = filters["page"]
        page_size = filters["page_size"]
        total_pages = ceil(total / page_size) if total else 0
        info("Documents listed", user_id=user_id, duration_ms=round((perf_counter() - started) * 1000, 2))
        return DocumentListResponse(
            items=items, page=page, page_size=page_size, total_items=total,
            total_pages=total_pages, has_next=page < total_pages,
            has_previous=page > 1 and total_pages > 0,
        )

    async def get_document(self, document_id: UUID, user_id: str) -> DocumentDetail:
        """Fetch one document and enforce ownership."""
        started = perf_counter()
        try:
            row = await asyncio.to_thread(self._repository.get_document, document_id)
        except DocumentRepositoryError as exc:
            raise DocumentServiceError("Unable to fetch document") from exc
        if row is None:
            raise DocumentNotFoundError("Document not found")
        if str(row.get("user_id")) != user_id:
            raise DocumentForbiddenError("Document access denied")
        info("Document fetched", user_id=user_id, document_id=str(document_id), duration_ms=round((perf_counter() - started) * 1000, 2))
        return self._detail(row)

    async def update_document(self, document_id: UUID, user_id: str, values: dict[str, Any]) -> DocumentDetail:
        """Update fields on an owned document."""
        await self.get_document(document_id, user_id)
        try:
            row = await asyncio.to_thread(self._repository.update_document, document_id, user_id, values)
        except DocumentRepositoryError as exc:
            raise DocumentServiceError("Unable to update document") from exc
        info("Document updated", user_id=user_id, document_id=str(document_id))
        return self._detail(row)

    async def delete_document(self, document_id: UUID, user_id: str) -> DocumentDeleteResponse:
        """Delete storage and all related database records."""
        started = perf_counter()
        document = await self.get_document(document_id, user_id)
        storage_deleted = True
        try:
            await asyncio.to_thread(self._storage.delete_file, document.storage_path)
        except StorageServiceError as exc:
            storage_deleted = False
            error("Document storage cleanup failed", user_id=user_id, document_id=str(document_id), error=str(exc))
        try:
            await asyncio.to_thread(self._repository.delete_document, document_id, user_id)
        except DocumentRepositoryError as exc:
            raise DocumentServiceError("Unable to delete document metadata") from exc
        info("Document deleted", user_id=user_id, document_id=str(document_id), duration_ms=round((perf_counter() - started) * 1000, 2))
        return DocumentDeleteResponse(
            document_id=document_id, deleted=True, storage_deleted=storage_deleted,
            message="Document deleted." if storage_deleted else "Document metadata deleted; file cleanup is pending.",
        )

    async def signed_url(self, document_id: UUID, user_id: str) -> SignedUrlResponse:
        """Generate a 15-minute signed URL for an owned document."""
        document = await self.get_document(document_id, user_id)
        try:
            url = await asyncio.to_thread(self._storage.get_signed_url, document.storage_path, 900)
        except StorageServiceError as exc:
            raise DocumentServiceError("Document file is unavailable") from exc
        info("Signed URL generated", user_id=user_id, document_id=str(document_id))
        return SignedUrlResponse(document_id=document_id, signed_url=url, expires_in=900)
