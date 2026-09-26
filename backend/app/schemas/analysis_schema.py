"""Pydantic schemas for deterministic legal document analysis."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(str, Enum):
    """Normalized document or clause risk level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StrictModel(BaseModel):
    """Base model that rejects fields not defined by the analysis contract."""

    model_config = ConfigDict(extra="forbid")


class ClauseAnalysis(StrictModel):
    """Analysis of one legally relevant clause."""

    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    risk_level: RiskLevel
    importance_score: int = Field(ge=0, le=100)
    original_text: str
    simplified_text: str
    why_it_matters: str


class Obligation(StrictModel):
    """Action that a party must perform under the document."""

    who: str
    action: str
    deadline: str
    priority: str


class TimelineItem(StrictModel):
    """Date or event identified in the document."""

    date: str
    event: str
    description: str


class GlossaryItem(StrictModel):
    """Plain-language definition of a legal term."""

    term: str
    definition: str


class LegalAnalysis(StrictModel):
    """Validated structured analysis returned to the frontend."""

    summary: str = Field(min_length=1)
    plain_english_summary: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    reading_difficulty: int = Field(ge=1, le=20)
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel | None = None
    risk_reasons: list[str]
    clauses: list[ClauseAnalysis]
    obligations: list[Obligation]
    timeline: list[TimelineItem]
    glossary: list[GlossaryItem]
    questions_for_lawyer: list[str]


AnalysisResponse = LegalAnalysis
