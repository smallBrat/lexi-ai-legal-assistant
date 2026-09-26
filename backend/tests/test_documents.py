"""Tests for the authenticated documents API."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import documents as documents_api
from app.core.security import AuthenticatedUser, get_current_user
from app.main import app
from app.schemas.document_schema import (
    DocumentDeleteResponse,
    DocumentDetail,
    DocumentListResponse,
)
from app.services.document_service import (
    DocumentForbiddenError,
    DocumentNotFoundError,
    DocumentService,
)

USER_ID = "user-123"
DOCUMENT_ID = uuid4()
CREATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def document_row(**overrides: Any) -> dict[str, Any]:
    """Build a representative database document row."""
    row: dict[str, Any] = {
        "id": str(DOCUMENT_ID),
        "user_id": USER_ID,
        "title": "Lease agreement",
        "document_type": "rental",
        "status": "completed",
        "pages": 4,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
        "storage_path": f"{DOCUMENT_ID}.pdf",
        "analysis": None,
    }
    row.update(overrides)
    return row


@pytest.fixture
def service() -> tuple[DocumentService, MagicMock, MagicMock]:
    """Provide a service with mocked repository and storage dependencies."""
    repository = MagicMock()
    storage = MagicMock()
    storage.get_signed_url.return_value = "https://signed.example/document"
    return DocumentService(repository, storage), repository, storage


def test_list_documents_pagination_and_signed_urls(
    service: tuple[DocumentService, MagicMock, MagicMock],
) -> None:
    """Return pagination metadata and sign only returned rows."""
    document_service, repository, storage = service
    repository.list_documents.return_value = ([document_row()], 21)

    result = __import__("asyncio").run(
        document_service.list_documents(
            USER_ID,
            page=2,
            page_size=10,
            search=None,
            document_type=None,
            risk_level=None,
            status=None,
            sort="created_at",
            order="desc",
        )
    )

    assert isinstance(result, DocumentListResponse)
    assert result.page == 2
    assert result.page_size == 10
    assert result.total_items == 21
    assert result.total_pages == 3
    assert result.has_next is True
    assert result.has_previous is True
    assert result.items[0].signed_preview_url == "https://signed.example/document"
    storage.get_signed_url.assert_called_once_with(f"{DOCUMENT_ID}.pdf", 900)


def test_list_documents_passes_trimmed_search_and_filters(
    service: tuple[DocumentService, MagicMock, MagicMock],
) -> None:
    """Pass search, filters, and sorting to the repository unchanged."""
    document_service, repository, _storage = service
    repository.list_documents.return_value = ([], 0)

    __import__("asyncio").run(
        document_service.list_documents(
            USER_ID,
            page=1,
            page_size=20,
            search=" lease ",
            document_type="rental",
            risk_level="high",
            status="completed",
            sort="title",
            order="asc",
        )
    )

    repository.list_documents.assert_called_once_with(
        USER_ID,
        page=1,
        page_size=20,
        search=" lease ",
        document_type="rental",
        risk_level="high",
        status="completed",
        sort="title",
        order="asc",
    )


@pytest.mark.asyncio
async def test_get_document_enforces_ownership(
    service: tuple[DocumentService, MagicMock, MagicMock],
) -> None:
    """Reject a document owned by a different authenticated user."""
    document_service, repository, _storage = service
    repository.get_document.return_value = document_row(user_id="other-user")

    with pytest.raises(DocumentForbiddenError):
        await document_service.get_document(DOCUMENT_ID, USER_ID)


@pytest.mark.asyncio
async def test_get_document_returns_404_error_for_missing_row(
    service: tuple[DocumentService, MagicMock, MagicMock],
) -> None:
    """Raise the service not-found error for missing documents."""
    document_service, repository, _storage = service
    repository.get_document.return_value = None

    with pytest.raises(DocumentNotFoundError):
        await document_service.get_document(DOCUMENT_ID, USER_ID)


@pytest.mark.asyncio
async def test_update_document_preserves_existing_fields(
    service: tuple[DocumentService, MagicMock, MagicMock],
) -> None:
    """Update only requested fields on an owned document."""
    document_service, repository, _storage = service
    repository.get_document.return_value = document_row()
    repository.update_document.return_value = document_row(title="Updated lease")

    result = await document_service.update_document(
        DOCUMENT_ID, USER_ID, {"title": "Updated lease"}
    )

    assert isinstance(result, DocumentDetail)
    assert result.title == "Updated lease"
    repository.update_document.assert_called_once_with(
        DOCUMENT_ID, USER_ID, {"title": "Updated lease"}
    )


@pytest.mark.asyncio
async def test_delete_document_removes_storage_and_metadata(
    service: tuple[DocumentService, MagicMock, MagicMock],
) -> None:
    """Delete the private file before deleting database records."""
    document_service, repository, storage = service
    repository.get_document.return_value = document_row()

    result = await document_service.delete_document(DOCUMENT_ID, USER_ID)

    assert isinstance(result, DocumentDeleteResponse)
    assert result.deleted is True
    assert result.storage_deleted is True
    storage.delete_file.assert_called_once_with(f"{DOCUMENT_ID}.pdf")
    repository.delete_document.assert_called_once_with(DOCUMENT_ID, USER_ID)


@pytest.mark.asyncio
async def test_signed_url_generation_uses_fifteen_minutes(
    service: tuple[DocumentService, MagicMock, MagicMock],
) -> None:
    """Generate a temporary signed URL with a 900-second expiry."""
    document_service, repository, storage = service
    repository.get_document.return_value = document_row()

    result = await document_service.signed_url(DOCUMENT_ID, USER_ID)

    assert result.expires_in == 900
    assert result.signed_url == "https://signed.example/document"
    storage.get_signed_url.assert_called_once_with(f"{DOCUMENT_ID}.pdf", 900)


def test_api_returns_401_without_jwt() -> None:
    """Require authentication for document routes."""
    with TestClient(app) as client:
        response = client.get("/documents")

    assert response.status_code == 401


def test_api_returns_422_for_invalid_uuid() -> None:
    """Reject malformed document identifiers."""
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=USER_ID)
    try:
        with TestClient(app) as client:
            response = client.get("/documents/not-a-uuid")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_api_maps_forbidden_document_to_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Map ownership failures to HTTP 403."""
    service = MagicMock()
    service.get_document.side_effect = DocumentForbiddenError("denied")
    monkeypatch.setattr(documents_api, "get_document_service", lambda: service)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=USER_ID)
    try:
        with TestClient(app) as client:
            response = client.get(f"/documents/{DOCUMENT_ID}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
