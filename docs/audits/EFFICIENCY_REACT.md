# Efficiency Report — React Rendering

| Area | Finding | Verdict |
|------|---------|---------|
| Unnecessary renders | `usePolling` subscribes via registry and only `setState` when status actually changes (`peekStatus === "polling"` check); terminal states stop all timers | PASS |
| Unstable callbacks | `usePolling` stores `onStatusChange` in a ref (`onStatusChangeRef`) — consumer callbacks never destabilize effect deps | PASS |
| Memoization | Poll results enter React Query via `setQueryData`, so consumers re-render through RQ's structural sharing, not manual state plumbing | PASS |
| Expensive hooks | `useDocuments` memoizes nothing heavy; list mapping (`mapDocument`) is O(n) per render of small pages | PASS |
| Dependency arrays | `terminatePolling`/`handleResult`/`stableFetchDocument` deps reviewed — all minimal and correct; `documentIdRef` guards async callbacks against stale ids | PASS |
| Context rerenders | `AuthContext` value object is recreated per render of `AuthProvider`, but the provider re-renders only on session changes (rare); children are stable | Acceptable |
| React Query cache misuse | **Correct usage**: poll owns the document GET (`setQueryData` only); `useDocument` disabled while polling with three guards; `staleTime: Infinity` + `refetchOnMount: false` for document/analysis — no refetch storms on navigation | PASS |
| Sibling state churn | `upload-dropzone` progress via `onProgress` callback — local state only | PASS |

## Notes (no action needed)

- The one intentional rerender path — polling status flips — is exactly the UI signal the user needs (progress/terminal).
- No component in the repo wraps expensive render trees that would benefit from `memo()`; page components are small and RQ-driven.

**Verdict: no inefficient patterns found; no changes required (score preserved).**
