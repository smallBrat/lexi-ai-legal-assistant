"""Schemas for the authenticated documents API."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.analysis_schema import (
    ClauseAnalysis,
    GlossaryItem,
    LegalAnalysis,
    Obligation,
    RiskLevel,
    TimelineItem,
)
from app.schemas.upload_schema import DocumentType


class DocumentStatus(str, Enum):
    """Document processing status."""

    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ANALYSIS_FAILED = "analysis_failed"


class SortField(str, Enum):
    """Allowed document sort fields."""

    CREATED_AT = "created_at"
    RISK_SCORE = "risk_score"
    TITLE = "title"


class SortOrder(str, Enum):
    """Allowed sort directions."""

    ASC = "asc"
    DESC = "desc"


class DocumentUpdateRequest(BaseModel):
    """Fields that may be changed on a document."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    document_type: DocumentType | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        """Trim titles and reject control characters."""
        if value is None:
            return None
        value = value.strip()
        if not value or any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("Title must contain printable characters.")
        return value


class DocumentListItem(BaseModel):
    """Document metadata returned in a list."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    document_type: DocumentType
    status: DocumentStatus
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel | None = None
    flag_count: int = Field(ge=0, default=0)
    pages: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime | None = None
    summary_preview: str
    storage_path: str
    signed_preview_url: str | None = None


class DocumentDetail(DocumentListItem):
    """Full document metadata and analysis."""

    analysis: LegalAnalysis | None = None
    clauses: list[ClauseAnalysis] = Field(default_factory=list)
    timeline: list[TimelineItem] = Field(default_factory=list)
    obligations: list[Obligation] = Field(default_factory=list)
    glossary: list[GlossaryItem] = Field(default_factory=list)
    questions_for_lawyer: list[str] = Field(default_factory=list)
    reading_difficulty: int | None = Field(default=None, ge=1, le=20)


class PaginationMetadata(BaseModel):
    """Pagination information for a document collection."""

    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class DocumentListResponse(BaseModel):
    """Paginated documents response."""

    items: list[DocumentListItem]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class DocumentDeleteResponse(BaseModel):
    """Result of a document deletion request."""

    document_id: UUID
    deleted: bool
    storage_deleted: bool
    message: str


class SignedUrlResponse(BaseModel):
    """Temporary URL for a private document."""

    document_id: UUID
    signed_url: str
    expires_in: int
