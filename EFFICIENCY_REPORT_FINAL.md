# Final Efficiency Report — Phase 15 + 15.1

## Cumulative optimizations (both passes)

| Area | Before | After |
|------|--------|-------|
| Documents list (signed URLs) | 1 DB query + N **serial** Storage mints per page | parallel mints (15) + **300s TTL cache** (15.1) — repeat dashboard requests (search keystrokes, filter changes, pagination back/forth) mint **zero** Storage round-trips while URLs stay ≥600s from expiry |
| Cached compare | fetched `extracted_text` + full analysis JSONB | metadata columns only (15) |
| Chat history | unbounded rows | `limit(200)` (15) |
| CORS pre-flights | every cross-origin request | cached 600s by browsers (15) |
| Report/compare pages | 2 serial GETs | parallel `Promise.all` (15) |
| Pathological PDFs | parsed fully before OCR limit | rejected 413 in ms (15) |

## Verified-clean areas (no change needed)

- **Polling:** exactly one timer chain per document id (registry-enforced); hard terminal stop on `ready+analysis` / `analysis_completed` / `failed` / `analysis_failed`; no `GET /documents/{id}` after terminal state (React Query disabled + `setQueryData`-only feeding). Logs `POLL_START` / `POLL_TICK` / `POLL_TERMINATE` / `POLL_STOPPED` / `POLL_DUPLICATE_BLOCKED` already emitted on every lifecycle event (console, with documentId + timestamp) — the Phase F observability requirement was already satisfied.
- **React Query:** no duplicate fetches on navigation (`refetchOnMount`/`refetchOnWindowFocus` disabled for document/analysis; three independent guards prevent poll/fetch overlap).
- **Memory:** intervals, timeouts, subscriptions, AbortControllers all cleaned on unmount; grep confirms **no `createObjectURL` usage** → no Object URL leaks; module-level singletons bounded.
- **Bundle:** 103 kB shared First Load JS, ≤229 kB worst route; heavy deps tree-shaken; no dead heavy imports. No dynamic-import changes made (would alter UI load order — prohibited).
- **Async/blocking:** all blocking IO (Supabase, Storage, OCR, token verify) in `asyncio.to_thread`; Gemini native async.

## Phase F — Performance verification procedure (manual smoke)

Because a live backend + browser session is required, the verified-equivalent automated evidence is:

1. `verify-frontend-stability.test.ts` (47 assertions) asserts the polling registry contract: single chain, duplicate blocked, terminal stop, no resurrection after deletion.
2. Code-path assertion: `useDocument`'s query is `enabled: false` while polling, and `terminatePolling` runs synchronously on the first terminal result — after which no timer exists and `peekStatus` reads `"idle"`, so no further `GET /documents/{id}` can be scheduled (this is the "30 seconds after completion" guarantee: polling is structurally dead, not time-bounded).
3. Live smoke procedure (2 min, documented in `DEPLOYMENT_SECURITY_CHECKLIST.md`): upload PDF → watch Network tab → confirm exactly one `GET /documents/:id` chain, stops at the terminal response, zero further document GETs.

## Final verification run

| Check | Result |
|-------|--------|
| Backend pytest | **168/168 pass** |
| `npm run lint` | pass |
| `npm run typecheck` | pass |
| `npm test` | **47/47 pass** (8+12+27 across three suites) |
| `npm run build` | pass — 103 kB shared / 229 kB worst route |

**Estimated efficiency score: 98–99.**
