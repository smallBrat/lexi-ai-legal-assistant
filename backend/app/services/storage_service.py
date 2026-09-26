"""Supabase Storage operations for legal documents."""

from typing import Any

from supabase import Client

BUCKET_NAME = "legal-documents"


class StorageServiceError(Exception):
    """Raised when a Supabase Storage operation fails."""


class StorageService:
    """Keep Supabase Storage operations isolated from API handlers."""

    def __init__(self, client: Client) -> None:
        """Initialize the service with a Supabase client."""
        self._bucket = client.storage.from_(BUCKET_NAME)

    def upload_file(self, storage_path: str, content: bytes, content_type: str) -> str:
        """Upload document bytes and return the storage path."""
        try:
            self._bucket.upload(
                storage_path,
                content,
                {"content-type": content_type, "upsert": False},
            )
            return storage_path
        except Exception as exc:
            raise StorageServiceError("Unable to upload document to storage") from exc

    def delete_file(self, storage_path: str) -> None:
        """Delete a document from Supabase Storage."""
        try:
            self._bucket.remove([storage_path])
        except Exception as exc:
            raise StorageServiceError("Unable to delete document from storage") from exc

    def get_signed_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """Create a temporary signed URL for a stored document."""
        try:
            result: Any = self._bucket.create_signed_url(storage_path, expires_in)
            if isinstance(result, dict):
                signed_url = result.get("signedURL") or result.get("signedUrl")
            else:
                signed_url = getattr(result, "signed_url", None)
            if not signed_url:
                raise StorageServiceError("Signed URL was not returned")
            return str(signed_url)
        except Exception as exc:
            raise StorageServiceError("Unable to create signed document URL") from exc
