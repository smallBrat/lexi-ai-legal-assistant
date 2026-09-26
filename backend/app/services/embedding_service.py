"""Cached ChromaDB embeddings for document clauses using Gemini Embedding 2."""

import hashlib
import os
import time
import traceback
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import UUID

from google.genai import types

from app.core.logging import error, info, warning
from app.services import gemini_provider
from app.services.gemini_provider import (
    EMBEDDING_MAX_INPUT_CHARS,
    EMBEDDING_MODEL,
    EMBEDDING_OUTPUT_DIMENSIONALITY,
    TASK_INSTRUCTION_RETRIEVAL_DOCUMENT,
    TASK_INSTRUCTION_RETRIEVAL_QUERY,
    gemini_status_code,
    is_retryable_status,
)

# Move ChromaDB outside backend/ so uvicorn file watcher never sees it.
_DEFAULT_CHROMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    ".chroma",
)

# Dimension marker used to detect old vector collections.
# gemini-embedding-001 produced 3072-dimensional vectors by default.
_OLD_EMBEDDING_DIMENSION = 3072
_NEW_EMBEDDING_DIMENSION = EMBEDDING_OUTPUT_DIMENSIONALITY


class EmbeddingServiceError(Exception):
    """Raised when clause embeddings cannot be generated or queried."""


@dataclass(frozen=True)
class ClauseMatch:
    """Retrieved clause and its similarity score."""

    title: str
    excerpt: str
    page_number: int | None
    similarity_score: float


def prepare_document_for_embedding(
    text: str, title: str | None = None
) -> str:
    """Format a document chunk for Gemini Embedding 2 retrieval.

    Official asymmetric format
    (https://ai.google.dev/gemini-api/docs/embeddings):
        title: {title} | text: {chunk text}
    with ``title: none`` when no title is available.
    """
    safe_title = title.strip() if title and title.strip() else "none"
    return f"{TASK_INSTRUCTION_RETRIEVAL_DOCUMENT}{safe_title} | text: {text}"


def prepare_query_for_embedding(text: str) -> str:
    """Format a user question for Gemini Embedding 2 retrieval.

    Official asymmetric format
    (https://ai.google.dev/gemini-api/docs/embeddings):
        task: question answering | query: {user question}
    """
    return f"{TASK_INSTRUCTION_RETRIEVAL_QUERY}{text}"


class EmbeddingService:
    """Generate and cache per-document clause vectors in ChromaDB.

    IMPORTANT: Use ``get_embedding_service()`` to obtain the singleton
    instance. Creating new instances per request causes SQLite file-lock
    contention and ChromaDB re-initialisation overhead.
    """

    def __init__(self, chroma_path: str | None = None, embedding_dimensionality: int | None = None) -> None:
        """Initialize Gemini embeddings and a persistent Chroma client.

        The ChromaDB path defaults to a directory *outside* ``backend/`` so
        the uvicorn dev-reloader never picks up ChromaDB file changes.

        Args:
            chroma_path: Optional path to ChromaDB persistent directory.
            embedding_dimensionality: Output dimensionality for embeddings.
                Defaults to EMBEDDING_OUTPUT_DIMENSIONALITY from the provider.
        """
        try:
            import chromadb

            self._chroma = chromadb.PersistentClient(
                path=chroma_path or _DEFAULT_CHROMA_PATH,
            )
            self._embedding_dimensionality = embedding_dimensionality or EMBEDDING_OUTPUT_DIMENSIONALITY
            # Shared singleton from the provider — never `genai.Client(...)`.
            # Accessed via the module so tests can patch the factory.
            self._gemini = gemini_provider.get_gemini_client()
        except Exception as exc:
            raise EmbeddingServiceError("Embedding service is unavailable") from exc

    @staticmethod
    def _collection_name(user_id: str, document_id: UUID) -> str:
        """Create a safe, stable collection name with user isolation."""
        digest = hashlib.sha256(f"{user_id}:{document_id}".encode()).hexdigest()[:32]
        return f"doc_{digest}"

    def _collection(self, user_id: str, document_id: UUID) -> Any:
        """Get the isolated Chroma collection for one user's document."""
        return self._chroma.get_or_create_collection(
            name=self._collection_name(user_id, document_id),
            metadata={"user_id": user_id, "document_id": str(document_id)},
        )

    @staticmethod
    def _failure_category(status_code: int | None, message: str) -> str:
        """Classify an embedding failure so operators can tell apart the causes.

        404 → invalid model name; 401/403 → invalid API key; 429 →
        rate-limited vs quota-exhausted (message sniff); 400 → payload too
        large or SDK misuse; 5xx → Gemini server-side; anything else →
        transport/unknown.
        """
        lowered = (message or "").lower()
        if status_code in (401, 403):
            return "invalid_api_key"
        if status_code == 404:
            return "invalid_model"
        if status_code == 429:
            return "quota_exceeded" if "quota" in lowered else "rate_limited"
        if status_code == 400:
            return "invalid_payload_or_sdk_misuse"
        if status_code is not None and 500 <= status_code < 600:
            return "server_error"
        if status_code is not None:
            return "client_error"
        return "transport_or_unknown"

    def _detect_old_collection(self, collection: Any) -> bool:
        """Detect if a ChromaDB collection holds incompatible vectors.

        Any stored vector whose dimension differs from the currently
        configured ``_embedding_dimensionality`` (old gemini-embedding-001
        vectors default to 3072 dims, or a previous Embedding 2 setting)
        must be invalidated — embedding spaces can never be mixed.
        """
        try:
            existing = collection.get(include=["embeddings"], n=1)
            embeddings = existing.get("embeddings", [])
            if embeddings:
                vector = embeddings[0]
                if hasattr(vector, "values"):
                    dim = len(vector.values)
                elif isinstance(vector, list):
                    dim = len(vector)
                else:
                    return False
                return dim != self._embedding_dimensionality
            return False
        except Exception:
            return False

    def _invalidate_if_old(self, collection: Any, user_id: str, document_id: UUID) -> bool:
        """If a collection contains old embedding-001 vectors, delete them.

        Returns True if the collection was invalidated (old vectors found and deleted).
        Never mixes 001 vectors with Embedding 2 vectors.
        """
        if not self._detect_old_collection(collection):
            return False
        warning(
            "INDEX_COLLECTION_OLD_VECTORS_DETECTED",
            document_id=str(document_id),
            user_id=user_id,
            collection_name=self._collection_name(user_id, document_id),
            old_dimension=_OLD_EMBEDDING_DIMENSION,
            new_dimension=self._embedding_dimensionality,
            message="Incompatible vectors detected (dimension mismatch). Deleting to prevent mixed embedding spaces.",
        )
        try:
            existing = collection.get(include=[])
            ids_to_delete = existing.get("ids", [])
            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
                info(
                    "INDEX_COLLECTION_OLD_VECTORS_DELETED",
                    document_id=str(document_id),
                    deleted_count=len(ids_to_delete),
                )
        except Exception as exc:
            error(
                "INDEX_COLLECTION_INVALIDATION_FAILED",
                document_id=str(document_id),
                user_id=user_id,
                exc_type=type(exc).__name__,
                exc_message=str(exc),
            )
        return True

    def _embed(self, text: str, _diag: dict[str, Any] | None = None) -> list[float]:
        """Generate one embedding with Gemini Embedding 2.

        Input is truncated to the provider's char guard so oversized
        clauses can never blow the token limit. Only RETRYABLE failures
        (429 / 5xx / transport errors) are retried once with a short
        backoff; fail-fast codes (400/401/403/404) raise immediately so a
        bad model name or key surfaces instead of being retried and
        swallowed. Every outcome is logged with full exception context —
        the caller skips that clause so indexing never blocks chat.

        ``_diag`` is diagnostics-only context (document_id, chunk_index,
        chunk_total, chunk_chars, label) attached to every log line. It
        never affects control flow.
        """
        payload = text[:EMBEDDING_MAX_INPUT_CHARS]
        diag: dict[str, Any] = dict(_diag or {})
        diag.setdefault("chunk_chars", len(payload))
        last_exc: Exception | None = None
        for attempt in (1, 2):
            info(
                "INDEX_EMBEDDING_REQUEST",
                model=EMBEDDING_MODEL,
                output_dimension=self._embedding_dimensionality,
                input_chars=len(payload),
                attempt=attempt,
                **diag,
            )
            attempt_started = perf_counter()
            try:
                response = self._gemini.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=payload,
                    config=types.EmbedContentConfig(
                        output_dimensionality=self._embedding_dimensionality
                    ),
                )
                embedding = getattr(response, "embeddings", None)
                if not embedding:
                    raise EmbeddingServiceError("Embedding response was empty")
                values = embedding[0].values if hasattr(embedding[0], "values") else embedding[0]
                vector = [float(value) for value in values]
                info(
                    "INDEX_EMBEDDING_SUCCESS",
                    model=EMBEDDING_MODEL,
                    output_dimension=self._embedding_dimensionality,
                    attempt=attempt,
                    dimensions=len(vector),
                    elapsed_ms=round((perf_counter() - attempt_started) * 1000, 2),
                    **diag,
                )
                return vector
            except EmbeddingServiceError:
                raise
            except Exception as exc:
                last_exc = exc
                status_code = gemini_status_code(exc)
                gemini_error = getattr(exc, "status", None)
                category = self._failure_category(status_code, str(exc))
                elapsed_ms = round((perf_counter() - attempt_started) * 1000, 2)
                if attempt == 1 and is_retryable_status(status_code):
                    warning(
                        "INDEX_EMBEDDING_RETRY",
                        model=EMBEDDING_MODEL,
                        output_dimension=self._embedding_dimensionality,
                        attempt=attempt,
                        input_chars=len(payload),
                        elapsed_ms=elapsed_ms,
                        exc_type=type(exc).__name__,
                        exc_message=str(exc),
                        gemini_status_code=status_code,
                        gemini_error=gemini_error,
                        failure_category=category,
                        **diag,
                    )
                    time.sleep(1.0)
                    continue
                error(
                    "INDEX_EMBEDDING_FAILURE",
                    model=EMBEDDING_MODEL,
                    output_dimension=self._embedding_dimensionality,
                    attempt=attempt,
                    input_chars=len(payload),
                    elapsed_ms=elapsed_ms,
                    exc_type=type(exc).__name__,
                    exc_message=str(exc),
                    gemini_status_code=status_code,
                    gemini_error=gemini_error,
                    failure_category=category,
                    retried=attempt > 1,
                    embedding_length=len(vector) if 'vector' in dir() else 0,
                    traceback=traceback.format_exc(),
                    **diag,
                )
                raise EmbeddingServiceError(
                    f"Unable to generate clause embedding "
                    f"(model={EMBEDDING_MODEL}, category={category}, "
                    f"status={status_code}, error={type(exc).__name__}: {exc})"
                ) from last_exc
        raise EmbeddingServiceError("Unable to generate clause embedding") from last_exc

    def _embed_batch(self, texts: list[str], _diag: dict[str, Any] | None = None) -> list[list[float]]:
        """Generate embeddings for multiple texts in a single batch request.

        Each text in the batch must already have the task instruction prepended
        by the caller. Returns one vector per input text — no aggregation.
        """
        diag: dict[str, Any] = dict(_diag or {})
        last_exc: Exception | None = None
        for attempt in (1, 2):
            info(
                "INDEX_EMBEDDING_REQUEST",
                model=EMBEDDING_MODEL,
                output_dimension=self._embedding_dimensionality,
                batch_size=len(texts),
                input_chars=sum(len(t) for t in texts),
                attempt=attempt,
                **diag,
            )
            attempt_started = perf_counter()
            try:
                response = self._gemini.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=texts,
                    config=types.EmbedContentConfig(
                        output_dimensionality=self._embedding_dimensionality
                    ),
                )
                embeddings = getattr(response, "embeddings", None)
                if not embeddings:
                    raise EmbeddingServiceError("Batch embedding response was empty")
                vectors: list[list[float]] = []
                for embedding in embeddings:
                    values = embedding.values if hasattr(embedding, "values") else embedding
                    vectors.append([float(value) for value in values])
                info(
                    "INDEX_EMBEDDING_SUCCESS",
                    model=EMBEDDING_MODEL,
                    output_dimension=self._embedding_dimensionality,
                    attempt=attempt,
                    batch_size=len(vectors),
                    dimensions=len(vectors[0]) if vectors else 0,
                    elapsed_ms=round((perf_counter() - attempt_started) * 1000, 2),
                    **diag,
                )
                return vectors
            except EmbeddingServiceError:
                raise
            except Exception as exc:
                last_exc = exc
                status_code = gemini_status_code(exc)
                gemini_error = getattr(exc, "status", None)
                category = self._failure_category(status_code, str(exc))
                elapsed_ms = round((perf_counter() - attempt_started) * 1000, 2)
                if attempt == 1 and is_retryable_status(status_code):
                    warning(
                        "INDEX_EMBEDDING_RETRY",
                        model=EMBEDDING_MODEL,
                        output_dimension=self._embedding_dimensionality,
                        attempt=attempt,
                        batch_size=len(texts),
                        elapsed_ms=elapsed_ms,
                        exc_type=type(exc).__name__,
                        exc_message=str(exc),
                        gemini_status_code=status_code,
                        gemini_error=gemini_error,
                        failure_category=category,
                        **diag,
                    )
                    time.sleep(1.0)
                    continue
                error(
                    "INDEX_EMBEDDING_FAILURE",
                    model=EMBEDDING_MODEL,
                    output_dimension=self._embedding_dimensionality,
                    attempt=attempt,
                    batch_size=len(texts),
                    elapsed_ms=elapsed_ms,
                    exc_type=type(exc).__name__,
                    exc_message=str(exc),
                    gemini_status_code=status_code,
                    gemini_error=gemini_error,
                    failure_category=category,
                    retried=attempt > 1,
                    traceback=traceback.format_exc(),
                    **diag,
                )
                raise EmbeddingServiceError(
                    f"Unable to generate batch embeddings "
                    f"(model={EMBEDDING_MODEL}, category={category}, "
                    f"status={status_code}, error={type(exc).__name__}: {exc})"
                ) from last_exc
        raise EmbeddingServiceError("Unable to generate batch embeddings") from last_exc

    @staticmethod
    def _clause_field(clause: Any, name: str, default: Any = "") -> Any:
        """Read a clause field from a dict OR a pydantic model."""
        if isinstance(clause, dict):
            return clause.get(name, default)
        return getattr(clause, name, default)

    def index_clauses(
        self, user_id: str, document_id: UUID, clauses: list[dict[str, Any]]
    ) -> None:
        """Cache embeddings for clauses that are not already indexed.

        Accepts dicts or pydantic clause models. A single bad clause or
        embedding failure never aborts the batch — it is logged with full
        context and skipped so a partial index still enables retrieval.

        Each clause is formatted with the retrieval-document task instruction
        before embedding, per Gemini Embedding 2 requirements.
        """
        collection_name = self._collection_name(user_id, document_id)
        info(
            "INDEX_START",
            document_id=str(document_id),
            user_id=user_id,
            clause_count=len(clauses),
            collection_name=collection_name,
            model=EMBEDDING_MODEL,
            output_dimension=self._embedding_dimensionality,
        )
        try:
            collection = self._collection(user_id, document_id)
        except Exception as exc:
            error(
                "INDEX_COLLECTION_FAILED",
                document_id=str(document_id),
                user_id=user_id,
                clause_count=len(clauses),
                collection_name=collection_name,
                exc_type=type(exc).__name__,
                exc_message=str(exc),
                traceback=traceback.format_exc(),
            )
            raise EmbeddingServiceError("Unable to open clause collection") from exc
        info(
            "INDEX_COLLECTION_READY",
            document_id=str(document_id),
            collection_name=collection_name,
            model=EMBEDDING_MODEL,
            output_dimension=self._embedding_dimensionality,
        )
        try:
            existing = collection.get(include=[])
        except Exception as exc:
            error(
                "INDEX_COLLECTION_FAILED",
                document_id=str(document_id),
                collection_name=collection_name,
                exc_type=type(exc).__name__,
                exc_message=str(exc),
                traceback=traceback.format_exc(),
            )
            raise EmbeddingServiceError("Unable to read clause collection") from exc

        # Detect and invalidate old embedding-001 vectors.
        # Never mix embedding spaces.
        self._invalidate_if_old(collection, user_id, document_id)

        existing_ids = set(existing.get("ids", []))
        embedded_count = 0
        skipped_count = 0
        info(
            "INDEX_UPSERT_START",
            document_id=str(document_id),
            collection_name=collection_name,
            clause_count=len(clauses),
            already_indexed=len(existing_ids),
            model=EMBEDDING_MODEL,
            output_dimension=self._embedding_dimensionality,
        )

        # Build formatted texts and vectors for batch processing.
        batch_texts: list[str] = []
        batch_indices: list[int] = []
        batch_clauses: list[dict[str, Any]] = []

        for index, clause in enumerate(clauses):
            excerpt = str(self._clause_field(clause, "original_text", "") or "").strip()
            if not excerpt:
                skipped_count += 1
                continue
            clause_id = str(self._clause_field(clause, "id", None) or index)
            if clause_id in existing_ids:
                skipped_count += 1
                continue

            title = str(self._clause_field(clause, "title", None) or "Clause")
            formatted = prepare_document_for_embedding(excerpt, title)
            batch_texts.append(formatted)
            batch_indices.append(index)
            batch_clauses.append(clause)

        # Process in batches of up to 256 (Gemini API batch limit).
        _BATCH_SIZE = 256
        for batch_start in range(0, len(batch_texts), _BATCH_SIZE):
            batch_end = min(batch_start + _BATCH_SIZE, len(batch_texts))
            batch_slice = batch_texts[batch_start:batch_end]
            batch_slice_indices = batch_indices[batch_start:batch_end]
            batch_slice_clauses = batch_clauses[batch_start:batch_end]

            try:
                vectors = self._embed_batch(batch_slice, {
                    "document_id": str(document_id),
                    "chunk_index": batch_slice_indices[0],
                    "chunk_total": len(clauses),
                })
            except Exception:
                # If batch fails, fall back to per-item embedding.
                for i, idx in enumerate(batch_slice_indices):
                    clause = batch_slice_clauses[i]
                    try:
                        excerpt = str(self._clause_field(clause, "original_text", "") or "").strip()
                        title = str(self._clause_field(clause, "title", None) or "Clause")
                        formatted = prepare_document_for_embedding(excerpt, title)
                        vector = self._embed(formatted, {
                            "document_id": str(document_id),
                            "chunk_index": idx,
                            "chunk_total": len(clauses),
                        })
                    except Exception as exc:
                        warning(
                            "INDEX_EMBEDDING_FAILED",
                            document_id=str(document_id),
                            collection_name=collection_name,
                            clause_index=idx,
                            exc_type=type(exc).__name__,
                            exc_message=str(exc),
                        )
                        skipped_count += 1
                        continue
                    self._upsert_clause(
                        collection, collection_name, clause, vector, idx, document_id, existing_ids,
                        user_id,
                    )
                    embedded_count += 1
                continue

            for i, (vector, idx, clause) in enumerate(zip(vectors, batch_slice_indices, batch_slice_clauses)):
                self._upsert_clause(
                    collection, collection_name, clause, vector, idx, document_id, existing_ids,
                    user_id,
                )
                embedded_count += 1

        info(
            "INDEX_UPSERT_DONE",
            document_id=str(document_id),
            collection_name=collection_name,
            clause_count=len(clauses),
            embedding_count=embedded_count,
            skipped_count=skipped_count,
            stored=embedded_count,
            model=EMBEDDING_MODEL,
            output_dimension=self._embedding_dimensionality,
        )
        if len(clauses) > 0 and embedded_count == 0:
            error(
                "INDEX_UPSERT_EMPTY",
                document_id=str(document_id),
                collection_name=collection_name,
                clause_count=len(clauses),
                skipped_count=skipped_count,
                stored=0,
                model=EMBEDDING_MODEL,
            )

    def _upsert_clause(
        self,
        collection: Any,
        collection_name: str,
        clause: dict[str, Any],
        vector: list[float],
        index: int,
        document_id: UUID,
        existing_ids: set[str],
        user_id: str,
    ) -> None:
        """Upsert a single clause embedding into ChromaDB."""
        clause_id = str(self._clause_field(clause, "id", None) or index)
        if clause_id in existing_ids:
            return
        try:
            title = str(self._clause_field(clause, "title", None) or "Clause")
            page_raw = self._clause_field(clause, "page_number", None)
            excerpt = str(self._clause_field(clause, "original_text", "") or "").strip()
            metadata: dict[str, Any] = {
                "user_id": user_id,
                "document_id": str(document_id),
                "title": title,
                "page_number": str(int(page_raw)) if page_raw not in (None, "") else "",
            }
            collection.add(
                ids=[clause_id],
                embeddings=[vector],
                documents=[excerpt],
                metadatas=[metadata],
            )
            existing_ids.add(clause_id)
        except Exception as exc:
            error(
                "INDEX_UPSERT_FAILED",
                document_id=str(document_id),
                collection_name=collection_name,
                clause_index=index,
                clause_id=clause_id,
                exc_type=type(exc).__name__,
                exc_message=str(exc),
                traceback=traceback.format_exc(),
            )

    def retrieve(
        self, user_id: str, document_id: UUID, question: str, top_k: int = 5
    ) -> list[ClauseMatch]:
        """Retrieve top-k clauses from the isolated document collection."""
        collection = self._collection(user_id, document_id)
        if collection.count() == 0:
            return []
        query_text = prepare_query_for_embedding(question)
        result = collection.query(
            query_embeddings=[
                self._embed(
                    query_text,
                    {"document_id": str(document_id), "label": "query"},
                )
            ],
            n_results=min(top_k, collection.count()),
            where={"$and": [{"user_id": user_id}, {"document_id": str(document_id)}]},
        )
        documents = result.get("documents", [[]])[0]
        distances = result.get("distances", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        matches: list[ClauseMatch] = []
        for excerpt, distance, metadata in zip(documents, distances, metadatas):
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            page_value = (metadata or {}).get("page_number")
            try:
                page_number = int(str(page_value)) if page_value not in (None, "") else None
            except (TypeError, ValueError):
                page_number = None
            matches.append(
                ClauseMatch(
                    title=str((metadata or {}).get("title") or "Clause"),
                    excerpt=str(excerpt),
                    page_number=page_number,
                    similarity_score=similarity,
                )
            )
        return matches

    def reindex_document(
        self, user_id: str, document_id: UUID, clauses: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Re-index a document: delete old vectors and rebuild with Embedding 2.

        Returns a summary of the reindex operation.
        """
        collection_name = self._collection_name(user_id, document_id)
        info(
            "INDEX_REINDEX_START",
            document_id=str(document_id),
            user_id=user_id,
            clause_count=len(clauses),
            collection_name=collection_name,
            model=EMBEDDING_MODEL,
            output_dimension=self._embedding_dimensionality,
        )
        collection = self._collection(user_id, document_id)

        # Delete all existing vectors to prevent mixing embedding spaces.
        existing = collection.get(include=[])
        old_ids = existing.get("ids", [])
        if old_ids:
            collection.delete(ids=old_ids)
            info(
                "INDEX_REINDEX_CLEARED",
                document_id=str(document_id),
                deleted_count=len(old_ids),
            )

        # Re-index with new embeddings.
        self.index_clauses(user_id, document_id, clauses)

        new_count = collection.count()
        info(
            "INDEX_REINDEX_DONE",
            document_id=str(document_id),
            new_vector_count=new_count,
            model=EMBEDDING_MODEL,
            output_dimension=self._embedding_dimensionality,
        )
        return {
            "document_id": str(document_id),
            "old_vectors_deleted": len(old_ids),
            "new_vectors_stored": new_count,
            "model": EMBEDDING_MODEL,
            "output_dimension": self._embedding_dimensionality,
        }


# ---------------------------------------------------------------------------
# Module-level singleton — created once, reused across all requests.
# ---------------------------------------------------------------------------
_singleton: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Return the process-wide singleton EmbeddingService.

    Creates the instance on first call; subsequent calls return the cached
    singleton. Thread-safe under CPython's GIL for the simple check.
    """
    global _singleton
    if _singleton is None:
        from app.core.config import get_settings
        settings = get_settings()
        _singleton = EmbeddingService(
            chroma_path=settings.CHROMA_DB_PATH,
            embedding_dimensionality=settings.EMBEDDING_OUTPUT_DIMENSIONALITY,
        )
    return _singleton


def reset_embedding_service() -> None:
    """Reset the singleton (testing only)."""
    global _singleton
    _singleton = None