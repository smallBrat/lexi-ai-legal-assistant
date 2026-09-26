# Efficiency Report — Backend API

## N+1 / duplicate query audit

| Location | Finding | Action |
|----------|---------|--------|
| `DocumentService.list_documents` | Signed-URL generation ran **serially per row** — N storage round-trips per page (N = page_size ≤ 100), ~100–300 ms each → up to 30 s worst case | **FIXED (Phase 15): all signed URLs fetched concurrently via `asyncio.gather` — one round-trip of latency regardless of page size** |
| `POST /compare` cached path | `_fetch_row` pulled `extracted_text` + `analysis` (large columns) only to render titles/types | **FIXED (Phase 15): `_metadata_only=True` skips heavy columns** |
| `AnalysisService.analyze_document` | Cached analysis returns immediately without Gemini (validated cache read) | PASS — dedup built in |
| `EmbeddingService.index_clauses` | Batch embedding (≤256/req) with per-item fallback; existing ids skipped on re-analysis | PASS — no duplicate embedding calls |
| `ChatService.answer` | One document fetch + one vector search + one Gemini call per question; history write is one insert | PASS — no duplicates |
| `GET /chat/{id}` | Unbounded history fetch grew with conversation length | **FIXED (Phase 15): `limit(200)`** |

## Blocking IO

- Every Supabase/storage/OCR call is wrapped in `asyncio.to_thread` — event loop never blocked.
- `verify_token` (network call to Supabase Auth) is also `to_thread`-wrapped.

## Serialization

- `LegalAnalysis` validated/normalized once and persisted; subsequent reads hit the stored JSON (cache-first `analyze`).
- Signed URLs are minted per list request (required — they expire); with the Phase 15 change they no longer serialize the response.

## Repeated Gemini calls

- Analyze: cached unless `force=true`; correction retry only on invalid JSON (max 1).
- Chat/compare: model fallback capped at 3 models × 2 attempts with backoff — worst case bounded.

**Net effect of Phase 15: up to ~N× latency removed from every documents-list request and large-column reads removed from cached comparisons.**
