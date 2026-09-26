# Deployment Security Checklist — Phase 15

## Vercel / frontend hosting

| Check | Status | Detail |
|-------|--------|--------|
| `NEXT_PUBLIC_SUPABASE_URL` | set via dashboard | public-safe |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | set via dashboard | public-safe (RLS-protected) |
| `NEXT_PUBLIC_API_URL` | set to Render backend URL, **no trailing slash** | client strips trailing `/` defensively |
| No private vars in `NEXT_PUBLIC_*` | PASS | only the three above are read |
| Security headers | PASS | emitted by `next.config.mjs` (verify with `curl -I https://<app>` → expect HSTS, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy) |
| Debug flags | PASS | no `console.debug` paths; polling logs are `console.info` with ids only (no document text) |
| Build envs in CI | PASS | placeholders only |

## Render / backend hosting

| Check | Status | Detail |
|-------|--------|--------|
| `GEMINI_API_KEY` | dashboard secret (`sync: false`) | rotate if ever exposed locally |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` | dashboard secrets | service key bypasses RLS — backend only |
| `ENVIRONMENT=production`, `DEBUG=false` | set in render.yaml | disables file logging + FastAPI debug |
| `FRONTEND_URL` | set to production frontend origin | CORS allowlist only allows localhost + this origin |
| `CHROMA_DB_PATH=/tmp/chroma` | set in render.yaml | ephemeral disk; graceful empty-index fallback exists |
| Health endpoint | `/health` — constant JSON, no external calls | Render health check safe |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | correct |
| Security headers | PASS | middleware on every response (verify with `curl -I https://<backend>/health`) |
| CORS | localhost dev origins + `FRONTEND_URL` only; methods/headers restricted | PASS |
| Cold start | Chroma empty → chat falls back to analysis context; index rebuilds on next analysis | documented behavior |

## Supabase

| Check | Status |
|-------|--------|
| RLS enabled on `documents`, `chat_history`, `comparisons`, `clauses` | verify in dashboard (backend uses service key + explicit `user_id` filters; RLS is the second layer) |
| Storage bucket `legal-documents` private (no public reads) | verify; signed URLs expire in 900 s |
| Migrations applied (`comparisons` table) | compare degrades gracefully to uncached if missing |
| JWT expiry | Supabase default (1 h) — frontend refreshes 60 s early |

## Localhost leftovers / production URLs

- `grep` audit: `localhost` appears only in dev defaults (`.env.example`, CORS dev origins, CI placeholders) — correct.
- No hardcoded production URLs anywhere in code (all via env).

## Recommended post-deploy smoke test

1. `curl -I` backend `/health` → 200 + security headers.
2. Upload a PDF → dashboard shows analysis → ask a chat question → citation appears.
3. Compare two analyzed documents → cached second run.
4. Confirm browser dev-tools Network tab shows exactly one polling chain per document.
