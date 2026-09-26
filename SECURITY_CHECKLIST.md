# 🔐 Security Checklist — Lexi AI

**Audit date:** 2026-09-25 · **Scope:** Phase 2 git audit before first public commit

---

## 1. .gitignore verification

Verified with `git check-ignore -v` (proves the rules actually match, not just that the lines exist):

| Path | Ignored by | Status |
|---|---|:---:|
| `frontend/.env.local` | `frontend/.gitignore` → `*.local` | ✅ |
| `backend/.env` | `.gitignore` → `**/.env` | ✅ |
| `frontend/.secrets/` | `.gitignore` → `.secrets/` | ✅ |
| `backend/.venv/` | `.gitignore` → `.venv/` | ✅ |
| `frontend/.next/` | `frontend/.gitignore` → `.next/` | ✅ |
| `frontend/node_modules/` | `frontend/.gitignore` → `node_modules/` | ✅ |
| `backend/.chroma/` | `.gitignore` → `backend/.chroma/` | ✅ |

Also covered by root `.gitignore`: `__pycache__/`, `*.py[cod]`, `logs/`, `*.log` (incl. `runtime-exit.log`, `lifecycle.log`, `frontend-*.log`), `coverage/`, `uploads/`, `chroma.sqlite3`, `*.env*` (with `!.env.example`), `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `tmp-*`, `debug-*`, `*.bak`, `.DS_Store`. Frontend has its own `.gitignore` (standard Next.js set).

## 2. Environment templates

All three exist with placeholder-only values (`your-…-here`, no real subdomains or keys):

- ✅ `.env.example` (root, shared reference)
- ✅ `backend/.env.example`
- ✅ `frontend/.env.example` — documents that only `NEXT_PUBLIC_*` vars reach the browser; explicitly warns against service-role keys client-side.

## 3. Secret scan (full repo, excluding `node_modules`)

| Pattern searched | Matches |
|---|---|
| Google key format (`AIza…`) | 0 real keys (only docs mentions of the *name* `GEMINI_API_KEY`) |
| Anthropic/OpenAI key formats (`sk-ant`, `sk-proj`, `sk-` + 20 chars) | 0 |
| GitHub tokens (`ghp_`), Slack tokens (`xoxb-`) | 0 |
| JWT-shaped strings (`eyJ…`) | 0 |
| `service_role` / `SUPABASE_SERVICE_ROLE` / `JWT_SECRET` | Variable names and documentation only — no values |
| Private key blocks (`-----BEGIN`) | 0 |
| Real Supabase project subdomains | 0 (previously removed from templates) |

Secrets in code are loaded via Pydantic `BaseSettings` with `SecretStr` (`backend/app/core/config.py`) — never hardcoded, never logged. `render.yaml` declares only variable names with `sync: false` (values set in the Render dashboard).

**No secret replacement was required — no real secrets exist in the working tree.**

## 4. Hardcoded localhost URLs

| Location | Value | Verdict |
|---|---|:---:|
| `frontend/lib/api-client.ts`, `frontend/app/api/health/route.ts` | `http://localhost:8000` as env **fallback** | ✅ dev default; `NEXT_PUBLIC_API_URL` overrides in production |
| `frontend/lib/supabase.ts` | `http://localhost:54321` fallback | ✅ dev default; overridden by `NEXT_PUBLIC_SUPABASE_URL` |
| `backend/app/main.py` (CORS) | `localhost:3000` origins | ✅ **fixed this phase** — see below |
| Test fixtures (`frontend/scripts/*.test.ts`, backend tests) | `localhost:8000`, mock URLs | ✅ intentional |

**Fixed in this phase:** the backend CORS allowlist previously ignored the documented `FRONTEND_URL` variable. `backend/app/main.py` now appends `settings.FRONTEND_URL` to the dev origins, and `FRONTEND_URL` was added to `backend/app/core/config.py`. Production deployments must set `FRONTEND_URL` to the frontend origin. (`compileall` passes; behavior in dev is unchanged.)

## 5. Runtime security controls (verified in code)

- ✅ JWT verification on every protected route via Supabase Auth (`get_current_user`), 401 + `WWW-Authenticate` on failure
- ✅ Row-level ownership — queries filtered by authenticated `user_id`; cross-user access returns 404
- ✅ Private storage bucket, short-lived owner-scoped signed URLs for downloads
- ✅ Strict Pydantic schemas; Gemini output schema-validated before touching API contracts
- ✅ Server-side upload limits (`MAX_PDF_PAGES`, `MAX_EXTRACTED_CHARACTERS`, `OCR_TIMEOUT_SECONDS`)
- ✅ CORS allowlist (no wildcard with credentials)

## 6. Pre-push checklist (deployment side — cannot be verified from the repo)

- [ ] Set `ENVIRONMENT=production`, `DEBUG=false`, `FRONTEND_URL=https://<your-frontend>` on the Render backend service
- [ ] Set real values for `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` in the Render dashboard (never in `render.yaml`)
- [ ] Rotate `GEMINI_API_KEY` / Supabase keys if they were ever pasted into chat tools or old local history
- [ ] Run `gitleaks detect --source .` after the first commit as a belt-and-braces history scan
- [ ] Enable GitHub secret scanning + push protection (Settings → Code security)
- [ ] Enable Supabase email confirmation on sign-up
- [ ] Consider rate limiting (`slowapi`) on `/upload` and `/chat` before launch
- [ ] Add `pip-audit` + `npm audit` to CI (`.github/workflows/ci.yml` exists — extend it)

---

**Verdict:** repository content is clean — no secrets in the tree, sensitive paths verified ignored, env templates complete. One code fix (CORS `FRONTEND_URL` support) applied this phase.
