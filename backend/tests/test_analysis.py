"""Tests for the AI legal document analysis engine."""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.schemas.analysis_schema import LegalAnalysis
from app.services.analysis_service import (
    AnalysisDatabaseError,
    AnalysisService,
    AnalysisValidationError,
    EmptyDocumentError,
)
from app.services.gemini_service import GeminiService, GeminiTimeoutError

USER_ID = "user-123"


def valid_analysis_json() -> str:
    """Return valid Gemini JSON for the analysis contract."""
    return LegalAnalysis(
        summary="A rental agreement.",
        plain_english_summary="This document describes a rental arrangement.",
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
    ).model_dump_json()


class SupabaseDocumentsDouble:
    """Capture the Supabase query chain used by AnalysisService."""

    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document
        self.inserted_updates: list[dict[str, Any]] = []
        self.query = MagicMock()
        self.query.select.return_value = self.query
        self.query.eq.return_value = self.query
        self.query.limit.return_value = self.query
        self.query.update.side_effect = self._update
        self.query.execute.side_effect = self._execute
        self.client = MagicMock()
        self.client.table.return_value = self.query
        self._execute_count = 0

    def _update(self, values: dict[str, Any]) -> MagicMock:
        """Capture update values and preserve the fluent query chain."""
        self.inserted_updates.append(values)
        return self.query

    def _execute(self) -> SimpleNamespace:
        """Return the document first, then a successful update response."""
        self._execute_count += 1
        if self._execute_count == 1:
            return SimpleNamespace(data=[self.document])
        return SimpleNamespace(data=[{"id": self.document.get("id", str(uuid4()))}])


@pytest.fixture
def service_factory() -> Iterator[tuple[Any, MagicMock, UUID]]:
    """Provide an analysis service with mocked database and Gemini boundaries."""
    document_id = uuid4()
    database = SupabaseDocumentsDouble(
        {
            "id": str(document_id),
            "user_id": USER_ID,
            "document_type": "rental",
            "extracted_text": "The tenant must pay rent on the first day.",
            "analysis": None,
        }
    )
    gemini = MagicMock(spec=GeminiService)
    gemini.analyze_document = AsyncMock(return_value=valid_analysis_json())
    yield AnalysisService(database.client, gemini), database, document_id


@pytest.mark.asyncio
async def test_successful_json_validation(
    service_factory: tuple[AnalysisService, SupabaseDocumentsDouble, UUID],
) -> None:
    """Validate a well-formed Gemini response and return typed analysis."""
    service, _database, document_id = service_factory

    result = await service.analyze_document(document_id, USER_ID)

    assert isinstance(result, LegalAnalysis)
    assert result.document_type == "rental"
    assert result.risk_level == "low"
    service._gemini_service.analyze_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_gemini_response_retries_once(
    service_factory: tuple[AnalysisService, SupabaseDocumentsDouble, UUID],
) -> None:
    """Retry once when Gemini returns malformed JSON, then raise a typed error."""
    service, _database, document_id = service_factory
    service._gemini_service.analyze_document = AsyncMock(
        side_effect=["not-json", "still-not-json"]
    )

    with pytest.raises(AnalysisValidationError):
        await service.analyze_document(document_id, USER_ID)

    assert service._gemini_service.analyze_document.await_count == 2
    correction = service._gemini_service.analyze_document.await_args_list[1].kwargs[
        "correction"
    ]
    assert "validation errors" in correction


@pytest.mark.asyncio
async def test_missing_required_field_retries_and_fails(
    service_factory: tuple[AnalysisService, SupabaseDocumentsDouble, UUID],
) -> None:
    """Reject JSON that remains invalid after the validation retry."""
    service, _database, document_id = service_factory
    incomplete = '{"plain_english_summary":"Only one field"}'
    service._gemini_service.analyze_document = AsyncMock(
        side_effect=[incomplete, incomplete]
    )

    with pytest.raises(AnalysisValidationError):
        await service.analyze_document(document_id, USER_ID)

    assert service._gemini_service.analyze_document.await_count == 2


@pytest.mark.asyncio
async def test_empty_document_does_not_call_gemini(
    service_factory: tuple[AnalysisService, SupabaseDocumentsDouble, UUID],
) -> None:
    """Reject documents without extracted text before invoking Gemini."""
    service, database, document_id = service_factory
    database.document["extracted_text"] = "   "

    with pytest.raises(EmptyDocumentError):
        await service.analyze_document(document_id, USER_ID)

    service._gemini_service.analyze_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_long_document_is_forwarded_without_truncation(
    service_factory: tuple[AnalysisService, SupabaseDocumentsDouble, UUID],
) -> None:
    """Pass a long extracted document to Gemini without silently truncating it."""
    service, database, document_id = service_factory
    long_document = "Lease terms and payment obligations. " * 10_000
    database.document["extracted_text"] = long_document

    await service.analyze_document(document_id, USER_ID)

    sent_text = service._gemini_service.analyze_document.await_args.args[0]
    assert sent_text == long_document.strip()
    assert len(sent_text) > 300_000


@pytest.mark.asyncio
async def test_gemini_timeout_is_propagated(
    service_factory: tuple[AnalysisService, SupabaseDocumentsDouble, UUID],
) -> None:
    """Propagate a Gemini timeout for the API layer to map to HTTP 504."""
    service, _database, document_id = service_factory
    service._gemini_service.analyze_document = AsyncMock(
        side_effect=GeminiTimeoutError("timeout")
    )

    with pytest.raises(GeminiTimeoutError):
        await service.analyze_document(document_id, USER_ID)


@pytest.mark.asyncio
async def test_database_persistence_stores_analysis_metadata(
    service_factory: tuple[AnalysisService, SupabaseDocumentsDouble, UUID],
) -> None:
    """Persist validated analysis with model and prompt metadata."""
    service, database, document_id = service_factory

    result = await service.analyze_document(document_id, USER_ID)

    assert database.inserted_updates
    stored = database.inserted_updates[-1]
    assert stored["analysis"] == result.model_dump(mode="json")
    assert stored["analysis_model"] == "gemini-2.5-flash"
    assert stored["analysis_prompt_version"] == "legal-analysis-v3"
    assert "analyzed_at" in stored


@pytest.mark.asyncio
async def test_database_failure_is_reported(
    service_factory: tuple[AnalysisService, SupabaseDocumentsDouble, UUID],
) -> None:
    """Raise the service database error when persistence fails."""
    service, database, document_id = service_factory
    database.query.execute.side_effect = [
        SimpleNamespace(data=[database.document]),
        RuntimeError("database unavailable"),
    ]

    with pytest.raises(AnalysisDatabaseError):
        await service.analyze_document(document_id, USER_ID)
