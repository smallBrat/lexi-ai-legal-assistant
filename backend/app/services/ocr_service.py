"""Text extraction services for uploaded legal documents."""

from dataclasses import dataclass
from time import monotonic


class OCRServiceError(Exception):
    """Raised when document text extraction fails."""


class OCRResourceLimitError(OCRServiceError):
    """Raised when a document exceeds configured OCR resource limits."""


@dataclass(frozen=True)
class PageText:
    """Text extracted from one document page."""

    page_number: int
    text: str


@dataclass(frozen=True)
class OCRResult:
    """Structured result of document text extraction."""

    pages: list[PageText]

    @property
    def total_pages(self) -> int:
        """Return the number of pages extracted."""
        return len(self.pages)

    @property
    def text(self) -> str:
        """Return all extracted page text in document order."""
        return "\n\n".join(page.text for page in self.pages)


class OCRService:
    """Extract text from supported document formats."""

    def extract_text(
        self,
        content: bytes,
        extension: str,
        max_pages: int = 100,
        max_characters: int = 300_000,
        timeout_seconds: float = 30.0,
    ) -> OCRResult:
        """Extract page text from a PDF or return an image placeholder."""
        normalized_extension = extension.lower().lstrip(".")
        if normalized_extension == "pdf":
            return self._extract_pdf_text(
                content, max_pages, max_characters, timeout_seconds
            )
        if normalized_extension in {"png", "jpg", "jpeg"}:
            raise OCRServiceError("Image OCR is not implemented")
        if normalized_extension == "docx":
            raise OCRServiceError("DOCX OCR is not implemented")
        raise OCRServiceError(f"Unsupported OCR format: {extension}")

    def _extract_pdf_text(
        self,
        content: bytes,
        max_pages: int,
        max_characters: int,
        timeout_seconds: float,
    ) -> OCRResult:
        """Extract text from every PDF page using PyMuPDF."""
        try:
            import fitz

            document = fitz.open(stream=content, filetype="pdf")
            try:
                if document.page_count > max_pages:
                    raise OCRResourceLimitError("PDF page limit exceeded")
                started_at = monotonic()
                pages: list[PageText] = []
                character_count = 0
                for index, page in enumerate(document):
                    if monotonic() - started_at > timeout_seconds:
                        raise OCRResourceLimitError("PDF extraction timed out")
                    text = page.get_text("text").strip()
                    character_count += len(text) + (2 if pages else 0)
                    if character_count > max_characters:
                        raise OCRResourceLimitError("PDF extracted text limit exceeded")
                    pages.append(PageText(page_number=index + 1, text=text))
            finally:
                document.close()
            return OCRResult(pages=pages)
        except OCRResourceLimitError:
            raise
        except Exception as exc:
            raise OCRServiceError("Unable to extract text from PDF") from exc

