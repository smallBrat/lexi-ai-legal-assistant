"""Application service for retrieving, analyzing, and storing document analysis."""

import asyncio
import traceback
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from uuid import UUID

from pydantic import ValidationError

try:
    from postgrest.exceptions import APIError
except ImportError:  # pragma: no cover
    APIError = None  # type: ignore[assignment,misc]

from app.core.logging import error, info
from app.schemas.analysis_schema import LegalAnalysis, RiskLevel
from app.services.gemini_service import (
    MODEL_NAME,
    MODEL_PRIORITY,
    PROMPT_VERSION,
    GeminiService,
    GeminiServiceError,
    GeminiTimeoutError,
    ModelUnavailableError,
)
from app.services.embedding_service import get_embedding_service

MODEL_PRIORITY_FIRST = MODEL_PRIORITY[0] if MODEL_PRIORITY else MODEL_NAME

RISK_WEIGHTS = {
    "financial": (20, ("penalt", "fine", "fee", "liquidated", "late charge")),
    "termination": (20, ("termination", "terminate", "renewal", "renew", "cancellation")),
    "liability": (20, ("liability", "indemn", "hold harmless", "limitation of liability")),
    "privacy": (15, ("personal data", "privacy", "data protection", "processing data")),
    "missing_obligations": (15, ("not specified", "unclear", "ambiguous", "no deadline")),
    "restrictive": (10, ("non-compete", "non-solicit", "exclusivity", "restrictive covenant")),
}


class AnalysisServiceError(Exception):
    """Base exception for analysis workflow failures."""


class EmptyDocumentError(AnalysisServiceError):
    """Raised when a document has no extracted text."""


class DocumentNotFoundError(AnalysisServiceError):
    """Raised when a document is not owned by the requesting user."""


class AnalysisDatabaseError(AnalysisServiceError):
    """Raised when document retrieval or analysis persistence fails."""


class AnalysisValidationError(AnalysisServiceError):
    """Raised when Gemini JSON does not match the analysis contract."""


class AnalysisService:
    """Coordinate document lookup, Gemini analysis, validation, and persistence."""

    def __init__(self, client: Any, gemini_service: GeminiService) -> None:
        """Initialize the service with Supabase and Gemini boundaries."""
        self._client = client
        self._gemini_service = gemini_service

    def _fetch_document(self, document_id: UUID, user_id: str) -> dict[str, Any]:
        """Fetch extracted text for a document owned by the user."""
        try:
            response = (
                self._client.table("documents")
                .select(
                    "id,document_type,extracted_text,user_id,analysis,"
                    "analysis_model,analysis_prompt_version,analyzed_at"
                )
                .eq("id", str(document_id))
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise AnalysisDatabaseError("Unable to fetch document") from exc
        records = response.data or []
        if not records:
            raise DocumentNotFoundError("Document was not found")
        return records[0]

    def _store_analysis(
        self,
        document_id: UUID,
        analysis: LegalAnalysis,
        analyzed_at: datetime,
        model_name: str = MODEL_NAME,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist validated analysis JSON on the document record."""
        try:
            payload: dict[str, Any] = {
                "analysis": analysis.model_dump(mode="json"),
                "analysis_model": model_name,
                "analysis_prompt_version": PROMPT_VERSION,
                "analyzed_at": analyzed_at.isoformat(),
            }
            if metadata is not None:
                payload["analysis_metadata"] = metadata
            response = (
                self._client.table("documents")
                .update(payload)
                .eq("id", str(document_id))
                .select("id")
                .execute()
            )
            if response.data is not None and not response.data:
                raise AnalysisDatabaseError("Analysis update affected no records")
        except AnalysisDatabaseError:
            raise
        except APIError as exc:
            error(
                "PostgREST APIError during analysis persistence",
                api_message=exc.message,
                api_code=exc.code,
                api_details=exc.details,
                api_hint=exc.hint,
                document_id=str(document_id),
                model_name=model_name,
                metadata=metadata,
            )
            raise AnalysisDatabaseError("Unable to store analysis") from exc
        except Exception as exc:
            error(
                "Analysis persistence failed",
                exc_type=type(exc).__name__,
                exc_message=str(exc),
                exc_repr=repr(exc),
                document_id=str(document_id),
                model_name=model_name,
                metadata=metadata,
            )
            raise AnalysisDatabaseError("Unable to store analysis") from exc

    def _store_failure(
        self,
        document_id: UUID,
        user_id: str,
        metadata: dict[str, Any],
        has_analysis: bool,
    ) -> None:
        """Mark a document as ``analysis_failed`` without touching analysis.

        When the document already holds a successful analysis (e.g. a forced
        retry failed), only the metadata is updated so the good analysis is
        never overwritten. Failures to persist the failure state are logged
        and swallowed — the caller still raises the overload error.
        """
        try:
            payload: dict[str, Any] = {"analysis_metadata": metadata}
            if not has_analysis:
                payload["status"] = "analysis_failed"
            response = (
                self._client.table("documents")
                .update(payload)
                .eq("id", str(document_id))
                .eq("user_id", user_id)
                .execute()
            )
            if response.data is not None and not response.data:
                error(
                    "Analysis failure state affected no records",
                    document_id=str(document_id),
                )
        except Exception as exc:
            error(
                "Analysis failure persistence failed",
                exc_type=type(exc).__name__,
                exc_repr=repr(exc),
                document_id=str(document_id),
            )

    @staticmethod
    def _overload_context(exc: BaseException) -> dict[str, Any]:
        """Extract structured overload context from a Gemini failure."""
        if isinstance(exc, ModelUnavailableError):
            return {
                "attempted_models": list(exc.attempted_models),
                "last_model": exc.last_model,
                "last_status_code": exc.last_status_code,
                "failure_reason": exc.failure_reason,
            }
        return {
            "attempted_models": [],
            "last_model": None,
            "last_status_code": None,
            "failure_reason": "timeout"
            if isinstance(exc, GeminiTimeoutError)
            else "unknown",
        }

    @staticmethod
    def _apply_risk_fallback(analysis: LegalAnalysis) -> LegalAnalysis:
        """Derive a risk level from risk score when Gemini omits it."""
        if analysis.risk_level is not None:
            return analysis
        if analysis.risk_score < 34:
            risk_level = RiskLevel.LOW
        elif analysis.risk_score < 67:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.HIGH
        return analysis.model_copy(update={"risk_level": risk_level})

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """Collapse whitespace and line breaks for fuzzy excerpt matching."""
        return " ".join(text.split())

    @staticmethod
    def _normalize(analysis: LegalAnalysis, document_text: str) -> LegalAnalysis:
        """Normalize text collections, verify excerpts, and preserve risk."""
        data = analysis.model_dump(mode="python")

        def clean(value: Any) -> Any:
            if isinstance(value, str):
                return value.strip()
            if isinstance(value, list):
                return [clean(item) for item in value]
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items()}
            return value

        data = clean(data)
        # Preserve Gemini risk values; fall back to heuristics only if invalid.
        gemini_score = data.get("risk_score")
        gemini_level = data.get("risk_level")
        data["risk_reasons"] = AnalysisService._unique_strings(data["risk_reasons"])
        normalized_doc = AnalysisService._normalize_whitespace(document_text)
        verified_clauses: list[dict[str, Any]] = []
        seen_clauses: set[tuple[str, str]] = set()
        rejected_count = 0
        for index, clause in enumerate(data["clauses"]):
            title = clause.get("title", "")
            excerpt = clause.get("original_text", "")
            category = clause.get("category", "")
            risk_level = clause.get("risk_level", "")

            if not title:
                info("Clause rejected: missing title", clause_index=index)
                rejected_count += 1
                continue
            if not excerpt:
                info("Clause rejected: missing original_text", clause_index=index, title=title)
                rejected_count += 1
                continue
            if not category:
                info("Clause rejected: missing category", clause_index=index, title=title)
            if not risk_level:
                info("Clause rejected: missing risk_level", clause_index=index, title=title)

            normalized_excerpt = AnalysisService._normalize_whitespace(excerpt)
            excerpt_in_doc = bool(normalized_excerpt) and (
                normalized_excerpt in normalized_doc or excerpt in document_text
            )
            if not excerpt_in_doc:
                info(
                    "Clause excerpt not verified in document (kept anyway)",
                    clause_index=index,
                    title=title,
                    excerpt_length=len(excerpt),
                    document_length=len(document_text),
                )

            key = (title.casefold(), excerpt.casefold())
            if key in seen_clauses:
                info("Clause rejected: duplicate", clause_index=index, title=title)
                rejected_count += 1
                continue
            seen_clauses.add(key)
            verified_clauses.append(clause)

        if rejected_count > 0:
            info(
                "Clause filtering summary",
                total_input=len(data["clauses"]),
                accepted=len(verified_clauses),
                rejected=rejected_count,
            )
        data["clauses"] = verified_clauses
        data["obligations"] = AnalysisService._unique_objects(
            data["obligations"], ("who", "action", "deadline", "priority")
        )
        data["glossary"] = AnalysisService._unique_objects(
            data["glossary"], ("term", "definition"), primary_key="term"
        )
        data["risk_reasons"] = AnalysisService._unique_strings(data["risk_reasons"])
        data["questions_for_lawyer"] = AnalysisService._unique_strings(
            data["questions_for_lawyer"]
        )
        data["timeline"] = AnalysisService._unique_objects(
            data["timeline"], ("date", "event", "description")
        )
        data["timeline"].sort(key=AnalysisService._timeline_key)
        valid_score = isinstance(gemini_score, int) and 0 <= gemini_score <= 100
        valid_levels = {level.value for level in RiskLevel}
        valid_level = gemini_level in valid_levels
        if not valid_score:
            evidence = " ".join(
                [
                    *data["risk_reasons"],
                    *[str(item) for item in data["clauses"]],
                ]
            ).casefold()
            data["risk_score"] = min(
                100,
                sum(weight for weight, keywords in RISK_WEIGHTS.values() if any(keyword in evidence for keyword in keywords)),
            )
        if not valid_level:
            data["risk_level"] = AnalysisService._risk_level(data["risk_score"])
        return LegalAnalysis.model_validate(data)

    @staticmethod
    def _unique_strings(values: list[str]) -> list[str]:
        """Trim and deduplicate strings while preserving model order."""
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                result.append(value)
        return result

    @staticmethod
    def _unique_objects(
        values: list[dict[str, Any]], fields: tuple[str, ...], primary_key: str | None = None
    ) -> list[dict[str, Any]]:
        """Deduplicate structured collection items while preserving order."""
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for value in values:
            key = str(value.get(primary_key, "") if primary_key else tuple(value.get(field, "") for field in fields)).casefold()
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result

    @staticmethod
    def _timeline_key(item: dict[str, Any]) -> tuple[int, str]:
        """Sort ISO-like dates first and undated events afterward."""
        date = str(item.get("date", ""))
        try:
            parsed = datetime.fromisoformat(date.replace("Z", "+00:00"))
            return 0, parsed.isoformat()
        except ValueError:
            return 1, date

    @staticmethod
    def _risk_level(score: int) -> RiskLevel:
        """Map the deterministic risk score to a stable level."""
        if score < 34:
            return RiskLevel.LOW
        if score < 67:
            return RiskLevel.MEDIUM
        return RiskLevel.HIGH

    async def analyze_document(
        self, document_id: UUID, user_id: str, force: bool = False
    ) -> LegalAnalysis:
        """Analyze a user's extracted document text and persist the result."""
        started_at = perf_counter()
        stage = "initialization"
        try:
            info("Analysis started", document_id=str(document_id), user_id=user_id)
            document = await asyncio.to_thread(self._fetch_document, document_id, user_id)
            if not force and document.get("analysis"):
                try:
                    cached = LegalAnalysis.model_validate(document["analysis"])
                    info(
                        "Analysis finished",
                        document_id=str(document_id),
                        model=document.get("analysis_model") or MODEL_NAME,
                        prompt_version=document.get("analysis_prompt_version") or PROMPT_VERSION,
                        retry_count=0,
                        duration_ms=round((perf_counter() - started_at) * 1000, 2),
                        input_characters=0,
                        output_characters=len(str(document["analysis"])),
                        cached=True,
                    )
                    return cached
                except (ValidationError, TypeError, ValueError) as exc:
                    error("Cached analysis is invalid", document_id=str(document_id), error=str(exc))
            document_text = str(document.get("extracted_text") or "").strip()
            if not document_text:
                raise EmptyDocumentError("Document has no extracted text")

            stage = "gemini_call"
            retry_count = 0
            gemini_latency_ms: float = 0.0
            gemini_fallback_used = False

            def _unpack_gemini_result(value: Any) -> tuple[str, str, float, int, bool]:
                """Support GeminiResult, (text, model), and legacy str mocks."""
                if isinstance(value, str):
                    return value, MODEL_NAME, 0.0, 0, False
                if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
                    return value[0], value[1], 0.0, 0, value[1] != MODEL_PRIORITY_FIRST
                model = getattr(value, "model", MODEL_NAME)
                return (
                    getattr(value, "text", value),
                    model,
                    float(getattr(value, "latency_ms", 0.0)),
                    int(getattr(value, "retry_count", 0)),
                    bool(getattr(value, "fallback_used", model != MODEL_PRIORITY_FIRST)),
                )

            gemini_started_at = perf_counter()
            try:
                gemini_out = await self._gemini_service.analyze_document(document_text)
            except (GeminiTimeoutError, ModelUnavailableError) as exc:
                context = self._overload_context(exc)
                failed_at = datetime.now(timezone.utc).isoformat()
                await asyncio.to_thread(
                    self._store_failure,
                    document_id,
                    user_id,
                    {
                        "error": "MODEL_UNAVAILABLE",
                        "retryable": True,
                        "last_model": context["last_model"],
                        "attempted_models": context["attempted_models"],
                        "failed_at": failed_at,
                    },
                    bool(document.get("analysis")),
                )
                error(
                    "Analysis failed",
                    document_id=str(document_id),
                    attempted_models=context["attempted_models"],
                    last_status_code=context["last_status_code"],
                    retryable=True,
                    failure_reason=context["failure_reason"],
                )
                raise
            raw_json, model_used, gemini_latency_ms, gemini_retries, gemini_fallback_used = _unpack_gemini_result(gemini_out)

            stage = "json_parse"
            try:
                analysis = LegalAnalysis.model_validate_json(raw_json)
            except (ValidationError, ValueError) as exc:
                retry_count = 1
                correction = (
                    "Return one JSON object matching the required schema. "
                    f"Correct these validation errors: {str(exc)[:1500]}"
                )
                gemini_out = await self._gemini_service.analyze_document(
                    document_text, correction=correction
                )
                raw_json, model_used, gemini_latency_ms, gemini_retries, gemini_fallback_used = _unpack_gemini_result(gemini_out)
                try:
                    analysis = LegalAnalysis.model_validate_json(raw_json)
                except (ValidationError, ValueError) as retry_exc:
                    error(
                        "Analysis JSON validation failed",
                        document_id=str(document_id),
                        error=str(retry_exc),
                    )
                    raise AnalysisValidationError(
                        "Gemini response failed schema validation"
                    ) from retry_exc

            stage = "schema_validate"
            normalized = self._normalize(analysis, document_text)
            output_characters = len(raw_json)
            total_retry_count = retry_count + gemini_retries

            # ---- Stage: Embed clauses into ChromaDB for chat retrieval ----
            try:
                embedding_service = get_embedding_service()
                await asyncio.to_thread(
                    embedding_service.index_clauses,
                    user_id,
                    document_id,
                    normalized.clauses,
                )
                info(
                    "Analysis indexing done",
                    document_id=str(document_id),
                    clause_count=len(normalized.clauses),
                )
            except Exception as exc:
                from app.services.embedding_service import EmbeddingService

                error(
                    "Analysis indexing failed",
                    document_id=str(document_id),
                    clause_count=len(normalized.clauses),
                    embedding_count=0,
                    collection_name=EmbeddingService._collection_name(
                        user_id, document_id
                    ),
                    exc_type=type(exc).__name__,
                    exc_message=str(exc),
                    exc_repr=repr(exc),
                    traceback=traceback.format_exc(),
                )

            stage = "persist"
            analyzed_at = datetime.now(timezone.utc)
            analysis_metadata: dict[str, Any] = {
                "model": model_used,
                "latency_ms": gemini_latency_ms or round((perf_counter() - gemini_started_at) * 1000, 2),
                "retry_count": total_retry_count,
                "fallback_used": gemini_fallback_used,
                "prompt_version": PROMPT_VERSION,
            }
            await asyncio.to_thread(
                self._store_analysis, document_id, normalized, analyzed_at, model_used, analysis_metadata
            )

            info(
                "Analysis finished",
                document_id=str(document_id),
                model=model_used,
                latency_ms=gemini_latency_ms,
                retry_count=total_retry_count,
                fallback_used=gemini_fallback_used,
                input_characters=len(document_text),
                output_characters=output_characters,
            )
            return normalized
        except EmptyDocumentError:
            raise
        except AnalysisValidationError:
            raise
        except DocumentNotFoundError:
            raise
        except AnalysisDatabaseError:
            raise
        except (GeminiTimeoutError, ModelUnavailableError, GeminiServiceError):
            raise
        except Exception as exc:
            error_details: dict[str, Any] = {
                "document_id": str(document_id),
                "stage": stage,
                "exc_type": type(exc).__name__,
                "exc_message": str(exc),
                "exc_repr": repr(exc),
            }
            if isinstance(exc, ValidationError):
                error_details["validation_errors"] = exc.errors()
                error_details["validation_error_count"] = len(exc.errors())
            cause = getattr(exc, "__cause__", None)
            if APIError is not None and isinstance(cause, APIError):
                error_details["api_message"] = cause.message
                error_details["api_code"] = cause.code
                error_details["api_details"] = cause.details
                error_details["api_hint"] = cause.hint
            error("Analysis pipeline failed", **error_details)
            raise AnalysisServiceError(f"Analysis failed at stage: {stage}") from exc
