# Security Report — File Uploads

Pipeline: `POST /upload` → size cap → extension allowlist → MIME check → magic-byte check → integrity parse → UUID storage path → Supabase Storage → OCR.

| Control | Implementation | Verdict |
|---------|----------------|---------|
| Extension validation | `{pdf, png, jpg, jpeg, docx}` allowlist (`ALLOWED_EXTENSIONS`) | PASS |
| MIME validation | Exact match against `MIME_TYPES[extension]`; mismatch → 415 | PASS |
| Size limit | 20 MB, enforced during read (`read(MAX+1)`) — connection aborted early, no full buffering | PASS |
| Magic bytes | `%PDF-` / PNG `\x89PNG…` / JPEG `\xff\xd8\xff` / DOCX zip with `[Content_Types].xml` + `word/document.xml` | PASS |
| Full-parse validation | PDF opened via PyMuPDF, images `Image.verify()`, DOCX zip structure checked — before any storage/OCR | PASS |
| Path traversal | Storage path = `f"{uuid4()}.{extension}"` — **no client filename ever used in a path**; original filename stored as metadata only | PASS |
| Filename sanitization | Title sanitized (ANSI escapes + control chars stripped, 200-char clamp) — **Phase 15** | FIXED |
| Duplicate uploads | `upsert: False` in storage upload; each upload gets a fresh UUID | PASS |
| PDF parser safety | PyMuPDF with page cap + character cap + OCR timeout (`MAX_PDF_PAGES=100`, `MAX_EXTRACTED_CHARACTERS=300k`, `OCR_TIMEOUT_SECONDS=30`) | PASS |
| **PDF page-bomb pre-check** | Page count validated **before** parse loop (`_validate_content` now rejects `page_count > MAX_PDF_PAGES` with 413 instead of discovering it during OCR) | FIXED (Phase 15) |
| DOCX safety | Zip integrity + required entries | PASS |
| **Zip bomb guard** | New: rejects >2,000 entries or >200 MB uncompressed from a 20 MB upload (≈10× inflation threshold) — **Phase 15** | FIXED |
| Image decompression bombs | Pillow `verify()` + 20 MB cap + pixel-limit is inherent to Pillow defaults; OCR pipeline caps pages/characters | PASS |
| SVG | Not in allowlist — SVG upload impossible → no stored-XSS vector via images | PASS |
| Failure cleanup | Storage row deleted if DB insert fails; status marked `failed` on OCR errors (no orphaned files) | PASS |
| Logging | Filenames/titles logged; **no document text logged** | PASS |

## Residual (accepted) risks

- `Image.verify()` does not decompress fully; a crafted image passing verify could still cost memory during OCR — bounded by the 20 MB cap and OCR timeout.
- Pillow decompression-bomb `MAX_IMAGE_PIXELS` guard is active by default (~178 MP) and raises on exceed.

**Risk: LOW after Phase 15.**
