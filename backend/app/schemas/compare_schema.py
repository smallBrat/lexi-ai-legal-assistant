"""Pydantic schemas for deterministic clause-by-clause document comparison.

The comparison pipeline NEVER reruns OCR or embeddings: it reuses the two
stored ``LegalAnalysis`` objects and asks Gemini only for comparison
reasoning. Every model is strict (``extra="forbid"``) so the Gemini
response schema and the API response contract can never drift apart.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base model that rejects fields outside the comparison contract."""

    model_config = ConfigDict(extra="forbid")


class ClauseSimilarity(str, Enum):
    """How alike a matched clause is across the two documents."""

    IDENTICAL = "identical"
    SIMILAR = "similar"
    CHANGED = "changed"
    ADDED = "added"
    REMOVED = "removed"


class RiskSeverity(str, Enum):
    """Severity bucket for an added/removed risk."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CompareRequest(StrictModel):
    """Request body for ``POST /compare``."""

    document_a_id: UUID
    document_b_id: UUID

    model_config = ConfigDict(extra="forbid")


class SummaryComparison(StrictModel):
    """Side-by-side summary metadata for both documents."""

    purpose_a: str = ""
    purpose_b: str = ""
    parties_a: str = ""
    parties_b: str = ""
    agreement_type_a: str = ""
    agreement_type_b: str = ""
    effective_dates_a: str = ""
    effective_dates_b: str = ""
    expiry_a: str = ""
    expiry_b: str = ""
    jurisdiction_a: str = ""
    jurisdiction_b: str = ""
    governing_law_a: str = ""
    governing_law_b: str = ""


class ClauseComparison(StrictModel):
    """One clause compared across both documents."""

    clause_name: str = Field(min_length=1)
    present_in_a: bool = False
    present_in_b: bool = False
    similarity: ClauseSimilarity = ClauseSimilarity.CHANGED
    text_a: str = ""
    text_b: str = ""
    difference_explanation: str = ""
    additional_obligations: str = ""


class RightsComparison(StrictModel):
    """Rights added or removed for one party role."""

    role: str = Field(min_length=1)
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)


class ObligationComparison(StrictModel):
    """One obligation compared side-by-side."""

    obligation: str = Field(min_length=1)
    party_a: str = ""
    party_b: str = ""
    detail_a: str = ""
    detail_b: str = ""
    changed: bool = False


class RiskComparison(StrictModel):
    """One risk delta between the two documents."""

    risk: str = Field(min_length=1)
    severity: RiskSeverity = RiskSeverity.MEDIUM
    added: bool = False
    removed: bool = False
    explanation: str = ""


class FinancialComparison(StrictModel):
    """One financial term compared side-by-side."""

    term: str = Field(min_length=1)
    value_a: str = ""
    value_b: str = ""
    changed: bool = False


class TimelineComparison(StrictModel):
    """One deadline/notice/renewal item compared side-by-side."""

    event: str = Field(min_length=1)
    value_a: str = ""
    value_b: str = ""
    changed: bool = False


class MissingClause(StrictModel):
    """A clause present on one side but absent on the other."""

    clause_name: str = Field(min_length=1)
    missing_from: str = Field(min_length=1)
    excerpt: str = ""


class ComparisonMetrics(StrictModel):
    """Overall difference metrics — always justified by matched clauses."""

    similarity_score: int = Field(ge=0, le=100)
    total_clauses_compared: int = Field(ge=0)
    clauses_matched: int = Field(ge=0)
    clauses_changed: int = Field(ge=0)
    clauses_added: int = Field(ge=0)
    clauses_removed: int = Field(ge=0)
    similarity_justification: str = ""


class ComparisonResult(StrictModel):
    """Structured Gemini comparison of two stored legal analyses."""

    summary: SummaryComparison = Field(default_factory=SummaryComparison)
    clauses: list[ClauseComparison] = Field(default_factory=list)
    rights: list[RightsComparison] = Field(default_factory=list)
    obligations: list[ObligationComparison] = Field(default_factory=list)
    risks: list[RiskComparison] = Field(default_factory=list)
    financials: list[FinancialComparison] = Field(default_factory=list)
    timeline: list[TimelineComparison] = Field(default_factory=list)
    missing_clauses: list[MissingClause] = Field(default_factory=list)
    metrics: ComparisonMetrics | None = None


class ComparisonResponse(BaseModel):
    """API response for a document comparison (cached or freshly computed)."""

    model_config = ConfigDict(extra="forbid")

    comparison_id: UUID
    document_a_id: UUID
    document_b_id: UUID
    document_a_title: str = ""
    document_b_title: str = ""
    document_a_type: str = ""
    document_b_type: str = ""
    created_at: datetime
    cached: bool = False
    result: ComparisonResult


class ComparisonPendingResponse(BaseModel):
    """Returned when one or both documents are not analyzed yet (HTTP 422)."""

    model_config = ConfigDict(extra="forbid")

    detail: str = "One or more documents are still being analyzed."
    document_a_ready: bool = False
    document_b_ready: bool = False
    retryable: bool = True
