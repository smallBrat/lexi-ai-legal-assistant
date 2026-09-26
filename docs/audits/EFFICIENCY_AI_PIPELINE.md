# Efficiency Report — OCR / AI Pipeline

## Flow

Upload → (PDF: PyMuPDF text extraction, images: OCR ≤30s timeout) → store text → POST /analyze (cached) → Gemini schema-JSON → normalize → **batch-index clauses into ChromaDB** → chat uses pre-built index.

## Findings

| Stage | Duplicate work? | Evidence / action |
|-------|-----------------|-------------------|
| OCR | no | Runs once at upload; text persisted; never re-extracted on later requests |
| Chunking | no | Clause segmentation is a byproduct of Gemini analysis (no separate chunker) |
| Embeddings | **no duplicates** | `index_clauses` skips clause ids already in the collection; batched ≤256 per Gemini request; re-analysis reuses existing vectors |
| Analysis | **no duplicates** | `analyze_document` cache-first (`force` only via explicit retry); model fallback bounded (3 models × 2 attempts, backoff+jitter) |
| Chat retrieval | no | Query embedding is 1 call; index built at analysis time (documented "indexing happens at analysis time") |
| Fallback path | efficient | Empty vector match → analysis-derived context (no second Gemini pre-call); genuine no-context → deterministic local answer, Gemini skipped entirely |

## Memory spikes

- PDFs processed page-by-page inside PyMuPDF with hard caps (`MAX_PDF_PAGES=100`, `MAX_EXTRACTED_CHARACTERS=300k`); 20 MB upload cap.
- **Phase 15:** PDF page-count validated *before* the OCR loop → pathological PDFs rejected in milliseconds instead of being parsed (DoS-hardening *and* efficiency win).
- Embedding batches capped at 256 texts / 25k chars each — bounded request payloads.

## Synchronous bottlenecks

- All OCR/embedding/DB work runs in `asyncio.to_thread`; Gemini is native async. The event loop stays responsive under concurrent uploads.
- `time.sleep(1.0)` in embedding retry runs inside worker threads (not the loop) — acceptable.

**Verdict: no duplicate AI work exists; Phase 15 added the PDF pre-parse rejection.**
