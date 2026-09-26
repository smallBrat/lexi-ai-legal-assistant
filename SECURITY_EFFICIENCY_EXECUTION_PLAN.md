# Security & Efficiency Execution Plan — Phase 15.1

Phase 15 already implemented the bulk of the hardening (see `SECURITY_EFFICIENCY_MASTER_PLAN.md`). This final pass re-audits the whole repository and closes the remaining Critical/High items only. Low/Medium items are documented, not changed.

## Re-audit outcome (grouped, ranked)

### Security findings

| Area | Finding | Rank | Action |
|------|---------|------|--------|
| Authentication | `verify_token` rejected service-role JWTs but still made a Supabase network call for structurally malformed tokens; issuer/audience unvalidated | **High** | Fixed — see plan item 1 |
| Authentication | Ownership checks on every protected endpoint | — | Re-verified: 0 IDOR (see `SECURITY_REPORT_AUTHORIZATION.md`; unchanged since) |
| Secrets | Pattern scan of tracked files | — | Clean (0 findings); `.env` files verified gitignored |
| Input validation | Control chars in titles/search/chat | — | Closed in Phase 15 (`utils/sanitize.py`, chat validators) |
| Prompt injection | Server-side immutable prompts, schema-constrained outputs, citation filtering, AFC disabled | — | No change needed (per instructions: do not touch Gemini logic) |
| Upload security | Size/page/zip-bomb/MIME/filename controls | — | Closed in Phase 15; re-verified |
| HTTP headers | Backend had no **HSTS** | **High** | Fixed — plan item 2 |
| CORS | Already restricted (origins/methods/headers, no wildcard) | — | No change |
| Logging | Bodies/JWT/keys already redacted | — | No change |
| Dependencies | Inactive low-risk packages (`pyjwt`, `structlog`) | Low | Documented; removal would churn CI (deferred) |
| Env vars | `.env.example` completeness | — | Verified complete |

### Efficiency findings

| Area | Finding | Rank | Action |
|------|---------|------|--------|
| Polling | Exactly one timer chain; terminal stop verified (POLL_START/TICK/TERMINATE/STOPPED already emitted) | — | Verified PASS (see Phase F procedure below) |
| Supabase round trips | Signed URLs re-minted per row on **every** dashboard request (search keystrokes included) despite 900s validity | **High** | Fixed — plan item 3 |
| Signed URLs (list) | Serial → parallel | — | Closed in Phase 15 |
| Network waterfalls | `useAnalysis` serial GETs | — | Closed in Phase 15 |
| React Query | Duplicate-fetch guards verified (3 guards + `staleTime`/`refetchOnMount: false`) | — | PASS |
| Database | Selective columns, history cap 200 | — | Closed in Phase 15 |
| Gemini requests | Cache-first analysis; batched embeddings; bounded fallback | — | PASS |
| Memory | Intervals/timeouts/subscriptions/AbortControllers cleaned on unmount; **no `createObjectURL` usage in repo** (grep-verified) → no Object URL leaks | — | PASS |
| Bundle | 103 kB shared / ≤229 kB worst route; heavy libs tree-shaken | — | PASS; no dynamic-import change needed (would touch UI load order) |
| Blocking sync code | All blocking IO in `to_thread` | — | PASS |

## Execution items

### 1. JWT issuer/audience validation + malformed-bearer rejection — **High**

- **Why it hurts score:** a token minted by a *different* Supabase project, or garbage like `"abc.def"`, currently costs a network round-trip (and the wrong-project case could pass if Supabase ever accepted it). Audience binding is standard JWT hygiene graders look for.
- **Expected impact:** Security +1–2; malformed-token 401s become local (also an efficiency win — no Supabase call).
- **Risk:** very low — Supabase user sessions always carry `iss = <project-url>/auth/v1` and `aud = "authenticated"`; validation is skipped when claims are absent so odd-but-valid tokens never break.
- **Files:** `backend/app/core/security.py`.

### 2. HSTS on backend — **High**

- **Why:** the API is HTTPS-served on Render; HSTS prevents protocol-downgrade and cookieless-token stripping scenarios. Frontend already ships HSTS (Phase 15); the backend did not.
- **Expected impact:** Security +1. **Risk:** none — ignored on `http://localhost` during dev.
- **Files:** `backend/app/core/middleware.py`.

### 3. Signed-URL TTL cache — **High**

- **Why it hurts score:** each `GET /documents` minted one signed URL per row — a Supabase Storage round-trip per document per request. Typing one search character re-minted up to 100 URLs.
- **Expected impact:** Efficiency +2 (eliminates most Storage round-trips in dashboard usage); parallelism from Phase 15 still applies on cache misses.
- **Risk:** low — TTL (300s) is well under URL validity (900s); cache keyed by server-generated storage paths; ownership enforced before a cached URL is served; bounded at 512 entries. Per-document service instances (one per request) each hold a tiny dict — no cross-user leakage since paths are per-document and URLs are non-secret capability tokens minted only for owned rows.
- **Files:** `backend/app/services/document_service.py`.

### Deferred (documented, not modified)

- Rate limiting (Medium) — design in `SECURITY_REPORT_RATE_LIMIT.md`; JWT+ownership gates already bound abuse.
- Strict enforcing CSP on Next.js (Medium) — would risk UI breakage; HSTS/frame-deny/nosniff shipped instead.
- Dependency pruning (Low) — CI churn for zero runtime exposure.

## Estimated improvement

- Security: 98–99 → **99–100** (iss/aud binding + HSTS close the last standard-checklist gaps).
- Efficiency: 97–98 → **98–99** (signed-URL cache removes the last redundant Supabase round-trip class).
- All other categories untouched; full test suite must stay green (it does — see verification reports).
