"""Regression tests for POST /analyze/{document_id} request validation.

The recurring production 422 came from requests that failed FastAPI request
validation *before* the endpoint body ran (Gemini never called). The endpoint
contract is Query-only: ``POST /analyze/{uuid}[?force=true]`` with **no**
request body. These tests pin every request variant so a stray body, an
invalid UUID (e.g. a hardcoded demo slug like ``msa-v2``), or a malformed
``force`` query can never silently regress.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

import app.api.analyze as analyze_api
from app.core.security import AuthenticatedUser, get_current_user
from app.main import app
from app.schemas.analysis_schema import LegalAnalysis

USER_ID = "user-123"


def _fake_analysis() -> LegalAnalysis:
    """Build a minimal valid LegalAnalysis for the mocked service."""
    return LegalAnalysis(
        summary="Summary.",
        plain_english_summary="Plain English.",
        document_type="rental",
        reading_difficulty=6,
        risk_score=12,
        risk_level="low",
        risk_reasons=[],
        clauses=[],
        obligations=[],
        timeline=[],
        glossary=[],
        questions_for_lawyer=[],
    )


class AnalyzeClient:
    """TestClient with auth + AnalysisService stubbed out."""

    def __init__(self) -> None:
        self.service = MagicMock()
        self.service.analyze_document = AsyncMock(return_value=_fake_analysis())
        self._orig = analyze_api.AnalysisService
        analyze_api.AnalysisService = lambda *args, **kwargs: self.service  # noqa: E731
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=USER_ID)

    def close(self) -> None:
        app.dependency_overrides.clear()
        analyze_api.AnalysisService = self._orig


def test_post_without_body_succeeds() -> None:
    """The canonical frontend request: POST with no body at all."""
    client = AnalyzeClient()
    try:
        with TestClient(app) as http:
            response = http.post(f"/analyze/{uuid4()}")
    finally:
        client.close()
    assert response.status_code == 200
    assert response.json()["risk_score"] == 12


def test_post_without_body_sends_no_content_type() -> None:
    """No body must mean no Content-Type requirement; handler still runs."""
    client = AnalyzeClient()
    try:
        with TestClient(app) as http:
            response = http.post(f"/analyze/{uuid4()}")
    finally:
        client.close()
    assert response.status_code == 200
    assert client.service.analyze_document.await_count == 1


def test_post_with_force_false_query() -> None:
    """Explicit ?force=false parses to False and calls the service."""
    document_id = uuid4()
    client = AnalyzeClient()
    try:
        with TestClient(app) as http:
            response = http.post(f"/analyze/{document_id}?force=false")
    finally:
        client.close()
    assert response.status_code == 200
    _, kwargs = client.service.analyze_document.call_args
    assert kwargs.get("force") is False or client.service.analyze_document.call_args[0][2] is False


def test_post_with_force_true_query() -> None:
    """?force=true bypasses the cache path."""
    document_id = uuid4()
    client = AnalyzeClient()
    try:
        with TestClient(app) as http:
            response = http.post(f"/analyze/{document_id}?force=true")
    finally:
        client.close()
    assert response.status_code == 200
    args, kwargs = client.service.analyze_document.call_args
    force = kwargs.get("force", args[2] if len(args) > 2 else None)
    assert force is True


def test_post_with_empty_json_body_is_tolerated() -> None:
    """The endpoint declares no body; a stray {} must not 422."""
    client = AnalyzeClient()
    try:
        with TestClient(app) as http:
            response = http.post(f"/analyze/{uuid4()}", json={})
    finally:
        client.close()
    assert response.status_code == 200


def test_post_with_unexpected_body_fields_is_tolerated() -> None:
    """A legacy {"force": ...} JSON body is ignored; query wins."""
    document_id = uuid4()
    client = AnalyzeClient()
    try:
        with TestClient(app) as http:
            response = http.post(f"/analyze/{document_id}", json={"force": True})
    finally:
        client.close()
    assert response.status_code == 200
    args, kwargs = client.service.analyze_document.call_args
    force = kwargs.get("force", args[2] if len(args) > 2 else None)
    assert force is False


def test_post_missing_auth_is_401_not_422() -> None:
    """No bearer token must be 401 (auth layer), never a validation 422."""
    app.dependency_overrides.clear()
    try:
        with TestClient(app) as http:
            response = http.post(f"/analyze/{uuid4()}")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 401


def test_post_with_demo_slug_id_is_422_and_never_reaches_service() -> None:
    """POST /analyze/msa-v2 fails UUID path validation before the handler.

    This is the exact recurring production 422: a hardcoded demo id fired by
    the report page / processing fallback. The service (Gemini) must never run.
    """
    client = AnalyzeClient()
    try:
        with TestClient(app) as http:
            response = http.post("/analyze/msa-v2")
    finally:
        client.close()
    assert response.status_code == 422
    assert client.service.analyze_document.await_count == 0
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["path", "document_id"]


def test_post_with_empty_force_query_is_422() -> None:
    """?force= (empty) is not a valid boolean."""
    client = AnalyzeClient()
    try:
        with TestClient(app) as http:
            response = http.post(f"/analyze/{uuid4()}?force=")
    finally:
        client.close()
    assert response.status_code == 422
    assert client.service.analyze_document.await_count == 0
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["query", "force"]
