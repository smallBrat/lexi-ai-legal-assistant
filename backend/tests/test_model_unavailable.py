"""Tests for Gemini overload recovery: retry, failure state, and 503 contract."""

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from google.genai import _extra_utils, types
from google.genai.errors import ClientError, ServerError

from app.api import analyze as analyze_api
from app.core.security import AuthenticatedUser, get_current_user
from app.main import app
from app.schemas.chat_schema import ChatResponse
from app.services.analysis_service import AnalysisService
from app.services.chat_service import ChatService
from app.services.gemini_service import (
    MODEL_PRIORITY,
    GeminiService,
    GeminiServiceError,
    ModelUnavailableError,
)

USER_ID = "user-123"


def make_gemini_service(monkeypatch: pytest.MonkeyPatch, fake_generate: AsyncMock) -> GeminiService:
    """Build a GeminiService with a faked async generate_content boundary."""
    monkeypatch.setattr(
        "app.services.gemini_provider.get_gemini_client", lambda: MagicMock()
    )
    service = GeminiService()
    service._client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate))
    )
    return service


@pytest.mark.asyncio
async def test_all_models_exhausted_raises_model_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry each model once on 503, then raise with overload context."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    fake = AsyncMock(
        side_effect=ServerError(503, {"error": {"message": "overloaded"}}, None)
    )
    service = make_gemini_service(monkeypatch, fake)

    with pytest.raises(ModelUnavailableError) as exc_info:
        await service._generate("some document text")

    err = exc_info.value
    assert err.attempted_models == MODEL_PRIORITY
    assert err.last_model == MODEL_PRIORITY[-1]
    assert err.last_status_code == 503
    assert err.retryable is True
    # One retry per model: 3 models x 2 attempts.
    assert fake.await_count == len(MODEL_PRIORITY) * 2


@pytest.mark.asyncio
async def test_retry_uses_exponential_backoff_with_jitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backoff grows exponentially between attempts."""
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    fake = AsyncMock(side_effect=asyncio.TimeoutError())
    service = make_gemini_service(monkeypatch, fake)

    with pytest.raises(ModelUnavailableError):
        await service._generate("some document text")

    assert len(sleeps) == len(MODEL_PRIORITY)
    assert sleeps[0] >= 2.0


@pytest.mark.asyncio
async def test_client_400_is_never_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail fast on 400/401/403 without retrying or switching models."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    fake = AsyncMock(side_effect=ClientError(400, {"error": {"message": "bad"}}, None))
    service = make_gemini_service(monkeypatch, fake)

    with pytest.raises(GeminiServiceError):
        await service._generate("some document text")

    assert fake.await_count == 1


@pytest.mark.asyncio
async def test_analysis_config_disables_afc(monkeypatch: pytest.MonkeyPatch) -> None:
    """The analysis generate_content call must skip the AFC code path."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    fake = AsyncMock(side_effect=asyncio.TimeoutError())
    service = make_gemini_service(monkeypatch, fake)

    with pytest.raises(ModelUnavailableError):
        await service._generate("some document text")

    config = fake.await_args.kwargs["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert _extra_utils.should_disable_afc(config) is True


@pytest.mark.asyncio
async def test_chat_config_disables_afc(monkeypatch: pytest.MonkeyPatch) -> None:
    """The chat generate_content call must skip the AFC code path."""
    monkeypatch.setattr(
        "app.services.gemini_provider.get_gemini_client", lambda: MagicMock()
    )
    captured: dict[str, Any] = {}

    async def fake_generate(*args: Any, **kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            text=ChatResponse(
                answer="Found it.",
                confidence_score=0,
                citations=[],
                follow_up_questions=[],
            ).model_dump_json()
        )

    service = ChatService(MagicMock(), MagicMock())
    service._gemini = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(generate_content=fake_generate)
        )
    )

    await service._generate("What is the rent?", [])

    config = captured["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert _extra_utils.should_disable_afc(config) is True


class SupabaseFailureDouble:
    """Capture the update chain used to persist the failure state."""

    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document
        self.updates: list[dict[str, Any]] = []
        self.query = MagicMock()
        self.query.select.return_value = self.query
        self.query.eq.return_value = self.query
        self.query.limit.return_value = self.query
        self.query.update.side_effect = self._update
        self.query.execute.side_effect = self._execute
        self.client = MagicMock()
        self.client.table.return_value = self.query
        self._calls = 0

    def _update(self, values: dict[str, Any]) -> MagicMock:
        self.updates.append(values)
        return self.query

    def _execute(self) -> SimpleNamespace:
        self._calls += 1
        if self._calls == 1:
            return SimpleNamespace(data=[self.document])
        return SimpleNamespace(data=[{"id": self.document["id"]}])


@pytest.mark.asyncio
async def test_overload_persists_analysis_failed_without_touching_analysis() -> None:
    """ exhaustion marks the row analysis_failed and keeps analysis intact."""
    document_id = uuid4()
    database = SupabaseFailureDouble(
        {
            "id": str(document_id),
            "user_id": USER_ID,
            "document_type": "rental",
            "extracted_text": "The tenant must pay rent.",
            "analysis": None,
        }
    )
    gemini = MagicMock(spec=GeminiService)
    gemini.analyze_document = AsyncMock(
        side_effect=ModelUnavailableError(
            "overloaded",
            attempted_models=list(MODEL_PRIORITY),
            last_model=MODEL_PRIORITY[-1],
            last_status_code=503,
            failure_reason="server_error",
        )
    )
    service = AnalysisService(database.client, gemini)

    with pytest.raises(ModelUnavailableError):
        await service.analyze_document(document_id, USER_ID)

    assert database.updates
    stored = database.updates[-1]
    assert stored["status"] == "analysis_failed"
    assert "analysis" not in stored
    metadata = stored["analysis_metadata"]
    assert metadata["error"] == "MODEL_UNAVAILABLE"
    assert metadata["retryable"] is True
    assert metadata["last_model"] == MODEL_PRIORITY[-1]
    assert metadata["attempted_models"] == list(MODEL_PRIORITY)
    assert metadata["failed_at"].endswith("+00:00")


@pytest.mark.asyncio
async def test_failed_retry_never_overwrites_successful_analysis() -> None:
    """A forced retry that fails keeps the existing analysis and status."""
    from app.services.analysis_service import LegalAnalysis

    document_id = uuid4()
    existing = LegalAnalysis(
        summary="Cached.",
        plain_english_summary="Cached plain English.",
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
    ).model_dump(mode="json")
    database = SupabaseFailureDouble(
        {
            "id": str(document_id),
            "user_id": USER_ID,
            "document_type": "rental",
            "extracted_text": "The tenant must pay rent.",
            "analysis": existing,
        }
    )
    gemini = MagicMock(spec=GeminiService)
    gemini.analyze_document = AsyncMock(
        side_effect=ModelUnavailableError(
            "overloaded",
            attempted_models=list(MODEL_PRIORITY),
            last_model=MODEL_PRIORITY[-1],
            last_status_code=503,
            failure_reason="server_error",
        )
    )
    service = AnalysisService(database.client, gemini)

    with pytest.raises(ModelUnavailableError):
        await service.analyze_document(document_id, USER_ID, force=True)

    stored = database.updates[-1]
    assert "status" not in stored
    assert "analysis" not in stored
    assert stored["analysis_metadata"]["error"] == "MODEL_UNAVAILABLE"


def test_api_returns_retryable_503_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Map model exhaustion to the structured 503 contract."""
    document_id = uuid4()
    service = MagicMock()
    service.analyze_document = AsyncMock(
        side_effect=ModelUnavailableError(
            "overloaded",
            attempted_models=list(MODEL_PRIORITY),
            last_model=MODEL_PRIORITY[-1],
            last_status_code=503,
            failure_reason="server_error",
        )
    )
    monkeypatch.setattr(analyze_api, "AnalysisService", lambda *args: service)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=USER_ID)
    try:
        with TestClient(app) as client:
            response = client.post(f"/analyze/{document_id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "AI analysis is temporarily unavailable.",
        "retryable": True,
        "error_code": "MODEL_UNAVAILABLE",
    }
    assert "traceback" not in response.text.lower()


def test_health_returns_ok() -> None:
    """Expose the lightweight health contract for the frontend."""
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "lexi-ai-backend"}
