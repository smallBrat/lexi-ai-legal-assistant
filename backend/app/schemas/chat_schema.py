"""Pydantic schemas for document-grounded legal chat."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """Question to answer from one uploaded document."""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    question: str = Field(min_length=1, max_length=4000)


class ChatQuestionRequest(BaseModel):
    """Question body for the document-scoped compatibility endpoint."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)


class Citation(BaseModel):
    """A retrieved clause supporting a chat answer."""

    model_config = ConfigDict(extra="forbid")

    clause_title: str
    excerpt: str
    page_number: int | None = None
    similarity_score: float = Field(ge=0, le=1)


class ChatResponse(BaseModel):
    """Structured answer grounded in retrieved document clauses."""

    model_config = ConfigDict(extra="forbid")

    answer: str
    confidence_score: int = Field(ge=0, le=100)
    citations: list[Citation]
    follow_up_questions: list[str]


class ChatHistoryItem(ChatResponse):
    """Stored chat exchange.

    ``follow_up_questions`` defaults to ``[]`` because persisted
    ``chat_history`` rows predate that column — rows are normalized in
    ``ChatRepository.get_history`` (the single mapping place) and this
    default keeps validation from ever 500ing on legacy rows.
    """

    question: str
    document_id: UUID
    user_id: str
    timestamp: datetime
    follow_up_questions: list[str] = Field(default_factory=list)


class ChatHistoryResponse(BaseModel):
    """Conversation history for a document."""

    items: list[ChatHistoryItem]


class ChatDeleteResponse(BaseModel):
    """Result of deleting document chat history."""

    document_id: UUID
    deleted: bool
    message: str
