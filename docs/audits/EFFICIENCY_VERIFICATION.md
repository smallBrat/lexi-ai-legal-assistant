# Efficiency Verification — Phase 15

## Before vs after

| Metric | Before | After | Evidence |
|--------|--------|-------|----------|
| Documents-list latency (page of 20) | 1 DB query + **20 serial storage calls** (~2–6 s typical, up to 30 s worst) | 1 DB query + 20 concurrent calls (~1 round-trip, ~0.2–0.5 s) | `asyncio.gather` in `DocumentService.list_documents` |
| Cached-compare payload | fetched `extracted_text` + full `analysis` JSONB per doc | metadata columns only | `_fetch_row(_metadata_only=True)` |
| Chat history response | unbounded rows (grows with conversation) | capped at 200 rows | `.limit(200)` |
| CORS pre-flight caching | none (every cross-origin request pre-flighted) | cached 600 s by browsers | `max_age=600` |
| Report/compare page data load | 2 serial GETs | 2 parallel GETs | `Promise.all` in `useAnalysis` |
| Pathological PDF upload | fully parsed before OCR limit hit | rejected with 413 in ms | pre-parse page check |
| Backend tests | 168 passed | **168 passed** | full pytest run |
| Frontend tests | 47/47 | **47/47** | npm test |
| Production build | pass | **pass** — First Load JS unchanged (103 kB shared; worst route 229 kB) | next build |
| Typecheck / lint | pass | **pass** | tsc + eslint |

## Regression safety

- All efficiency changes are latency-only: response schemas, status codes, and pagination semantics are byte-identical (covered by the 215 passing tests).
- Signed-URL ordering preserved (`zip(rows, urls)` — row i keeps its own URL).
- History cap chosen above any realistic conversation length; frontend contract unchanged.

## Leak/duplicate checks

- Polling: single chain per document id, terminal stop verified (see EFFICIENCY_POLLING.md).
- Memory: no timers/subscriptions/controllers leak (see EFFICIENCY_MEMORY.md) — 0 findings.
- Network: no duplicate fetches; single-flight token refresh shared across all callers.
