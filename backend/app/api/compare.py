"""API endpoints for clause-by-clause document comparison."""

import asyncio
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError

from app.core.security import AuthenticatedUser, get_current_user
from app.core.supabase import get_supabase
from app.repositories.compare_repository import ComparisonRepository
from app.schemas.compare_schema import (
    CompareRequest,
    ComparisonResponse,
    ComparisonResult,
)
from app.services.compare_service import (
    CompareAnalysisPendingError,
    CompareDocumentNotFoundError,
    CompareForbiddenError,
    CompareGeminiError,
    CompareService,
    CompareServiceError,
    CompareValidationError,
)

router = APIRouter(prefix="/compare", tags=["compare"])


def _row_to_response(
    row: dict, a_id: UUID, b_id: UUID, docs: dict[str, dict], *, cached: bool
) -> ComparisonResponse:
    """Build a ``ComparisonResponse`` from a stored row (or fresh values)."""
    result_raw = row.get("result") if isinstance(row, dict) else None
    try:
        result = ComparisonResult.model_validate(result_raw)
    except (ValidationError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The stored comparison is invalid.",
        ) from exc
    created_at = row.get("created_at") if isinstance(row, dict) else None
    try:
        parsed_created = (
            datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            if created_at
            else datetime.now(timezone.utc)
        )
    except ValueError:
        parsed_created = datetime.now(timezone.utc)
    comparison_id = row.get("id") if isinstance(row, dict) else None
    try:
        parsed_id = UUID(str(comparison_id)) if comparison_id else uuid4()
    except ValueError:
        parsed_id = uuid4()
    doc_a = docs.get("a", {})
    doc_b = docs.get("b", {})
    return ComparisonResponse(
        comparison_id=parsed_id,
        document_a_id=a_id,
        document_b_id=b_id,
        document_a_title=str(doc_a.get("title") or ""),
        document_b_title=str(doc_b.get("title") or ""),
        document_a_type=str(doc_a.get("document_type") or ""),
        document_b_type=str(doc_b.get("document_type") or ""),
        created_at=parsed_created,
        cached=cached,
        result=result,
    )


@router.post("", response_model=ComparisonResponse, summary="Compare two legal documents")
async def compare_documents(
    payload: CompareRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> ComparisonResponse:
    """Compare two analyzed documents owned by the authenticated user.

    Uses only the stored structured analyses (never OCR/embeddings).
    Returns the cached comparison when the pair was compared before.
    """
    client = get_supabase()
    service = CompareService(client)
    repository = ComparisonRepository(client)

    # Fast path: return the cached comparison without calling Gemini.
    # Cache lookup never raises (missing table => None).
    try:
        cached = repository.find_cached(payload.document_a_id, payload.document_b_id, current_user.id)
    except Exception:  # noqa: BLE001 - repository already swallows; belt-and-braces
        cached = None
    if cached:
        try:
            row_a, row_b = await asyncio.gather(
                asyncio.to_thread(service._fetch_row, payload.document_a_id, _metadata_only=True),
                asyncio.to_thread(service._fetch_row, payload.document_b_id, _metadata_only=True),
            )
            docs = {"a": row_a or {}, "b": row_b or {}}
        except CompareServiceError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Documents are temporarily unavailable.") from exc
        return _row_to_response(cached, payload.document_a_id, payload.document_b_id, docs, cached=True)

    try:
        result, compared, _meta = await service.compare(
            payload.document_a_id, payload.document_b_id, current_user.id
        )
    except CompareDocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.") from exc
    except CompareForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this document.",
        ) from exc
    except CompareAnalysisPendingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "One or more documents are still being analyzed.",
                "document_a_ready": exc.document_a_ready,
                "document_b_ready": exc.document_b_ready,
                "retryable": True,
            },
        ) from exc
    except CompareValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The comparison provider returned an invalid response.",
        ) from exc
    except CompareGeminiError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document comparison is temporarily unavailable. Please try again in a minute.",
        ) from exc
    except CompareServiceError as exc:
        if "itself" in str(exc):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Document comparison failed.") from exc

    result_json = result.model_dump(mode="json")
    try:
        stored = repository.save(
            payload.document_a_id, payload.document_b_id, current_user.id, result_json
        )
    except Exception:  # noqa: BLE001 - persistence must never fail the request
        stored = None
    docs = {"a": compared.document_a, "b": compared.document_b}
    if stored:
        return _row_to_response(stored, payload.document_a_id, payload.document_b_id, docs, cached=False)
    # Persistence unavailable (migrations not run): still return the result.
    return ComparisonResponse(
        comparison_id=uuid4(),
        document_a_id=payload.document_a_id,
        document_b_id=payload.document_b_id,
        document_a_title=str(compared.document_a.get("title") or ""),
        document_b_title=str(compared.document_b.get("title") or ""),
        document_a_type=str(compared.document_a.get("document_type") or ""),
        document_b_type=str(compared.document_b.get("document_type") or ""),
        created_at=datetime.now(timezone.utc),
        cached=False,
        result=result,
    )


@router.get("", summary="List recent comparisons")
async def list_comparisons(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[dict]:
    """Return the authenticated user's most recent comparisons."""
    repository = ComparisonRepository(get_supabase())
    return repository.list_for_user(current_user.id, limit=limit)
