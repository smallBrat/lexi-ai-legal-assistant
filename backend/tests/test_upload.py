"""Tests for the document upload and OCR pipeline."""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import fitz
import pytest
from fastapi.testclient import TestClient

from app.api import upload as upload_module
from app.core.security import AuthenticatedUser, get_current_user
from app.main import app
from app.services.ocr_service import OCRService
from app.services.storage_service import StorageService

USER_ID = "user-123"


class FakeDocumentsTable:
    """Capture document metadata operations made through Supabase."""

    def __init__(self) -> None:
        self.inserted: dict[str, Any] | None = None
        self.updates: list[dict[str, Any]] = []
        self.document_id: str | None = None

    def insert(self, values: dict[str, Any]) -> "FakeDocumentsTable":
        """Capture an insert payload."""
        self.inserted = values
        return self

    def update(self, values: dict[str, Any]) -> "FakeDocumentsTable":
        """Capture an update payload."""
        self.updates.append(values)
        return self

    def eq(self, _column: str, value: str) -> "FakeDocumentsTable":
        """Capture the document identifier used by an update."""
        self.document_id = value
        return self

    def execute(self) -> SimpleNamespace:
        """Return a successful Supabase-like response."""
        return SimpleNamespace(data=[self.inserted] if self.inserted else [])


class FakeSupabaseClient:
    """Minimal Supabase client double for metadata persistence tests."""

    def __init__(self) -> None:
        self.documents = FakeDocumentsTable()

    def table(self, name: str) -> FakeDocumentsTable:
        """Return the fake documents table."""
        assert name == "documents"
        return self.documents


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, FakeSupabaseClient, MagicMock]]:
    """Provide an authenticated client with mocked Supabase boundaries."""
    fake_client = FakeSupabaseClient()
    fake_storage = MagicMock(spec=StorageService)
    monkeypatch.setattr(upload_module, "get_supabase", lambda: fake_client)
    monkeypatch.setattr(upload_module, "StorageService", lambda _client: fake_storage)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=USER_ID)
    with TestClient(app) as test_client:
        yield test_client, fake_client, fake_storage
    app.dependency_overrides.clear()


def pdf_bytes(text: str = "Employment agreement text") -> bytes:
    """Create a valid one-page PDF for tests."""
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def test_successful_pdf_upload(
    client: tuple[TestClient, FakeSupabaseClient, MagicMock],
) -> None:
    """Upload a valid PDF and return extracted text in the response."""
    test_client, _fake_client, fake_storage = client

    response = test_client.post(
        "/upload",
        files={"file": ("employment.pdf", pdf_bytes(), "application/pdf")},
        data={"document_type": "employment", "title": "  Employment agreement  "},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["title"] == "Employment agreement"
    assert body["pages"] == 1
    assert "Employment agreement text" in body["text_preview"]
    assert body["character_count"] > 0
    fake_storage.upload_file.assert_called_once()


def test_invalid_extension(
    client: tuple[TestClient, FakeSupabaseClient, MagicMock],
) -> None:
    """Reject files with unsupported extensions."""
    test_client, _fake_client, fake_storage = client

    response = test_client.post(
        "/upload",
        files={"file": ("document.exe", b"content", "application/octet-stream")},
        data={"document_type": "other"},
    )

    assert response.status_code == 415
    fake_storage.upload_file.assert_not_called()


def test_oversized_file(
    client: tuple[TestClient, FakeSupabaseClient, MagicMock],
) -> None:
    """Reject files larger than 20 MB."""
    test_client, _fake_client, fake_storage = client

    response = test_client.post(
        "/upload",
        files={
            "file": (
                "large.pdf",
                b"x" * (upload_module.MAX_UPLOAD_SIZE + 1),
                "application/pdf",
            )
        },
        data={"document_type": "other"},
    )

    assert response.status_code == 413
    fake_storage.upload_file.assert_not_called()


def test_empty_file(
    client: tuple[TestClient, FakeSupabaseClient, MagicMock],
) -> None:
    """Reject empty uploads."""
    test_client, _fake_client, fake_storage = client

    response = test_client.post(
        "/upload",
        files={"file": ("empty.pdf", b"", "application/pdf")},
        data={"document_type": "other"},
    )

    assert response.status_code == 400
    fake_storage.upload_file.assert_not_called()


def test_ocr_extraction_returns_text() -> None:
    """Extract page text from a valid PDF."""
    result = OCRService().extract_text(pdf_bytes("Confidential loan terms"), "pdf")

    assert result.total_pages == 1
    assert result.pages[0].page_number == 1
    assert "Confidential loan terms" in result.text


def test_metadata_inserted_into_supabase(
    client: tuple[TestClient, FakeSupabaseClient, MagicMock],
) -> None:
    """Persist the authenticated user and initial processing metadata."""
    test_client, fake_client, _fake_storage = client

    response = test_client.post(
        "/upload",
        files={"file": ("loan.pdf", pdf_bytes(), "application/pdf")},
        data={"document_type": "loan"},
    )

    assert response.status_code == 201
    inserted = fake_client.documents.inserted
    assert inserted is not None
    assert inserted["user_id"] == USER_ID
    assert inserted["document_type"] == "loan"
    assert inserted["status"] == "processing"
    assert inserted["storage_path"].endswith(".pdf")
    assert any(
        update["status"] == "completed" for update in fake_client.documents.updates
    )
