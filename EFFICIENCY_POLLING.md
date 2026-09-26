# Efficiency Report — Polling

Audited `hooks/use-polling.ts` + `lib/polling-registry.ts` (Phase 14 architecture).

## Requirements checklist

| Requirement | Evidence | Verdict |
|-------------|----------|---------|
| Exactly one polling source | Registry singleton keyed by document id; `startFresh` blocks a second chain (`POLL_DUPLICATE_BLOCKED`); React Query is *not* a second source (disabled + `setQueryData` only) | PASS |
| Timer cleanup | `stop()` clears interval + timeout and deletes the entry; hook cleanup clears local timeout + unsubscribes; unmount sets `mountedRef = false` | PASS |
| AbortController | Each tick bounded by `pollingFetch` timeout (60s) via `withTimeout` combined signal; `inFlightRef` prevents overlap instead of aborting (simpler + equivalent) | PASS |
| Retry backoff | `BACKOFF_INTERVALS = [2s, 4s, 6s, 6s, 8s]`, reset to 0 on success | PASS |
| Stop conditions | Terminal statuses: `ready+analysis`, `analysis_completed`, `failed`, `analysis_failed`; also auth failure and last-unsubscribe | PASS |
| Duplicate chain prevention | Synchronous hard stop (`terminatePolling`): mounted flag → registry status → registry stop → unsubscribe → clear timeout → return; `scheduleNext` re-checks `peekStatus` before arming | PASS |
| 401 handling | Proactive refresh (60s horizon) before every tick via `pollingFetch`; reactive 401 joins the single-flight refresh, retries exactly once, then terminates on failure — no 401 loops | PASS |
| Memory | Deleted registry entries cannot resurrect (`peekStatus` of deleted id = "idle"); `stopAll` available | PASS |

## Interval budget

- Fresh document: ticks at 2–8s — bounded by backoff, stops at terminal state. No fixed interval longer than 8s; no runaway polling after completion (verified: `terminatePolling` on first terminal result).

**Verdict: polling architecture is sound; no changes required.**
