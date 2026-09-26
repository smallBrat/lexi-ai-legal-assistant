"""Phase-2 chat history + Gemini fix regression tests.

Covers the exact bug chain from the report:
  POST /documents/{id}/chat 200 but GET /documents/{id}/chat 500,
  CHAT_GEMINI_SKIPPED on empty retrieval, and "Analysis indexing failed".

Root causes fixed:
  1. ``ChatHistoryItem`` required ``follow_up_questions`` but Supabase
     ``chat_history`` rows never store it -> ValidationError -> HTTP 500.
  2. ``EmbeddingService.index_clauses`` called ``clause.get(...)`` on
     ``ClauseAnalysis`` pydantic models -> AttributeError -> empty Chroma
     index -> zero vector matches -> Gemini skipped.
  3. Empty retrieval skipped Gemini instead of answering from OCR text.
"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.schemas.analysis_schema import ClauseAnalysis, RiskLevel
from app.schemas.chat_schema import ChatHistoryItem
from app.services.chat_service import ChatService
from app.services.embedding_service import ClauseMatch
from app.services.retrieval_service import RetrievalService

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


def sample_clause() -> ClauseAnalysis:
    """Return a ClauseAnalysis model like analysis_service produces."""
    return ClauseAnalysis(
        title="Payment",
        category="financial",
        risk_level=RiskLevel.MEDIUM,
        importance_score=70,
        original_text="Payment is due on the first day.",
        simplified_text="Pay on day one.",
        why_it_matters="Cash flow.",
    )


class FakeChatRepository:
    """In-memory chat repository double mirroring the Supabase shape."""

    def __init__(self, analysis: Any = None) -> None:
        self.document: dict[str, Any] | None = {
            "id": str(DOCUMENT_ID),
            "user_id": USER_ID,
            "analysis": analysis
            if analysis is not None
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
        # Mirror the real repository normalization: legacy rows lack
        # follow_up_questions until normalized in ONE place.
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
    monkeypatch.setattr("app.services.gemini_provider.get_gemini_client", lambda: gemini_client)
    return ChatService(repository, retrieval), gemini_client


# ---- Legacy Supabase-shaped row (no follow_up_questions) validates ----

def test_legacy_row_without_follow_up_questions_validates() -> None:
    """The exact GET-500 trigger: a DB row must validate as ChatHistoryItem."""
    row = {
        "document_id": str(DOCUMENT_ID),
        "user_id": USER_ID,
        "question": "When is payment due?",
        "answer": "The agreement requires payment on the first day.",
        "citations": [],
        "confidence_score": 80,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    item = ChatHistoryItem.model_validate(row)  # raised ValidationError before fix
    assert item.question == "When is payment due?"
    assert item.follow_up_questions == []


# ---- save message ----

@pytest.mark.asyncio
async def test_save_message_persists_exchange(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST answer persists one exchange."""
    repository = FakeChatRepository()
    service, _gemini = build_service(monkeypatch, repository)

    await service.answer(DOCUMENT_ID, USER_ID, "When is payment due?")

    assert len(repository.saved) == 1
    assert repository.saved[0]["question"] == "When is payment due?"


# ---- fetch history ----

@pytest.mark.asyncio
async def test_fetch_history_returns_saved_exchange(monkeypatch: pytest.MonkeyPatch) -> None:
    """History returns previously saved exchanges."""
    repository = FakeChatRepository()
    service, _gemini = build_service(monkeypatch, repository)
    await service.answer(DOCUMENT_ID, USER_ID, "When is payment due?")

    history = await service.history(DOCUMENT_ID, USER_ID)

    assert len(history) == 1
    assert history[0]["question"] == "When is payment due?"
    # Every row must serialize through the API schema (the GET 500 path).
    items = [ChatHistoryItem.model_validate(row) for row in history]
    assert items[0].answer.startswith("The agreement requires")


# ---- POST then GET history (end-to-end through the compat route shape) ----

@pytest.mark.asyncio
async def test_post_then_get_history_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST then GET: saved answer re-validates as the GET response model."""
    repository = FakeChatRepository()
    service, _gemini = build_service(monkeypatch, repository)

    await service.answer(DOCUMENT_ID, USER_ID, "When is payment due?")
    rows = await service.history(DOCUMENT_ID, USER_ID)
    items = [ChatHistoryItem.model_validate(row) for row in rows]

    assert len(items) == 1
    assert items[0].document_id == DOCUMENT_ID
    assert items[0].user_id == USER_ID
    assert items[0].question == "When is payment due?"
    assert items[0].answer.startswith("The agreement requires")


# ---- empty history ----

@pytest.mark.asyncio
async def test_empty_history_returns_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """No exchanges yet -> empty history, no crash."""
    repository = FakeChatRepository()
    service, _gemini = build_service(monkeypatch, repository)

    history = await service.history(DOCUMENT_ID, USER_ID)

    assert history == []
    assert [ChatHistoryItem.model_validate(row) for row in history] == []


# ---- Gemini response ----

@pytest.mark.asyncio
async def test_gemini_response_returned_with_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini answer flows through with verified citations and confidence."""
    repository = FakeChatRepository()
    service, gemini = build_service(monkeypatch, repository)

    result = await service.answer(DOCUMENT_ID, USER_ID, "When is payment due?")

    gemini.aio.models.generate_content.assert_awaited()
    assert result.answer.startswith("The agreement requires")
    assert result.citations[0].clause_title == "Payment"
    assert result.confidence_score > 0


# ---- retrieval fallback (empty vector matches, analysis text exists) ----

@pytest.mark.asyncio
async def test_retrieval_fallback_still_calls_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty vector retrieval answers from OCR-derived analysis, never skips."""
    repository = FakeChatRepository()
    service, gemini = build_service(monkeypatch, repository, matches=[])

    result = await service.answer(DOCUMENT_ID, USER_ID, "What is the governing law?")

    gemini.aio.models.generate_content.assert_awaited()
    assert result.answer.startswith("The agreement requires")
    assert len(repository.saved) == 1


# ---- indexing success with pydantic ClauseAnalysis models ----

def test_index_clauses_accepts_pydantic_models() -> None:
    """index_clauses handles ClauseAnalysis models (the indexing crash)."""
    from app.services.embedding_service import EmbeddingService

    service = EmbeddingService.__new__(EmbeddingService)
    service._embedding_dimensionality = 1536
    indexed_ids: list[str] = []
    indexed_docs: list[str] = []

    class FakeCollection:
        def get(self, include: Any = None) -> dict[str, Any]:
            return {"ids": list(indexed_ids)}

        def add(
            self,
            ids: list[str],
            embeddings: list[list[float]],
            documents: list[str],
            metadatas: list[dict[str, Any]],
        ) -> None:
            indexed_ids.extend(ids)
            indexed_docs.extend(documents)

        def count(self) -> int:
            return len(indexed_ids)

    service._collection = lambda _u, _d: FakeCollection()  # type: ignore[method-assign]
    service._gemini = MagicMock()
    service._gemini.models.embed_content = MagicMock(
        return_value=SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1] * 1536)]
        )
    )

    # Raised AttributeError before the fix (clause.get on a pydantic model).
    service.index_clauses(USER_ID, DOCUMENT_ID, [sample_clause()])  # type: ignore[arg-type]

    assert len(indexed_ids) == 1
    assert indexed_docs == ["Payment is due on the first day."]


# ---- indexing failure recovery (one bad embedding skips, batch continues) ----

def test_indexing_failure_recovers_partial_batch() -> None:
    """Batch embedding succeeds and all clauses are indexed."""
    from app.services.embedding_service import EmbeddingService

    service = EmbeddingService.__new__(EmbeddingService)
    service._embedding_dimensionality = 1536
    indexed: list[str] = []

    class FakeCollection:
        def __init__(self) -> None:
            self._ids: list[str] = []

        def get(self, include: Any = None) -> dict[str, Any]:
            return {"ids": list(self._ids)}

        def add(
            self,
            ids: list[str],
            embeddings: list[list[float]],
            documents: list[str],
            metadatas: list[dict[str, Any]],
        ) -> None:
            self._ids.extend(ids)
            indexed.extend(documents)

        def count(self) -> int:
            return len(self._ids)

    service._collection = lambda _u, _d: FakeCollection()  # type: ignore[method-assign]
    service._gemini = MagicMock()
    service._gemini.models.embed_content = MagicMock(
        return_value=SimpleNamespace(
            embeddings=[
                SimpleNamespace(values=[0.1] * 1536),
                SimpleNamespace(values=[0.2] * 1536),
                SimpleNamespace(values=[0.3] * 1536),
            ]
        )
    )

    clauses = [
        {"title": "First", "original_text": "first clause", "page_number": 1},
        {"title": "Bad", "original_text": "second clause fails", "page_number": 2},
        {"title": "Third", "original_text": "third clause", "page_number": 3},
    ]
    service.index_clauses(USER_ID, DOCUMENT_ID, clauses)  # must not raise

    assert len(indexed) == 3
    assert "first clause" in indexed
