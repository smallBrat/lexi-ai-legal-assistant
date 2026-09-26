"""Authenticated documents API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import AuthenticatedUser, get_current_user
from app.core.supabase import get_supabase
from app.repositories.document_repository import DocumentRepository
from app.schemas.document_schema import (
    DocumentDeleteResponse,
    DocumentDetail,
    DocumentListResponse,
    DocumentStatus,
    DocumentType,
    DocumentUpdateRequest,
    SignedUrlResponse,
    SortField,
    SortOrder,
)
from app.services.document_service import (
    DocumentForbiddenError,
    DocumentNotFoundError,
    DocumentService,
    DocumentServiceError,
)
from app.services.storage_service import StorageService

router = APIRouter(prefix="/documents", tags=["documents"])


def get_document_service() -> DocumentService:
    """Build the document service from the configured Supabase client."""
    client = get_supabase()
    return DocumentService(DocumentRepository(client), StorageService(client))


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    document_type: Annotated[DocumentType | None, Query()] = None,
    risk_level: Annotated[str | None, Query()] = None,
    document_status: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    sort: Annotated[SortField, Query()] = SortField.CREATED_AT,
    order: Annotated[SortOrder, Query()] = SortOrder.DESC,
) -> DocumentListResponse:
    """Return the authenticated user's paginated documents."""
    if risk_level is not None and risk_level not in {"low", "medium", "high"}:
        raise HTTPException(status_code=422, detail="Invalid risk_level filter.")
    service = get_document_service()
    try:
        return await service.list_documents(
            current_user.id,
            page=page,
            page_size=page_size,
            search=search.strip() if search else None,
            document_type=document_type.value if document_type else None,
            risk_level=risk_level,
            status=document_status.value if document_status else None,
            sort=sort.value,
            order=order.value,
        )
    except DocumentServiceError as exc:
        raise HTTPException(status_code=503, detail="Documents are temporarily unavailable.") from exc


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> DocumentDetail:
    """Return one authenticated user's document and analysis."""
    try:
        return await get_document_service().get_document(document_id, current_user.id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except DocumentForbiddenError as exc:
        raise HTTPException(status_code=403, detail="You do not have access to this document.") from exc
    except DocumentServiceError as exc:
        raise HTTPException(status_code=503, detail="Document is temporarily unavailable.") from exc


@router.patch("/{document_id}", response_model=DocumentDetail)
async def update_document(
    document_id: UUID,
    payload: DocumentUpdateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> DocumentDetail:
    """Update the title or type of an owned document."""
    try:
        return await get_document_service().update_document(
            document_id,
            current_user.id,
            payload.model_dump(mode="json", exclude_none=True),
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except DocumentForbiddenError as exc:
        raise HTTPException(status_code=403, detail="You do not have access to this document.") from exc
    except DocumentServiceError as exc:
        raise HTTPException(status_code=503, detail="Document could not be updated.") from exc


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> DocumentDeleteResponse:
    """Delete an owned document and its related records."""
    try:
        return await get_document_service().delete_document(document_id, current_user.id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except DocumentForbiddenError as exc:
        raise HTTPException(status_code=403, detail="You do not have access to this document.") from exc
    except DocumentServiceError as exc:
        raise HTTPException(status_code=503, detail="Document could not be deleted.") from exc


@router.get("/{document_id}/signed-url", response_model=SignedUrlResponse)
async def get_signed_url(
    document_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> SignedUrlResponse:
    """Return a 15-minute signed URL for an owned document."""
    try:
        return await get_document_service().signed_url(document_id, current_user.id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except DocumentForbiddenError as exc:
        raise HTTPException(status_code=403, detail="You do not have access to this document.") from exc
    except DocumentServiceError as exc:
        raise HTTPException(status_code=503, detail="Document file is unavailable.") from exc
