"""Tests for the clause-by-clause document comparison pipeline.

Covers every fixed Compare bug:
- dual-document loading (both IDs preserved, never overwritten),
- permission isolation (other-user documents are forbidden),
- pending analysis (422 surface, no Gemini call),
- malformed Gemini JSON (validation error, no persistence),
- cached comparison (no second Gemini call),
- deterministic clause merge + metric clamping.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.schemas.compare_schema import ComparisonResult
from app.services.compare_service import (
    CompareAnalysisPendingError,
    CompareDocumentNotFoundError,
    CompareForbiddenError,
    CompareService,
    CompareValidationError,
    build_comparison_input,
    merge_clause_titles,
)

USER_ID = "user-123"
OTHER_USER_ID = "user-999"


def _analysis_payload(title: str, excerpt: str) -> dict[str, Any]:
    """Return a minimal valid stored analysis."""
    return {
        "summary": f"Summary of {title}.",
        "plain_english_summary": f"Plain summary of {title}.",
        "document_type": "employment agreement",
        "reading_difficulty": 6,
        "risk_score": 20,
        "risk_level": "low",
        "risk_reasons": [],
        "clauses": [
            {
                "title": title,
                "category": "payment",
                "risk_level": "low",
                "importance_score": 50,
                "original_text": excerpt,
                "simplified_text": excerpt,
                "why_it_matters": "It matters.",
            }
        ],
        "obligations": [],
        "timeline": [],
        "glossary": [],
        "questions_for_lawyer": [],
    }


def _comparison_json() -> str:
    """Return a minimal valid comparison result."""
    return ComparisonResult(
        metrics={
            "similarity_score": 80,
            "total_clauses_compared": 2,
            "clauses_matched": 1,
            "clauses_changed": 1,
            "clauses_added": 0,
            "clauses_removed": 0,
            "similarity_justification": "1 matched of 2 compared clauses.",
        },
        clauses=[
            {
                "clause_name": "Payment Terms",
                "present_in_a": True,
                "present_in_b": True,
                "similarity": "similar",
                "text_a": "Pay on day one.",
                "text_b": "Pay on day five.",
                "difference_explanation": "Deadline moved.",
                "additional_obligations": "",
            }
        ],
    ).model_dump_json()


class SupabaseCompareDouble:
    """Serve two document rows through the Supabase query chain."""

    def __init__(self, rows: dict[str, dict[str, Any]]) -> None:
        self._rows = rows
        self._wanted: str | None = None
        self.query = MagicMock()
        self.query.select.return_value = self.query
        self.query.eq.side_effect = self._eq
        self.query.limit.return_value = self.query
        self.query.execute.side_effect = self._execute
        self.client = MagicMock()
        self.client.table.return_value = self.query

    def _eq(self, column: str, value: str) -> MagicMock:
        if column == "id":
            self._wanted = value
        return self.query

    def _execute(self) -> SimpleNamespace:
        row = self._rows.get(self._wanted or "")
        return SimpleNamespace(data=[row] if row else [])


def _service(rows: dict[str, dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> CompareService:
    """Build a compare service with a stubbed Gemini singleton."""
    monkeypatch.setattr("app.services.compare_service.gemini_provider.get_gemini_client", lambda: MagicMock())
    return CompareService(SupabaseCompareDouble(rows).client)


def _rows(both_analyzed: bool = True, owner_b: str = USER_ID) -> tuple[Any, Any, dict[str, dict[str, Any]]]:
    a_id, b_id = uuid4(), uuid4()
    rows = {
        str(a_id): {
            "id": str(a_id),
            "user_id": USER_ID,
            "title": "Employment Agreement",
            "document_type": "employment",
            "extracted_text": "Pay on day one.",
            "analysis": _analysis_payload("Payment Terms", "Pay on day one."),
        },
        str(b_id): {
            "id": str(b_id),
            "user_id": owner_b,
            "title": "Offer Letter",
            "document_type": "offer",
            "extracted_text": "Pay on day five.",
            "analysis": _analysis_payload("Payment Terms", "Pay on day five.")
            if both_analyzed
            else None,
        },
    }
    return a_id, b_id, rows


@pytest.mark.asyncio
async def test_load_documents_preserves_both_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both document IDs survive loading (regression: second upload replaced first)."""
    a_id, b_id, rows = _rows()
    service = _service(rows, monkeypatch)
    docs = await service.load_documents(a_id, b_id, USER_ID)
    assert str(docs.document_a["id"]) == str(a_id)
    assert str(docs.document_b["id"]) == str(b_id)
    assert docs.document_a["title"] == "Employment Agreement"
    assert docs.document_b["title"] == "Offer Letter"


@pytest.mark.asyncio
async def test_load_documents_forbidden_for_other_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """A document owned by another user is forbidden, not leaked."""
    a_id, b_id, rows = _rows(owner_b=OTHER_USER_ID)
    service = _service(rows, monkeypatch)
    with pytest.raises(CompareForbiddenError):
        await service.load_documents(a_id, b_id, USER_ID)


@pytest.mark.asyncio
async def test_load_documents_missing_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unknown document id raises not-found."""
    a_id, _b_id, rows = _rows()
    service = _service(rows, monkeypatch)
    with pytest.raises(CompareDocumentNotFoundError):
        await service.load_documents(a_id, uuid4(), USER_ID)


@pytest.mark.asyncio
async def test_load_documents_pending_when_analysis_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing analysis raises pending with per-document readiness."""
    a_id, b_id, rows = _rows(both_analyzed=False)
    service = _service(rows, monkeypatch)
    with pytest.raises(CompareAnalysisPendingError) as exc_info:
        await service.load_documents(a_id, b_id, USER_ID)
    assert exc_info.value.document_a_ready is True
    assert exc_info.value.document_b_ready is False


@pytest.mark.asyncio
async def test_compare_same_document_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Comparing a document with itself is rejected."""
    from app.services.compare_service import CompareServiceError

    a_id, _b_id, rows = _rows()
    service = _service(rows, monkeypatch)
    with pytest.raises(CompareServiceError):
        await service.compare(a_id, a_id, USER_ID)


def test_merge_clause_titles_is_deterministic() -> None:
    """Clause union is case-insensitive, deduplicated, and sorted."""
    from app.schemas.analysis_schema import LegalAnalysis

    analysis_a = LegalAnalysis.model_validate(_analysis_payload("Payment Terms", "Pay on day one."))
    analysis_b = LegalAnalysis.model_validate(_analysis_payload("payment  terms", "Pay on day five."))
    assert merge_clause_titles(analysis_a, analysis_b) == ["payment terms"]
    assert merge_clause_titles(analysis_b, analysis_a) == ["payment terms"]


def test_build_comparison_input_contains_both_analyses() -> None:
    """Gemini input embeds BOTH analyses (regression: only one document sent)."""
    from app.schemas.analysis_schema import LegalAnalysis

    analysis_a = LegalAnalysis.model_validate(_analysis_payload("Payment Terms", "Pay on day one."))
    analysis_b = LegalAnalysis.model_validate(_analysis_payload("Notice Period", "Thirty days notice."))
    payload = build_comparison_input(analysis_a, analysis_b, "Agreement A", "Offer B")
    assert "Pay on day one." in payload
    assert "Thirty days notice." in payload
    assert "payment terms" in payload and "notice period" in payload


@pytest.mark.asyncio
async def test_compare_success_validates_and_returns_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid Gemini response validates and carries execution metadata."""
    from app.services.compare_service import GeminiCompareResult

    a_id, b_id, rows = _rows()
    service = _service(rows, monkeypatch)
    monkeypatch.setattr(
        service,
        "_generate",
        AsyncMock(return_value=GeminiCompareResult(text=_comparison_json(), model="gemini-2.5-flash", latency_ms=10.0, retry_count=0, fallback_used=False)),
    )
    result, _docs, meta = await service.compare(a_id, b_id, USER_ID)
    assert result.metrics is not None and result.metrics.similarity_score == 80
    assert len(result.clauses) == 1
    assert meta["model"] == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_compare_malformed_gemini_raises_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed Gemini JSON (twice) raises a validation error."""
    from app.services.compare_service import GeminiCompareResult

    a_id, b_id, rows = _rows()
    service = _service(rows, monkeypatch)
    monkeypatch.setattr(
        service,
        "_generate",
        AsyncMock(return_value=GeminiCompareResult(text="not json", model="m", latency_ms=1.0, retry_count=0, fallback_used=False)),
    )
    with pytest.raises(CompareValidationError):
        await service.compare(a_id, b_id, USER_ID)
    assert service._generate.await_count == 2  # initial + one correction retry


@pytest.mark.asyncio
async def test_compare_pending_never_calls_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pending analysis short-circuits before any Gemini call."""
    a_id, b_id, rows = _rows(both_analyzed=False)
    service = _service(rows, monkeypatch)
    spy = AsyncMock()
    monkeypatch.setattr(service, "_generate", spy)
    with pytest.raises(CompareAnalysisPendingError):
        await service.compare(a_id, b_id, USER_ID)
    spy.assert_not_called()


def test_metrics_clamped_to_clause_union() -> None:
    """Invented metric counts are clamped to the deterministic union size."""
    from app.schemas.analysis_schema import LegalAnalysis
    from app.services.compare_service import CompareService as CS

    analysis_a = LegalAnalysis.model_validate(_analysis_payload("Payment Terms", "Pay on day one."))
    analysis_b = LegalAnalysis.model_validate(_analysis_payload("Payment Terms", "Pay on day five."))
    docs = SimpleNamespace(analysis_a=analysis_a, analysis_b=analysis_b)
    inflated = ComparisonResult.model_validate_json(
        ComparisonResult(
            metrics={
                "similarity_score": 80,
                "total_clauses_compared": 999,
                "clauses_matched": 999,
                "clauses_changed": 999,
                "clauses_added": 999,
                "clauses_removed": 999,
                "similarity_justification": "",
            }
        ).model_dump_json()
    )
    fixed = CS._cross_check_metrics(inflated, docs)  # type: ignore[arg-type]
    assert fixed.metrics is not None
    assert fixed.metrics.total_clauses_compared == 1
    assert fixed.metrics.clauses_matched == 1
    assert fixed.metrics.similarity_justification != ""


def test_comparison_repository_cache_miss_on_missing_table() -> None:
    """A missing comparisons table degrades to a cache miss (never raises)."""
    from uuid import uuid4

    from app.repositories.compare_repository import ComparisonRepository

    broken = MagicMock()
    broken.table.side_effect = Exception("relation does not exist")
    repository = ComparisonRepository(broken)
    assert repository.find_cached(uuid4(), uuid4(), USER_ID) is None
    assert repository.save(uuid4(), uuid4(), USER_ID, {}) is None
    assert repository.list_for_user(USER_ID) == []


# -- API contract ---------------------------------------------------------

def _api_client(monkeypatch: pytest.MonkeyPatch, service: Any, repository: Any):  # type: ignore[no-untyped-def]
    """Build a TestClient with auth stubbed and compare boundaries faked."""
    from fastapi.testclient import TestClient

    import app.api.compare as compare_api
    from app.core.security import AuthenticatedUser, get_current_user
    from app.main import app

    monkeypatch.setattr(compare_api, "CompareService", lambda *args: service)
    monkeypatch.setattr(compare_api, "ComparisonRepository", lambda *args: repository)
    monkeypatch.setattr(compare_api, "get_supabase", lambda: MagicMock())
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=USER_ID)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_api_same_document_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /compare with identical ids is rejected (no Gemini call)."""
    doc_id = uuid4()
    service = MagicMock()
    from app.services.compare_service import CompareServiceError as _Same

    service.compare = AsyncMock(side_effect=_Same("Cannot compare a document with itself."))
    repository = MagicMock()
    repository.find_cached.return_value = None
    for client in _api_client(monkeypatch, service, repository):
        response = client.post(
            "/compare", json={"document_a_id": str(doc_id), "document_b_id": str(doc_id)}
        )
    assert response.status_code == 422


def test_api_pending_returns_readiness_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /compare maps pending analysis to 422 with per-document flags."""
    from app.services.compare_service import CompareAnalysisPendingError

    service = MagicMock()
    service.compare = AsyncMock(
        side_effect=CompareAnalysisPendingError(
            "One or more documents are still being analyzed.",
            document_a_ready=True,
            document_b_ready=False,
        )
    )
    repository = MagicMock()
    repository.find_cached.return_value = None
    for client in _api_client(monkeypatch, service, repository):
        response = client.post(
            "/compare", json={"document_a_id": str(uuid4()), "document_b_id": str(uuid4())}
        )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["document_a_ready"] is True
    assert detail["document_b_ready"] is False
    assert detail["retryable"] is True


def test_api_cached_comparison_skips_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cached pair returns 200 with cached=true and never calls the service."""
    from datetime import datetime, timezone

    a_id, b_id = uuid4(), uuid4()
    result_json = ComparisonResult.model_validate_json(_comparison_json()).model_dump(mode="json")
    repository = MagicMock()
    repository.find_cached.return_value = {
        "id": str(uuid4()),
        "result": result_json,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    service = MagicMock()
    service.compare = AsyncMock()
    service._fetch_row = MagicMock(
        side_effect=[
            {"title": "Agreement A", "document_type": "employment"},
            {"title": "Offer B", "document_type": "offer"},
        ]
    )
    for client in _api_client(monkeypatch, service, repository):
        response = client.post(
            "/compare", json={"document_a_id": str(a_id), "document_b_id": str(b_id)}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is True
    assert body["document_a_title"] == "Agreement A"
    assert body["result"]["metrics"]["similarity_score"] == 80
    service.compare.assert_not_called()


def test_api_forbidden_maps_to_403(monkeypatch: pytest.MonkeyPatch) -> None:
    """Another user's document maps to 403 (no existence leak beyond that)."""
    from app.services.compare_service import CompareForbiddenError

    service = MagicMock()
    service.compare = AsyncMock(side_effect=CompareForbiddenError("denied"))
    repository = MagicMock()
    repository.find_cached.return_value = None
    for client in _api_client(monkeypatch, service, repository):
        response = client.post(
            "/compare", json={"document_a_id": str(uuid4()), "document_b_id": str(uuid4())}
        )
    assert response.status_code == 403
