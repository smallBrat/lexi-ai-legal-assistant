"""Document upload and text extraction endpoint."""

import asyncio
import io
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings
from app.core.logging import error, info
from app.core.security import AuthenticatedUser, get_current_user
from app.core.supabase import get_supabase
from app.schemas.upload_schema import DocumentType, UploadResponse
from app.services.ocr_service import OCRResourceLimitError, OCRService, OCRServiceError
from app.services.storage_service import StorageService, StorageServiceError

try:
    from postgrest.exceptions import APIError
except ImportError:  # pragma: no cover - postgrest is a transitive dependency
    APIError = None  # type: ignore[assignment,misc]

router = APIRouter(tags=["upload"])

MAX_UPLOAD_SIZE = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "docx"}
DEFAULT_CONTENT_TYPE = "application/octet-stream"
MIME_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class UploadPipelineError(Exception):
    """Base exception for document upload failures."""


class DatabaseServiceError(UploadPipelineError):
    """Raised when document metadata cannot be persisted."""


async def _read_upload(file: UploadFile) -> bytes:
    """Read an upload while enforcing the maximum file size."""
    content = await file.read(MAX_UPLOAD_SIZE + 1)
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size must not exceed 20 MB.",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    return content


def _extension(filename: str | None) -> str:
    """Return a normalized filename extension."""
    return PurePosixPath(filename or "").suffix.lower().lstrip(".")


def _validate_content(content: bytes, extension: str, content_type: str | None) -> None:
    """Validate MIME type, magic bytes, and document integrity."""
    if content_type != MIME_TYPES[extension]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The file content type is not supported.",
        )
    try:
        if extension == "pdf":
            import fitz

            # Phase 15: reject PDFs whose page count alone exceeds the
            # processing limit before any parsing/OCR work happens.
            document = fitz.open(stream=content, filetype="pdf")
            try:
                settings = get_settings()
                if document.page_count > settings.MAX_PDF_PAGES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="The PDF exceeds processing limits.",
                    )
            finally:
                document.close()
            if not content.startswith(b"%PDF-"):
                raise ValueError("Invalid PDF signature")
        elif extension in {"png", "jpg", "jpeg"}:
            expected_signature = b"\x89PNG\r\n\x1a\n" if extension == "png" else b"\xff\xd8\xff"
            if not content.startswith(expected_signature):
                raise ValueError("Invalid image signature")
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
        else:
            if not zipfile.is_zipfile(io.BytesIO(content)):
                raise ValueError("Invalid DOCX archive")
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise ValueError("Invalid DOCX structure")
                # Phase 15: docx bomb guard. A 20MB DOCX that inflates to
                # hundreds of MB (or tens of thousands of entries) is a
                # decompression bomb against the parser.
                max_entries = 2_000
                if len(names) > max_entries:
                    raise ValueError("DOCX archive contains too many entries")
                total_uncompressed = sum(info.file_size for info in archive.infolist())
                if total_uncompressed > 200 * 1024 * 1024:
                    raise ValueError("DOCX archive is too large when decompressed")
    except (UnidentifiedImageError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The uploaded file is invalid or corrupted.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The uploaded file is invalid or corrupted.",
        ) from exc


def _validate_title(title: str | None, fallback: str) -> str:
    """Trim, sanitize, and validate a user-supplied document title."""
    from app.utils.sanitize import sanitize_text

    value = sanitize_text(title, 200) or (fallback[:200] if fallback else "")
    if len(value) > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Title must be 200 characters or fewer.",
        )
    return value


def _database_insert(client: Any, values: dict[str, Any]) -> None:
    """Insert document metadata into PostgreSQL through Supabase."""
    try:
        client.table("documents").insert(values).execute()
    except Exception as exc:
        raise DatabaseServiceError("Unable to save document metadata") from exc


def _database_update(client: Any, document_id: UUID, values: dict[str, Any]) -> None:
    """Update document processing metadata through Supabase."""
    try:
        client.table("documents").update(values).eq("id", str(document_id)).execute()
    except Exception as exc:
        raise DatabaseServiceError("Unable to update document metadata") from exc


def _log_api_error_details(exc: BaseException | None) -> dict[str, Any]:
    """Extract PostgREST APIError fields for structured logging.

    Returns a dict with ``message``, ``code``, ``details``, and ``hint``
    keys when the original exception is a PostgREST ``APIError``. Returns an
    empty dict otherwise so the caller can safely spread the result.
    """
    if APIError is None or not isinstance(exc, APIError):
        return {}
    return {
        "api_message": exc.message,
        "api_code": exc.code,
        "api_details": exc.details,
        "api_hint": exc.hint,
    }


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and extract a legal document",
)
async def upload_document(
    file: Annotated[UploadFile, File(...)],
    document_type: Annotated[DocumentType, Form(...)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    title: Annotated[str | None, Form()] = None,
) -> UploadResponse:
    """Store a legal document, extract its text, and return a preview."""
    extension = _extension(file.filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Supported file types are PDF, PNG, JPG, JPEG, and DOCX.",
        )

    info("Upload started", filename=file.filename, document_type=document_type.value)
    content = await _read_upload(file)
    _validate_content(content, extension, file.content_type)
    document_id = uuid4()
    storage_path = f"{document_id}.{extension}"
    document_title = _validate_title(title, file.filename or storage_path)
    content_type = file.content_type or DEFAULT_CONTENT_TYPE
    settings = get_settings()
    client: Any = None
    storage: StorageService | None = None
    uploaded = False
    created_at = datetime.now(timezone.utc)

    try:
        client = get_supabase()
        storage = StorageService(client)
        await asyncio.to_thread(storage.upload_file, storage_path, content, content_type)
        uploaded = True
        info("Storage uploaded", document_id=str(document_id), storage_path=storage_path)

        await asyncio.to_thread(
            _database_insert,
            client,
            {
                "id": str(document_id),
                "user_id": current_user.id,
                "title": document_title,
                "file_name": file.filename,
                "document_type": document_type.value,
                "status": "processing",
                "storage_path": storage_path,
                "created_at": created_at.isoformat(),
            },
        )
        info("Database updated", document_id=str(document_id), status="processing")

        if extension != "pdf":
            info("Upload finished", document_id=str(document_id), status="processing")
            return UploadResponse(
                document_id=document_id,
                title=document_title,
                document_type=document_type,
                status="processing",
                pages=0,
                character_count=0,
                text_preview="",
                message="OCR processing is pending for this file type.",
                storage_path=storage_path,
                created_at=created_at,
            )

        ocr_result = await asyncio.to_thread(
            OCRService().extract_text,
            content,
            extension,
            settings.MAX_PDF_PAGES,
            settings.MAX_EXTRACTED_CHARACTERS,
            settings.OCR_TIMEOUT_SECONDS,
        )
        extracted_text = ocr_result.text
        await asyncio.to_thread(
            _database_update,
            client,
            document_id,
            {
                "status": "completed",
                "pages": ocr_result.total_pages,
                "character_count": len(extracted_text),
                "extracted_text": extracted_text,
            },
        )
        info(
            "OCR completed",
            document_id=str(document_id),
            pages=ocr_result.total_pages,
            character_count=len(extracted_text),
        )
        info("Upload finished", document_id=str(document_id), status="completed")
        return UploadResponse(
            document_id=document_id,
            title=document_title,
            document_type=document_type,
            status="completed",
            pages=ocr_result.total_pages,
            character_count=len(extracted_text),
            text_preview=extracted_text[:800],
            storage_path=storage_path,
            created_at=created_at,
        )
    except StorageServiceError as exc:
        error("Upload failed during storage", document_id=str(document_id))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except DatabaseServiceError as exc:
        cause = exc.__cause__
        api_details = _log_api_error_details(cause) if cause else {}
        error(
            "Upload failed during database operation",
            document_id=str(document_id),
            title=document_title,
            storage_path=storage_path,
            error=str(exc),
            api_message=api_details.get("api_message"),
            api_code=api_details.get("api_code"),
            api_details=api_details.get("api_details"),
            api_hint=api_details.get("api_hint"),
            cause_repr=repr(cause),
        )
        if uploaded and storage is not None:
            try:
                await asyncio.to_thread(storage.delete_file, storage_path)
            except StorageServiceError as cleanup_exc:
                error("Storage cleanup failed", document_id=str(document_id), error=str(cleanup_exc))
        raise HTTPException(status_code=503, detail="Document metadata could not be saved.") from exc
    except OCRResourceLimitError as exc:
        error("Upload exceeded OCR resource limits", document_id=str(document_id), error=str(exc))
        if client is not None:
            try:
                await asyncio.to_thread(_database_update, client, document_id, {"status": "failed"})
            except DatabaseServiceError as update_exc:
                error("Failed to mark document as failed", document_id=str(document_id), error=str(update_exc))
        raise HTTPException(status_code=413, detail="The PDF exceeds processing limits.") from exc
    except OCRServiceError as exc:
        error("Upload failed during OCR", document_id=str(document_id), error=str(exc))
        if client is not None:
            try:
                await asyncio.to_thread(_database_update, client, document_id, {"status": "failed"})
            except DatabaseServiceError as update_exc:
                error("Failed to mark document as failed", document_id=str(document_id), error=str(update_exc))
        raise HTTPException(status_code=422, detail="Document text extraction failed.") from exc
    except Exception as exc:
        error("Upload failed unexpectedly", document_id=str(document_id), error=str(exc))
        if uploaded and storage is not None:
            try:
                await asyncio.to_thread(storage.delete_file, storage_path)
            except StorageServiceError:
                pass
        raise HTTPException(status_code=500, detail="Document upload failed.") from exc
