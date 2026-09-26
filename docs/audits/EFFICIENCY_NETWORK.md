# Efficiency Report — Network

Every frontend network call inventoried from `services/*`, `hooks/use-lexi.ts`, `hooks/use-polling.ts`, `lib/api-client.ts`.

| Component / hook | Endpoint | Frequency | Duplicate? | Cached? | Retry? | Abortable? |
|------------------|----------|-----------|------------|---------|--------|------------|
| `useDocuments` | GET /documents | on mount/filter change | no (queryKey keyed by params) | React Query, default staleTime | 1 | via RQ signal |
| `useDocument` | GET /documents/:id | one-shot (guarded) | **no** — 3 independent guards (`!isPolling`, registry status, no poll data) prevent duplication with polling | `setQueryData` from poll loop; `staleTime: Infinity` | 1 | yes (timeout) |
| `usePolling` | GET /documents/:id | backoff chain 2→4→6→8s while processing | **no** — single-flight `inFlightRef` + registry `startFresh` blocks duplicate chains | pushes to RQ cache | refresh-once-on-401 | timeout per tick |
| `useAnalysis` | GET /documents/:id (+list) | on report/compare mount | no | staleTime: Infinity | 1 | yes |
| **`useAnalysis` (Phase 15)** | list prefetch | was serial second GET → **now `Promise.all` with document fetch** | deduped | yes | 1 | yes | 
| `useChat` | GET /documents/:id/chat | opt-in on chat tab | no | staleTime 30s | 1 | yes |
| `useSendChatMessage` | POST /chat | per submit | no — per-document AbortController aborts stale send | invalidates history | no | **yes** (AbortController per doc) |
| `useAnalyzeDocument` | POST /analyze/:id | once per processing page | no — module-level controller map aborts previous | setQueryData (no refetch) | no | **yes** (AbortController per doc) |
| `useUpload` | POST /upload | per submit | no | invalidates list | no | XHR (no signal; acceptable) |
| `useComparison` | POST /compare | on results mount | no | staleTime: Infinity | 1 | yes |
| `useDeleteDocument` | DELETE via POST /delete | per click | no | invalidates list | no | no |
| api-client | all | — | 401 → single-flight refresh shared by ALL callers, retry once | — | — | timeout per request (`withTimeout`) |

## Phase 15 improvement

- **`useAnalysis` parallelization**: report/compare pages previously did two serial round-trips (metadata list, then document). Now both fire in one `Promise.all` — one round-trip of latency saved per page load.

## Verdict

No duplicate polling sources (registry-enforced), no unbounded retries (max 1), all fetches timeout-bounded, long-running mutations abortable. The 422/401 paths share one refresh promise.
