# Efficiency Report — Memory / Leaks

## Frontend

| Resource | Cleanup | Verdict |
|----------|---------|---------|
| Polling timers | `pollingRegistry.stop()` clears interval+timeout; hook cleanup clears local `timeoutRef` | PASS |
| Registry subscribers | `unsubscribe()` on unmount / id change; `maybeStop` deletes empty entries | PASS |
| AbortControllers | Per-mutation maps (`activeAnalyzeControllers`, `activeChatControllers`) delete the controller in `finally`; aborted controllers never reused | PASS |
| Auth listener | `onAuthStateChange` subscription unsubscribed on unmount (try/catch guarded) | PASS |
| Event listeners | `withTimeout` uses `{ once: true }` abort listeners + clears timeout in `finally` (`combined.cancel()`) | PASS |
| XHR (upload) | One-shot per upload, GC after settle | PASS |
| React Query cache | Entries keyed per id; `staleTime: Infinity` only for document/analysis — bounded by user's own documents | PASS |
| Module-level singletons | `pollingRegistry`, supabase client — intentional singletons, constant size | PASS |

## Backend

| Resource | Cleanup | Verdict |
|----------|---------|---------|
| Supabase client | Process singleton | PASS |
| Gemini client | Thread-safe singleton, reused for aio + sync | PASS |
| ChromaDB client | Singleton `EmbeddingService` (per-request clients caused SQLite lock contention previously — fixed upstream) | PASS |
| Settings | Cached singleton | PASS |
| Threads | All `to_thread` calls are short-lived executor tasks (default executor) | PASS |
| Caches | Chroma persistent on disk, not RAM; no unbounded in-process caches | PASS |

**Leaks found: 0.**
