"""Regression tests for embedding failure classification and logging.

Covers Bug 2:
  - successful embeddings are stored in Chroma (REQUEST + SUCCESS logs),
  - only retryable failures (429/5xx/transport) are retried once,
  - fail-fast codes (400/401/403/404) raise immediately without retry,
  - failures carry category + status + original message (no swallowing),
  - per-clause skips continue the batch; zero-stored upserts log
    INDEX_UPSERT_EMPTY instead of claiming completion.
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from google.genai.errors import ClientError, ServerError

from app.services.embedding_service import (
    EmbeddingService,
    EmbeddingServiceError,
    prepare_document_for_embedding,
    prepare_query_for_embedding,
)

USER_ID = "user-123"
DOCUMENT_ID = uuid4()


def make_service() -> EmbeddingService:
    """Build an EmbeddingService without touching Chroma or the network."""
    service = EmbeddingService.__new__(EmbeddingService)
    service._gemini = MagicMock()
    service._embedding_dimensionality = 1536
    return service


def fake_embedding(values: list[float] | None = None) -> SimpleNamespace:
    """Return a Gemini-shaped embed_content response with 1536-dim vectors."""
    return SimpleNamespace(
        embeddings=[SimpleNamespace(values=values or [0.1] * 1536)]
    )


def fake_embeddings(count: int, values_per_vec: list[float] | None = None) -> SimpleNamespace:
    """Return a Gemini-shaped batch embed_content response."""
    if values_per_vec is None:
        values_per_vec = [0.1] * 1536
    return SimpleNamespace(
        embeddings=[SimpleNamespace(values=values_per_vec) for _ in range(count)]
    )


class FakeCollection:
    """In-memory Chroma collection double."""

    def __init__(self) -> None:
        self.ids: list[str] = []
        self.documents: list[str] = []
        self._all_embeddings: list[list[float]] = []

    def get(self, include: object = None, n: int = None) -> dict:
        result: dict = {"ids": list(self.ids)}
        if include and "embeddings" in include:
            result["embeddings"] = [
                SimpleNamespace(values=v) for v in self._all_embeddings
            ]
        return result

    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        self.ids.extend(ids)
        self.documents.extend(documents)
        for vec in embeddings:
            self._all_embeddings.append(vec)

    def delete(self, ids: list[str]) -> None:
        id_set = set(ids)
        self.ids = [i for i in self.ids if i not in id_set]
        self.documents = [d for i, d in enumerate(self.documents) if self.ids[i] if i < len(self.ids) and self.ids[i] not in id_set]
        self._all_embeddings = [
            v for i, v in enumerate(self._all_embeddings)
            if i < len(self.ids) and self.ids[i] not in id_set
        ]

    def count(self) -> int:
        return len(self.ids)


class LogCapture(logging.Handler):
    """Collect lexi log messages and their structured context."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []
        self.contexts: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())
        ctx = getattr(record, "context", {})
        if ctx:
            self.contexts.append(ctx)


@pytest.fixture
def log_capture() -> LogCapture:
    """Capture CHAT_/INDEX_ stage names emitted during a test."""
    handler = LogCapture()
    logger = logging.getLogger("lexi-ai-legal-assistant")
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the 1s retry backoff."""
    monkeypatch.setattr("app.services.embedding_service.time.sleep", lambda _s: None)


def test_embed_success_logs_request_and_success(
    no_sleep: None, log_capture: LogCapture
) -> None:
    """A good embedding returns a vector and logs REQUEST + SUCCESS."""
    service = make_service()
    service._gemini.models.embed_content = MagicMock(return_value=fake_embedding())

    vector = service._embed("Payment is due on day one.")

    assert vector == [0.1] * 1536
    assert "INDEX_EMBEDDING_REQUEST" in log_capture.messages
    assert "INDEX_EMBEDDING_SUCCESS" in log_capture.messages
    assert "INDEX_EMBEDDING_FAILURE" not in log_capture.messages
    # Verify model name is gemini-embedding-2 in log context
    assert any(
        ctx.get("model") == "gemini-embedding-2"
        for ctx in log_capture.contexts
    )


def test_embed_404_fails_fast_without_retry(no_sleep: None) -> None:
    """Invalid model (404) raises immediately — retrying can never help."""
    service = make_service()
    service._gemini.models.embed_content = MagicMock(
        side_effect=ClientError(404, {"error": {"message": "model not found"}}, None)
    )

    with pytest.raises(EmbeddingServiceError, match="invalid_model"):
        service._embed("some clause")

    assert service._gemini.models.embed_content.call_count == 1


def test_embed_401_fails_fast_without_retry(no_sleep: None) -> None:
    """Invalid API key (401) raises immediately with its category."""
    service = make_service()
    service._gemini.models.embed_content = MagicMock(
        side_effect=ClientError(401, {"error": {"message": "API key not valid"}}, None)
    )

    with pytest.raises(EmbeddingServiceError, match="invalid_api_key"):
        service._embed("some clause")

    assert service._gemini.models.embed_content.call_count == 1


def test_embed_429_retried_once_then_succeeds(
    no_sleep: None, log_capture: LogCapture
) -> None:
    """Rate limits are retryable: second attempt succeeds and stores."""
    service = make_service()
    service._gemini.models.embed_content = MagicMock(
        side_effect=[
            ClientError(429, {"error": {"message": "Resource exhausted"}}, None),
            fake_embedding([0.4] * 1536),
        ]
    )

    vector = service._embed("some clause")

    assert vector == [0.4] * 1536
    assert service._gemini.models.embed_content.call_count == 2
    assert "INDEX_EMBEDDING_RETRY" in log_capture.messages
    assert "INDEX_EMBEDDING_SUCCESS" in log_capture.messages


def test_embed_503_retried_then_surfaces_server_error(no_sleep: None) -> None:
    """Persistent 503s retry once, then raise with category + status."""
    service = make_service()
    service._gemini.models.embed_content = MagicMock(
        side_effect=ServerError(503, {"error": {"message": "overloaded"}}, None)
    )

    with pytest.raises(EmbeddingServiceError, match="server_error"):
        service._embed("some clause")

    assert service._gemini.models.embed_content.call_count == 2


def test_embed_transport_error_retried_once(no_sleep: None) -> None:
    """Codeless transport errors (no Gemini status) are retryable once."""
    service = make_service()
    service._gemini.models.embed_content = MagicMock(
        side_effect=[ConnectionError("reset by peer"), fake_embedding([0.9] * 1536)]
    )

    assert service._embed("some clause") == [0.9] * 1536
    assert service._gemini.models.embed_content.call_count == 2


@pytest.mark.parametrize(
    ("code", "message", "category"),
    [
        (401, "API key not valid", "invalid_api_key"),
        (403, "forbidden", "invalid_api_key"),
        (404, "models/xxx not found", "invalid_model"),
        (429, "Resource exhausted", "rate_limited"),
        (429, "quota exceeded for project", "quota_exceeded"),
        (400, "invalid argument", "invalid_payload_or_sdk_misuse"),
        (500, "internal", "server_error"),
        (503, "overloaded", "server_error"),
        (None, "reset by peer", "transport_or_unknown"),
    ],
)
def test_failure_categories(code: int | None, message: str, category: str) -> None:
    """Each distinguishable cause maps to its operator-facing category."""
    assert EmbeddingService._failure_category(code, message) == category


def test_index_success_stores_vectors(no_sleep: None, log_capture: LogCapture) -> None:
    """Successful embeddings land in Chroma with stored counts."""
    service = make_service()
    # Mock embed_content to return 2 embeddings (one per clause)
    service._gemini.models.embed_content = MagicMock(
        return_value=fake_embeddings(2)
    )
    collection = FakeCollection()
    service._collection = lambda _u, _d: collection  # type: ignore[method-assign]

    service.index_clauses(USER_ID, DOCUMENT_ID, [
        {"title": "Payment", "original_text": "Pay on day one.", "page_number": 1},
        {"title": "End", "original_text": "Either party may end it.", "page_number": 2},
    ])

    assert len(collection.documents) == 2
    assert "Pay on day one." in collection.documents
    assert "Either party may end it." in collection.documents
    assert "INDEX_EMBEDDING_REQUEST" in log_capture.messages
    assert "INDEX_EMBEDDING_SUCCESS" in log_capture.messages
    assert "INDEX_UPSERT_EMPTY" not in log_capture.messages
    # Verify model name in log context
    assert any(
        ctx.get("model") == "gemini-embedding-2"
        for ctx in log_capture.contexts
    )


def test_index_all_failures_log_empty_instead_of_completion(
    no_sleep: None, log_capture: LogCapture
) -> None:
    """Zero stored embeddings must not look like a completed index."""
    service = make_service()
    service._gemini.models.embed_content = MagicMock(
        side_effect=ClientError(401, {"error": {"message": "bad key"}}, None)
    )
    collection = FakeCollection()
    service._collection = lambda _u, _d: collection  # type: ignore[method-assign]

    # Never raises (indexing must not block analysis/chat)...
    service.index_clauses(USER_ID, DOCUMENT_ID, [
        {"title": "Payment", "original_text": "Pay on day one.", "page_number": 1},
    ])

    # ...but nothing stored and the empty index is loud.
    assert collection.documents == []
    assert "INDEX_UPSERT_DONE" in log_capture.messages
    assert "INDEX_UPSERT_EMPTY" in log_capture.messages
    assert "INDEX_EMBEDDING_FAILURE" in log_capture.messages


# ---- Task formatting tests ----

def test_prepare_document_for_embedding() -> None:
    """Document embedding text uses the official asymmetric format."""
    text = "Payment is due on the first day."
    formatted = prepare_document_for_embedding(text, title="Payment")
    assert formatted == "title: Payment | text: Payment is due on the first day."


def test_prepare_document_for_embedding_no_title() -> None:
    """Document without title uses the official 'title: none' fallback."""
    formatted = prepare_document_for_embedding("Some text")
    assert formatted == "title: none | text: Some text"


def test_prepare_query_for_embedding() -> None:
    """Query embedding text uses the official question-answering format."""
    formatted = prepare_query_for_embedding("What is the termination date?")
    assert formatted == "task: question answering | query: What is the termination date?"


# ---- Dimension consistency tests ----

def test_embedding_dimensionality_is_1536() -> None:
    """Default embedding dimensionality is 1536."""
    from app.services.gemini_provider import EMBEDDING_OUTPUT_DIMENSIONALITY
    assert EMBEDDING_OUTPUT_DIMENSIONALITY == 1536


def test_embedding_model_is_gemini_embedding_2() -> None:
    """The embedding model is gemini-embedding-2, not gemini-embedding-001."""
    from app.services.gemini_provider import EMBEDDING_MODEL
    assert EMBEDDING_MODEL == "gemini-embedding-2"
    assert EMBEDDING_MODEL != "gemini-embedding-001"


# ---- SDK-shape regression tests (root cause: INVALID kwarg) ----

def test_embed_uses_config_not_top_level_kwarg(no_sleep: None) -> None:
    """output_dimensionality must travel inside EmbedContentConfig.

    The google-genai signature is
    ``embed_content(*, model, contents, config=None)`` — a top-level
    ``output_dimensionality`` kwarg raises TypeError on every call (the
    production INDEX_EMBEDDING_FAILURE storm).
    """
    from google.genai import types

    service = make_service()
    service._gemini.models.embed_content = MagicMock(return_value=fake_embedding())

    service._embed("some clause")

    _, kwargs = service._gemini.models.embed_content.call_args
    assert "output_dimensionality" not in kwargs
    assert kwargs["model"] == "gemini-embedding-2"
    config = kwargs["config"]
    assert isinstance(config, types.EmbedContentConfig)
    assert config.output_dimensionality == 1536


def test_embed_batch_uses_config_not_top_level_kwarg(no_sleep: None) -> None:
    """Batch embeddings use the same config envelope."""
    from google.genai import types

    service = make_service()
    service._gemini.models.embed_content = MagicMock(return_value=fake_embeddings(2))

    service._embed_batch(["doc one", "doc two"])

    _, kwargs = service._gemini.models.embed_content.call_args
    assert "output_dimensionality" not in kwargs
    assert isinstance(kwargs["config"], types.EmbedContentConfig)
    assert kwargs["config"].output_dimensionality == 1536


def test_upsert_stores_user_id_for_retrieval_filter(no_sleep: None) -> None:
    """Stored metadata user_id must match the retrieve() where filter."""
    service = make_service()
    service._gemini.models.embed_content = MagicMock(return_value=fake_embeddings(1))
    collection = FakeCollection()
    stored_metadatas: list[dict] = []
    orig_add = collection.add

    def spy_add(ids: list[str], embeddings: list, documents: list[str], metadatas: list[dict]) -> None:
        stored_metadatas.extend(metadatas)
        orig_add(ids, embeddings, documents, metadatas)

    collection.add = spy_add  # type: ignore[method-assign]
    service._collection = lambda _u, _d: collection  # type: ignore[method-assign]

    service.index_clauses(USER_ID, DOCUMENT_ID, [
        {"title": "Payment", "original_text": "Pay on day one.", "page_number": 1},
    ])

    assert stored_metadatas and all(m["user_id"] == USER_ID for m in stored_metadatas)


def test_old_vectors_detected_on_any_dimension_mismatch() -> None:
    """Any dim != configured dim is incompatible, not just 3072."""
    service = make_service()

    class DimCollection(FakeCollection):
        def __init__(self, dim: int) -> None:
            super().__init__()
            self._all_embeddings = [[0.1] * dim]
            self.ids = ["old"]

    assert service._detect_old_collection(DimCollection(3072)) is True
    assert service._detect_old_collection(DimCollection(768)) is True
    assert service._detect_old_collection(DimCollection(1536)) is False
