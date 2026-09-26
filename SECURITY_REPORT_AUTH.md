# Security Report — Authentication

## Frontend

| Area | Finding | Verdict |
|------|---------|---------|
| Token storage | Supabase JS persists session in `localStorage` via browser client (`lib/supabase.ts`); no custom token handling, no token in URLs | PASS (acceptable for anon-key architecture) |
| Session refresh | Single-flight proactive refresh (60s horizon) in `lib/api-client.ts` `getValidAccessToken`; reactive 401 path shares the same in-flight promise | PASS — no refresh stampede |
| Auth persistence | `persistSession: true`, `autoRefreshToken: true` | PASS |
| Logout cleanup | `signOut` via Supabase clears server + local session; React Query caches are per-session data only | PASS |
| Route guards | `dashboard-shell.tsx` gates on `useAuth()`; unauthenticated users redirected | PASS |
| Middleware | No Next middleware; API routes proxy health only | PASS (no cookie-based session to protect) |
| LocalStorage contents | Session only (access+refresh JWTs) — standard Supabase flow, no PII beyond user id/email | PASS |

## Backend

| Area | Finding | Verdict |
|------|---------|---------|
| JWT validation | `get_current_user` → Supabase Auth API `get_user(token)` — signature + expiry verified server-side | PASS |
| Expiration | Handled by Supabase Auth (expired tokens fail verification → 401) | PASS |
| Issuer/audience | Verified implicitly by Supabase Auth against the project; local HS256 path documented as optional | PASS |
| Clock skew | Managed by Supabase Auth server-side | PASS |
| Unauthorized responses | 401 with `WWW-Authenticate: Bearer` on missing/invalid token | PASS |
| Client-supplied userId trust | **No endpoint accepts `user_id` from the client.** Identity always derives from the bearer token via `get_current_user` | PASS |
| **Phase 15 hardening** | `verify_token` now decodes the payload first and **rejects `role=service_role` credentials** before calling Supabase — a leaked service key can no longer authenticate API calls even if misconfigured into a frontend | FIXED |
| Token in logs | Authorization header redacted (`Bearer <redacted>`) in the validation-error handler; request bodies no longer logged (Phase 15) | PASS |

## Notes

- `get_token_payload` (decode-without-verification) exists but is used **only inside `verify_token` as a pre-check** — never for authorization decisions.
- Threads: token verification runs via `asyncio.to_thread` — no event-loop blocking.

**Risk: LOW after Phase 15.**
