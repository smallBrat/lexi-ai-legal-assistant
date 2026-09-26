"""API endpoint for structured legal document analysis."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.core.security import AuthenticatedUser, get_current_user
from app.core.supabase import get_supabase
from app.schemas.analysis_schema import LegalAnalysis
from app.services.analysis_service import (
    AnalysisDatabaseError,
    AnalysisService,
    AnalysisValidationError,
    DocumentNotFoundError,
    EmptyDocumentError,
)
from app.services.gemini_service import (
    GeminiInvalidJSONError,
    GeminiService,
    GeminiServiceError,
    GeminiTimeoutError,
    ModelUnavailableError,
)

router = APIRouter(tags=["analysis"])

MODEL_UNAVAILABLE_BODY = {
    "detail": "AI analysis is temporarily unavailable.",
    "retryable": True,
    "error_code": "MODEL_UNAVAILABLE",
}


@router.post(
    "/analyze/{document_id}",
    response_model=LegalAnalysis,
    summary="Analyze a legal document",
)
async def analyze_document(
    document_id: UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    force: Annotated[bool, Query()] = False,
) -> LegalAnalysis:
    """Return validated, structured analysis for an owned document."""
    try:
        service = AnalysisService(get_supabase(), GeminiService())
        return await service.analyze_document(document_id, current_user.id, force=force)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        ) from exc
    except EmptyDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The document has no extracted text.",
        ) from exc
    except (ModelUnavailableError, GeminiTimeoutError):
        # All free-tier models exhausted: structured, retryable 503 with no
        # stack trace. The document row was already marked analysis_failed.
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=dict(MODEL_UNAVAILABLE_BODY),
        )
    except (GeminiInvalidJSONError, AnalysisValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The analysis provider returned an invalid response.",
        ) from exc
    except GeminiServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI analysis is temporarily unavailable. Please try again in a minute.",
        ) from exc
    except AnalysisDatabaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document analysis could not be persisted.",
        ) from exc
