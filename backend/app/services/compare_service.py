"""Clause-by-clause comparison of two analyzed legal documents.

Pipeline (no OCR, no embeddings — both are reused from stored analyses):

1. Fetch both documents and verify ownership by the requesting user.
2. Require a validated ``LegalAnalysis`` on each (else ``AnalysisPending``).
3. Build a deterministic merged input (clause union by normalized title).
4. Ask Gemini ONLY for comparison reasoning (structured JSON).
5. Validate with Pydantic, cross-check metrics, return the result.

Persistence/caching lives in ``ComparisonRepository`` and is orchestrated
by the API layer so this service stays a pure compute unit (easy to test).
"""

import asyncio
import json
import random
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

from google.genai import types
from google.genai.errors import ClientError, ServerError
from pydantic import ValidationError

from app.core.logging import error, info, warning
from app.schemas.analysis_schema import LegalAnalysis
from app.schemas.compare_schema import ComparisonResult
from app.services import gemini_provider
from app.services.gemini_provider import MODEL_PRIORITY
from app.utils.schema_utils import build_gemini_schema_for

COMPARE_PROMPT_VERSION = "compare-analysis-v1"
COMPARE_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "compare_analysis.txt"

SANITIZED_COMPARE_SCHEMA: dict = build_gemini_schema_for(ComparisonResult)

COMPARE_TIMEOUT_SECONDS = 90.0
_MAX_ATTEMPTS_PER_MODEL = 2  # initial attempt + one retry
_RETRY_BASE_SECONDS = 2.0
_JITTER_MAX = 1.5


class CompareServiceError(Exception):
    """Base exception for comparison workflow failures."""


class CompareDocumentNotFoundError(CompareServiceError):
    """Raised when a document id does not exist."""


class CompareForbiddenError(CompareServiceError):
    """Raised when a document belongs to another user."""


class CompareAnalysisPendingError(CompareServiceError):
    """Raised when one or both documents lack a validated analysis."""

    def __init__(
        self,
        message: str,
        *,
        document_a_ready: bool = False,
        document_b_ready: bool = False,
    ) -> None:
        """Capture per-document readiness for the 422 response body."""
        super().__init__(message)
        self.document_a_ready = document_a_ready
        self.document_b_ready = document_b_ready


class CompareValidationError(CompareServiceError):
    """Raised when Gemini JSON does not match the comparison contract."""


class CompareGeminiError(CompareServiceError):
    """Raised when Gemini is unavailable (maps to HTTP 503, retryable)."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        """Capture the message and whether the caller should retry."""
        super().__init__(message)
        self.retryable = retryable


@dataclass
class ComparedDocuments:
    """Validated inputs for a comparison."""

    document_a: dict[str, Any]
    document_b: dict[str, Any]
    analysis_a: LegalAnalysis
    analysis_b: LegalAnalysis


@dataclass
class GeminiCompareResult:
    """Successful Gemini comparison with execution metadata."""

    text: str
    model: str
    latency_ms: float
    retry_count: int
    fallback_used: bool


def normalize_clause_title(title: str) -> str:
    """Normalize a clause title for deterministic union matching."""
    return " ".join(title.casefold().split())


def merge_clause_titles(analysis_a: LegalAnalysis, analysis_b: LegalAnalysis) -> list[str]:
    """Return the deterministic union of clause titles (normalized, sorted).

    Used to build the comparison input and to cross-check Gemini's metrics
    so similarity counts can never be invented from nothing.
    """
    titles: set[str] = set()
    for clause in (*analysis_a.clauses, *analysis_b.clauses):
        normalized = normalize_clause_title(clause.title)
        if normalized:
            titles.add(normalized)
    return sorted(titles)


def build_comparison_input(
    analysis_a: LegalAnalysis, analysis_b: LegalAnalysis, title_a: str, title_b: str
) -> str:
    """Serialize both analyses into the deterministic Gemini input."""
    merged = merge_clause_titles(analysis_a, analysis_b)
    payload = {
        "document_a_title": title_a,
        "document_b_title": title_b,
        "clause_title_union": merged,
        "document_a_analysis": analysis_a.model_dump(mode="json"),
        "document_b_analysis": analysis_b.model_dump(mode="json"),
    }
    return (
        "Document A analysis (untrusted data):\n"
        + json.dumps(payload["document_a_analysis"], ensure_ascii=False)
        + "\n\nDocument B analysis (untrusted data):\n"
        + json.dumps(payload["document_b_analysis"], ensure_ascii=False)
        + "\n\nClause title union (deterministic alignment aid):\n"
        + json.dumps(merged, ensure_ascii=False)
    )


class CompareService:
    """Compute a structured comparison from two stored analyses."""

    def __init__(self, client: Any) -> None:
        """Initialize the service with a Supabase client."""
        self._client = client
        # Shared singleton from the provider — never `genai.Client(...)`
        # here. Accessed via the module so tests can patch the factory.
        self._gemini = gemini_provider.get_gemini_client()

    # -- document loading -------------------------------------------------

    def _fetch_row(self, document_id: UUID) -> dict[str, Any] | None:
        """Fetch one document row without applying ownership."""
        response = (
            self._client.table("documents")
            .select("id,user_id,title,document_type,extracted_text,analysis")
            .eq("id", str(document_id))
            .limit(1)
            .execute()
        )
        records = response.data or []
        return records[0] if records else None

    def _load_validated(self, document_id: UUID, user_id: str) -> tuple[dict[str, Any], LegalAnalysis | None]:
        """Fetch an owned document and validate its stored analysis."""
        try:
            row = self._fetch_row(document_id)
        except Exception as exc:
            raise CompareServiceError("Unable to fetch document") from exc
        if row is None:
            raise CompareDocumentNotFoundError("Document was not found")
        if str(row.get("user_id")) != str(user_id):
            raise CompareForbiddenError("You do not have access to this document.")
        raw_analysis = row.get("analysis")
        if not raw_analysis:
            return row, None
        try:
            if isinstance(raw_analysis, str):
                return row, LegalAnalysis.model_validate_json(raw_analysis)
            return row, LegalAnalysis.model_validate(raw_analysis)
        except (ValidationError, ValueError) as exc:
            warning("Stored analysis failed validation", document_id=str(document_id), error=str(exc))
            return row, None

    async def load_documents(self, a_id: UUID, b_id: UUID, user_id: str) -> ComparedDocuments:
        """Load and validate both documents; raise typed errors otherwise."""
        if a_id == b_id:
            raise CompareServiceError("Cannot compare a document with itself.")
        row_a, analysis_a = await asyncio.to_thread(self._load_validated, a_id, user_id)
        row_b, analysis_b = await asyncio.to_thread(self._load_validated, b_id, user_id)
        ready_a = analysis_a is not None
        ready_b = analysis_b is not None
        if not (ready_a and ready_b):
            raise CompareAnalysisPendingError(
                "One or more documents are still being analyzed.",
                document_a_ready=ready_a,
                document_b_ready=ready_b,
            )
        assert analysis_a is not None and analysis_b is not None
        return ComparedDocuments(document_a=row_a, document_b=row_b, analysis_a=analysis_a, analysis_b=analysis_b)

    # -- Gemini ------------------------------------------------------------

    def _build_system_instruction(self) -> str:
        """Load the shared comparison system instruction."""
        try:
            return COMPARE_PROMPT_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            raise CompareGeminiError("Comparison prompt is unavailable", retryable=False) from exc

    def _backoff_with_jitter(self, attempt: int) -> float:
        """Return exponential backoff (base * 2**attempt) plus jitter."""
        return _RETRY_BASE_SECONDS * (2**attempt) + random.uniform(0, _JITTER_MAX)

    async def _generate(self, comparison_input: str, correction: str | None = None) -> GeminiCompareResult:
        """Generate comparison JSON with multi-model fallback.

        Mirrors the analysis retry policy: each model is retried once on
        503/429/timeout with backoff; 400/401/403 fail fast.
        """
        config = types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=SANITIZED_COMPARE_SCHEMA,
            system_instruction=self._build_system_instruction(),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        contents = comparison_input if correction is None else [comparison_input, correction]
        total_retries = 0
        for model_index, model_name in enumerate(MODEL_PRIORITY):
            for attempt in range(_MAX_ATTEMPTS_PER_MODEL):
                started = perf_counter()
                try:
                    response = await asyncio.wait_for(
                        self._gemini.aio.models.generate_content(
                            model=model_name, contents=contents, config=config
                        ),
                        timeout=COMPARE_TIMEOUT_SECONDS,
                    )
                    text = getattr(response, "text", None)
                    if not text:
                        raise CompareGeminiError("Comparison provider returned an empty response")
                    return GeminiCompareResult(
                        text=str(text).strip(),
                        model=model_name,
                        latency_ms=round((perf_counter() - started) * 1000, 2),
                        retry_count=total_retries,
                        fallback_used=(model_index > 0),
                    )
                except (asyncio.TimeoutError, ServerError) as exc:
                    status_code = getattr(exc, "code", None)
                    warning(
                        "compare_model_attempt_failed",
                        model=model_name,
                        attempt=attempt + 1,
                        reason="timeout" if isinstance(exc, asyncio.TimeoutError) else "server_error",
                        status_code=status_code,
                    )
                    if attempt + 1 < _MAX_ATTEMPTS_PER_MODEL:
                        total_retries += 1
                        await asyncio.sleep(self._backoff_with_jitter(attempt))
                        continue
                    break
                except ClientError as exc:
                    status_code = getattr(exc, "code", None)
                    if status_code in (400, 401, 403):
                        error("Compare Gemini API error", status_code=status_code, model=model_name)
                        raise CompareGeminiError("Comparison request failed", retryable=False) from exc
                    warning("compare_model_attempt_failed", model=model_name, status_code=status_code)
                    if status_code == 429 and attempt + 1 < _MAX_ATTEMPTS_PER_MODEL:
                        total_retries += 1
                        await asyncio.sleep(self._backoff_with_jitter(attempt))
                        continue
                    break
        raise CompareGeminiError("Comparison provider is temporarily unavailable.")

    # -- public pipeline ----------------------------------------------------

    async def compare(self, a_id: UUID, b_id: UUID, user_id: str) -> tuple[ComparisonResult, ComparedDocuments, dict[str, Any]]:
        """Run the full comparison pipeline and return (result, docs, meta)."""
        docs = await self.load_documents(a_id, b_id, user_id)
        comparison_input = build_comparison_input(
            docs.analysis_a,
            docs.analysis_b,
            str(docs.document_a.get("title") or ""),
            str(docs.document_b.get("title") or ""),
        )
        info(
            "Comparison started",
            document_a_id=str(a_id),
            document_b_id=str(b_id),
            clause_union_size=len(merge_clause_titles(docs.analysis_a, docs.analysis_b)),
        )
        try:
            gemini_out = await self._generate(comparison_input)
        except CompareGeminiError:
            raise
        except Exception as exc:
            raise CompareGeminiError("Comparison provider failed") from exc

        try:
            result = ComparisonResult.model_validate_json(gemini_out.text)
        except (ValidationError, ValueError):
            correction = (
                "Return one JSON object matching the required schema. "
                "Correct any validation errors and return JSON only."
            )
            try:
                retry_out = await self._generate(comparison_input, correction=correction)
            except CompareGeminiError:
                raise
            except Exception as exc:
                raise CompareGeminiError("Comparison provider failed") from exc
            try:
                result = ComparisonResult.model_validate_json(retry_out.text)
                gemini_out = retry_out
            except (ValidationError, ValueError) as exc:
                error("Comparison JSON validation failed", error=str(exc))
                raise CompareValidationError("Comparison provider returned an invalid response.") from exc

        result = self._cross_check_metrics(result, docs)
        meta = {
            "model": gemini_out.model,
            "latency_ms": gemini_out.latency_ms,
            "retry_count": gemini_out.retry_count,
            "fallback_used": gemini_out.fallback_used,
            "prompt_version": COMPARE_PROMPT_VERSION,
        }
        info(
            "Comparison finished",
            document_a_id=str(a_id),
            document_b_id=str(b_id),
            model=gemini_out.model,
            similarity=(result.metrics.similarity_score if result.metrics else None),
        )
        return result, docs, meta

    @staticmethod
    def _cross_check_metrics(result: ComparisonResult, docs: ComparedDocuments) -> ComparisonResult:
        """Clamp metric counters so they can never exceed the clause union.

        Gemini justifies similarity from matched clauses; this guard keeps
        invented counts bounded by the deterministic union size instead of
        rejecting (and losing) an otherwise valid comparison.
        """
        union_size = len(merge_clause_titles(docs.analysis_a, docs.analysis_b))
        metrics = result.metrics
        if metrics is None:
            return result
        data = metrics.model_dump(mode="python")
        for key in ("total_clauses_compared", "clauses_matched", "clauses_changed", "clauses_added", "clauses_removed"):
            value = data.get(key, 0)
            if not isinstance(value, int) or value < 0:
                data[key] = 0
            elif union_size and value > union_size:
                data[key] = union_size
                warning("Comparison metric clamped to clause union", metric=key, union_size=union_size)
        if not data.get("similarity_justification"):
            data["similarity_justification"] = (
                f"Similarity {data.get('similarity_score', 0)} based on "
                f"{data.get('clauses_matched', 0)} matched of "
                f"{data.get('total_clauses_compared', 0)} compared clauses."
            )
        data["similarity_justification"] = str(data["similarity_justification"]).strip()
        updated = metrics.model_copy(update=data)
        return result.model_copy(update={"metrics": updated})
