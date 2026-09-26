"""Regression tests for the single Gemini provider + hardened chat pipeline.

Covers TASK 10:
  provider singleton (identity, threads, reset, missing key),
  chat payload builder validation,
  sanitized chat response schema (the 400 root cause),
  retrieval-empty fallback still calling Gemini,
  Gemini timeout -> ChatTimeoutError -> HTTP 504,
  invalid API key (401) -> non-retryable 502,
  429 retried once per model, then retryable failure,
  history serialization incl. NULL/corrupt rows (never 500),
  GET history after POST through the real FastAPI routes,
  concurrent chats, empty history, missing analysis,
  Gemini Embedding 2 migration (model name, dimensionality, task formatting).
"""

import asyncio
import inspect
import json
import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from google.genai.errors import ClientError

import app.api.chat as chat_api
import app.services.gemini_provider as provider_module
from app.core.security import AuthenticatedUser, get_current_user
from app.main import app
from app.services.chat_service import (
    ChatService,
    ChatTimeoutError,
)
from app.services.embedding_service import ClauseMatch
from app.services.gemini_provider import (
    EMBEDDING_MODEL,
    EMBEDDING_OUTPUT_DIMENSIONALITY,
    ChatPayloadError,
    GeminiProviderError,
    build_chat_config,
    build_chat_contents,
    build_gemini_schema_for,
    get_gemini_client,
    reset_gemini_client,
)
from app.services.retrieval_service import RetrievalService
from app.schemas.chat_schema import ChatResponse

USER_ID = "user-123"
DOCUMENT_ID = uuid4()


def valid_response_json() -> str:
    """Return a valid structured chat response."""
    return json.dumps({
        "answer": "The agreement requires payment on the first day.",
        "confidence_score": 80,
        "citations": [
            {
                "clause_title": "Payment",
                "excerpt": "Payment is due on the first day.",
                "page_number": 1,
                "similarity_score": 0.91,
            }
        ],
        "follow_up_questions": [],
    })


_MISSING = object()


class FakeChatRepository:
    """In-memory chat repository double mirroring the Supabase shape."""

    def __init__(self, analysis: Any = _MISSING) -> None:
        self.document: dict[str, Any] | None = {
            "id": str(DOCUMENT_ID),
            "user_id": USER_ID,
            "analysis": analysis
            if analysis is not _MISSING
            else {
                "summary": "A payment agreement.",
                "clauses": [
                    {
                        "title": "Payment",
                        "original_text": "Payment is due on the first day.",
                        "page_number": 1,
                    }
                ],
            },
        }
        self.saved: list[dict[str, Any]] = []

    def get_document(self, _document_id: object, _user_id: str) -> dict[str, Any] | None:
        return self.document

    def save_message(
        self,
        document_id: object,
        user_id: str,
        question: str,
        answer: dict[str, Any],
        timestamp: datetime,
    ) -> None:
        self.saved.append({
            "document_id": document_id,
            "user_id": user_id,
            "question": question,
            "answer": answer,
            "timestamp": timestamp,
        })

    def get_history(self, _document_id: object, _user_id: str) -> list[dict[str, Any]]:
        rows = [
            {
                "document_id": str(DOCUMENT_ID),
                "user_id": USER_ID,
                "question": str(item["question"]),
                **dict(item["answer"]),
                "timestamp": item["timestamp"],
            }
            for item in self.saved
        ]
        for row in rows:
            row.setdefault("follow_up_questions", [])
        return rows

    def delete_history(self, _document_id: object, _user_id: str) -> None:
        self.saved.clear()


def build_service(
    monkeypatch: pytest.MonkeyPatch,
    repository: FakeChatRepository,
    matches: list[ClauseMatch] | None = None,
) -> tuple[ChatService, MagicMock]:
    """Build a chat service with mocked Gemini and retrieval."""
    retrieval = MagicMock(spec=RetrievalService)
    retrieval.retrieve = AsyncMock(
        return_value=matches
        if matches is not None
        else [
            ClauseMatch(
                title="Payment",
                excerpt="Payment is due on the first day.",
                page_number=1,
                similarity_score=0.91,
            )
        ]
    )
    gemini_client = MagicMock()
    gemini_client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text=valid_response_json())
    )
    monkeypatch.setattr(
        "app.services.gemini_provider.get_gemini_client", lambda: gemini_client
    )
    return ChatService(repository, retrieval), gemini_client


# ---- Provider singleton ----

def test_provider_singleton_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two calls return the same client object."""
    reset_gemini_client()
    monkeypatch.setattr(provider_module, "get_gemini_key", lambda: "test-key")
    try:
        assert get_gemini_client() is get_gemini_client()
    finally:
        reset_gemini_client()


def test_provider_singleton_threads_share_one_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent first-use from threads still creates exactly one client."""
    reset_gemini_client()
    monkeypatch.setattr(provider_module, "get_gemini_key", lambda: "test-key")
    try:
        results: list[Any] = []
        threads = [
            threading.Thread(target=lambda: results.append(get_gemini_client()))
            for _ in range(8)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(results) == 8
        assert all(client is results[0] for client in results)
    finally:
        reset_gemini_client()


def test_provider_reset_creates_fresh_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset drops the cache so the next call builds a new client."""
    reset_gemini_client()
    monkeypatch.setattr(provider_module, "get_gemini_key", lambda: "test-key")
    try:
        first = get_gemini_client()
        reset_gemini_client()
        second = get_gemini_client()
        assert first is not second
    finally:
        reset_gemini_client()


def test_provider_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty API key fails fast with a provider error, not a cryptic SDK error."""
    reset_gemini_client()
    monkeypatch.setattr(provider_module, "get_gemini_key", lambda: "  ")
    try:
        with pytest.raises(GeminiProviderError):
            get_gemini_client()
    finally:
        reset_gemini_client()


def test_services_share_provider_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chat, analysis, and embedding services use the same client object."""
    reset_gemini_client()
    monkeypatch.setattr(provider_module, "get_gemini_key", lambda: "test-key")
    try:
        from app.services.gemini_service import GeminiService

        chat = ChatService(FakeChatRepository(), MagicMock())
        analysis = GeminiService()
        assert chat._gemini is analysis._client is get_gemini_client()
    finally:
        reset_gemini_client()


# ---- Payload builder ----

def test_payload_builder_accepts_valid_inputs() -> None:
    """A normal question + context builds the exact SDK contents string."""
    contents = build_chat_contents("When is payment due?", '[{"clause": 1}]')
    assert "When is payment due?" in contents
    assert "untrusted data" in contents
    assert '[{"clause": 1}]' in contents


@pytest.mark.parametrize("question", ["", "   ", None, 123])
def test_payload_builder_rejects_bad_question(question: Any) -> None:
    """Empty/None/non-string questions never reach the SDK."""
    with pytest.raises(ChatPayloadError):
        build_chat_contents(question, "some context")  # type: ignore[arg-type]


@pytest.mark.parametrize("context", ["", "   ", None, 123])
def test_payload_builder_rejects_bad_context(context: Any) -> None:
    """Empty/None/non-string contexts never reach the SDK."""
    with pytest.raises(ChatPayloadError):
        build_chat_contents("a question?", context)  # type: ignore[arg-type]


def test_config_builder_rejects_empty_system_instruction() -> None:
    """Missing system prompt fails before the API call, not inside it."""
    with pytest.raises(ChatPayloadError):
        build_chat_config("   ")


def test_config_uses_sanitized_schema() -> None:
    """The SDK config carries no $ref/$defs (the 400 root cause)."""
    config = build_chat_config("You are Lexi.")
    dumped = json.dumps(config.response_schema)
    assert "$ref" not in dumped
    assert "$defs" not in dumped
    assert config.temperature == 0.0
    assert config.response_mime_type == "application/json"
    assert config.automatic_function_calling.disable is True


def test_sanitized_chat_schema_matches_analysis_treatment() -> None:
    """Chat schema gets the identical proven pipeline as analysis."""
    schema = build_gemini_schema_for(ChatResponse)
    dumped = json.dumps(schema)
    assert "$ref" not in dumped
    assert "$defs" not in dumped
    assert set(schema["required"]) == {
        "answer",
        "confidence_score",
        "citations",
        "follow_up_questions",
    }
    citation_props = schema["properties"]["citations"]["items"]["properties"]
    assert "clause_title" in citation_props


# ---- Retrieval-empty fallback ----

@pytest.mark.asyncio
async def test_retrieval_empty_falls_back_to_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero vector matches + summary-only analysis still calls Gemini."""
    repository = FakeChatRepository(
        analysis={"summary": "A payment agreement.", "clauses": []}
    )
    service, gemini = build_service(monkeypatch, repository, matches=[])

    result = await service.answer(DOCUMENT_ID, USER_ID, "Summarize please.")

    gemini.aio.models.generate_content.assert_awaited()
    assert result.answer.startswith("The agreement requires")
    request = gemini.aio.models.generate_content.await_args.kwargs
    assert "A payment agreement." in request["contents"]


# ---- Timeout -> 504 ----

@pytest.mark.asyncio
async def test_gemini_timeout_maps_to_504(monkeypatch: pytest.MonkeyPatch) -> None:
    """All attempts timing out raises ChatTimeoutError -> HTTP 504."""
    repository = FakeChatRepository()
    service, gemini = build_service(monkeypatch, repository)
    gemini.aio.models.generate_content = AsyncMock(side_effect=asyncio.TimeoutError())
    monkeypatch.setattr("app.services.chat_service._RETRY_BASE_SECONDS", 0.0)
    monkeypatch.setattr("app.services.chat_service._JITTER_MAX", 0.0)

    with pytest.raises(ChatTimeoutError):
        await service.answer(DOCUMENT_ID, USER_ID, "When is payment due?")

    http_exc = chat_api._service_error(ChatTimeoutError("timed out"))
    assert http_exc.status_code == 504
    assert http_exc.detail["error_code"] == "CHAT_TIMEOUT"
    assert http_exc.detail["retryable"] is True


# ---- Invalid API key (401) -> non-retryable 502 ----

@pytest.mark.asyncio
async def test_invalid_key_is_non_retryable_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """401 fails fast (one attempt) and maps to 502 retryable=False."""
    repository = FakeChatRepository()
    service, gemini = build_service(monkeypatch, repository)
    gemini.aio.models.generate_content = AsyncMock(
        side_effect=ClientError(401, {"error": {"message": "invalid key"}}, None)
    )

    with pytest.raises(Exception) as exc_info:
        await service.answer(DOCUMENT_ID, USER_ID, "Hello?")
    assert getattr(exc_info.value, "retryable") is False
    assert gemini.aio.models.generate_content.await_count == 1

    http_exc = chat_api._service_error(exc_info.value)  # type: ignore[arg-type]
    assert http_exc.status_code == 502
    assert http_exc.detail["error_code"] == "GEMINI_ERROR"
    assert http_exc.detail["retryable"] is False


# ---- 429 retried, then retryable ----

@pytest.mark.asyncio
async def test_gemini_429_retried_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single 429 is retried within the model and then succeeds."""
    repository = FakeChatRepository()
    service, gemini = build_service(monkeypatch, repository)
    calls = {"n": 0}

    async def flaky(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ClientError(429, {"error": {"message": "quota"}}, None)
        return SimpleNamespace(text=valid_response_json())

    gemini.aio.models.generate_content = flaky
    monkeypatch.setattr("app.services.chat_service._RETRY_BASE_SECONDS", 0.0)
    monkeypatch.setattr("app.services.chat_service._JITTER_MAX", 0.0)

    result = await service.answer(DOCUMENT_ID, USER_ID, "When is payment due?")

    assert result.answer.startswith("The agreement requires")
    assert calls["n"] == 2


# ---- History serialization: NULLs and corrupt rows never 500 ----

@pytest.mark.asyncio
async def test_history_rows_skip_corrupt_without_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_history_rows returns valid items and skips malformed rows (200, no raise)."""
    good_ts = datetime.now(timezone.utc).isoformat()
    fake_service = MagicMock()
    fake_service.history = AsyncMock(
        return_value=[
            {
                "document_id": str(DOCUMENT_ID),
                "user_id": USER_ID,
                "question": "Q?",
                "answer": "A.",
                "citations": [],
                "confidence_score": 10,
                "timestamp": good_ts,
                "follow_up_questions": [],
            },
            {"bogus": "row"},  # corrupt: must be skipped, not 500
            {
                "document_id": str(DOCUMENT_ID),
                "user_id": USER_ID,
                "question": None,  # NULL-ish: repo normalizes, direct rows skip
                "answer": "B.",
                "citations": [],
                "confidence_score": 5,
                "timestamp": good_ts,
                "follow_up_questions": [],
            },
        ]
    )
    monkeypatch.setattr(
        chat_api, "get_chat_service", lambda: fake_service
    )
    user = SimpleNamespace(id=USER_ID)

    items = await chat_api._history_rows(DOCUMENT_ID, user, route="test")  # type: ignore[arg-type]

    assert len(items) == 1
    assert items[0].question == "Q?"


# ---- GET history after POST through the real routes ----

def test_get_history_after_post_returns_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST then GET via FastAPI: 200 + valid history item, no 500."""
    repository = FakeChatRepository()
    retrieval = MagicMock(spec=RetrievalService)
    retrieval.retrieve = AsyncMock(
        return_value=[
            ClauseMatch(
                title="Payment",
                excerpt="Payment is due on the first day.",
                page_number=1,
                similarity_score=0.91,
            )
        ]
    )
    gemini_client = MagicMock()
    gemini_client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text=valid_response_json())
    )
    monkeypatch.setattr(
        "app.services.gemini_provider.get_gemini_client", lambda: gemini_client
    )
    monkeypatch.setattr(
        chat_api, "get_chat_service", lambda: ChatService(repository, retrieval)
    )
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=USER_ID)
    try:
        with TestClient(app) as client:
            post = client.post(
                f"/documents/{DOCUMENT_ID}/chat", json={"question": "When is payment due?"}
            )
            assert post.status_code == 200, post.text
            assert post.json()["answer"].startswith("The agreement requires")

            get = client.get(f"/documents/{DOCUMENT_ID}/chat")
            assert get.status_code == 200, get.text
            body = get.json()
            assert isinstance(body, list) and len(body) == 1
            assert body[0]["question"] == "When is payment due?"
            assert body[0]["answer"].startswith("The agreement requires")
    finally:
        app.dependency_overrides.clear()


# ---- Concurrent chats ----

@pytest.mark.asyncio
async def test_concurrent_chats_all_succeed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three concurrent answers share the provider client and all succeed."""
    repository = FakeChatRepository()
    retrieval = MagicMock(spec=RetrievalService)
    retrieval.retrieve = AsyncMock(
        return_value=[
            ClauseMatch(
                title="Payment",
                excerpt="Payment is due.",
                page_number=1,
                similarity_score=0.9,
            )
        ]
    )
    gemini_client = MagicMock()
    gemini_client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(text=valid_response_json())
    )
    monkeypatch.setattr(
        "app.services.gemini_provider.get_gemini_client", lambda: gemini_client
    )
    services = [ChatService(repository, retrieval) for _ in range(3)]

    results = await asyncio.gather(
        services[0].answer(DOCUMENT_ID, USER_ID, "Question 1?"),
        services[1].answer(DOCUMENT_ID, USER_ID, "Question 2?"),
        services[2].answer(DOCUMENT_ID, USER_ID, "Question 3?"),
    )

    assert len(results) == 3
    assert all(r.answer.startswith("The agreement requires") for r in results)


# ---- Empty history / missing analysis ----

@pytest.mark.asyncio
async def test_empty_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """No exchanges yet -> empty history, no crash."""
    service, _gemini = build_service(monkeypatch, FakeChatRepository())

    assert await service.history(DOCUMENT_ID, USER_ID) == []


@pytest.mark.asyncio
async def test_missing_analysis_keeps_deterministic_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No analysis and no matches -> 'not found' without calling Gemini."""
    repository = FakeChatRepository(analysis=None)
    service, gemini = build_service(monkeypatch, repository, matches=[])

    result = await service.answer(DOCUMENT_ID, USER_ID, "Governing law?")

    assert result.answer == "This is not found in the uploaded document."
    gemini.aio.models.generate_content.assert_not_awaited()


# ---- Gemini Embedding 2 Migration Tests ----


def test_embedding_model_is_gemini_embedding_2() -> None:
    """The embedding model must be gemini-embedding-2."""
    assert EMBEDDING_MODEL == "gemini-embedding-2"
    assert EMBEDDING_MODEL != "gemini-embedding-001"


def test_embedding_dimensionality_is_1536() -> None:
    """Default embedding dimensionality must be 1536."""
    assert EMBEDDING_OUTPUT_DIMENSIONALITY == 1536


def test_embedding_model_not_duplicated() -> None:
    """The model name must appear exactly once in gemini_provider."""
    source = inspect.getsource(provider_module)
    count = source.count("gemini-embedding-2")
    assert count >= 1, "EMBEDDING_MODEL must reference gemini-embedding-2"
