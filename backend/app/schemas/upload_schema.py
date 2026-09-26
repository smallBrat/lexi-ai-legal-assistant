"""Schemas for document upload requests and responses."""

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentType(str, Enum):
    """Supported legal document categories."""

    EMPLOYMENT = "employment"
    RENTAL = "rental"
    INSURANCE = "insurance"
    NDA = "NDA"
    LOAN = "loan"
    GOVERNMENT = "government"
    OTHER = "other"


class UploadResponse(BaseModel):
    """Response returned after a document is processed."""

    model_config = ConfigDict(use_enum_values=True)

    document_id: UUID
    title: str
    document_type: DocumentType
    status: Literal["processing", "completed"]
    pages: int
    character_count: int
    text_preview: str = Field(max_length=800)
    message: str | None = None
    storage_path: str
    created_at: datetime
