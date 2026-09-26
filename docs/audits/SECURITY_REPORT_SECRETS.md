# Security Report — Secrets

**Scope:** full repository scan (tracked files, `.env` files, `frontend/.secrets/`, `opencode.json`, CI workflow, Render blueprint).
**Method:** pattern scan (JWT literals, `AIza…`, `sk-…`, `ghp_`, `xox[bp]-`, PEM blocks) + git-tracked file review.

## Findings

| # | Finding | Location | Risk | Status |
|---|---------|----------|------|--------|
| 1 | Real Gemini API key + Supabase anon/service keys present in **untracked** `backend/.env` and `frontend/.env.local` | local only | HIGH | Verified gitignored (`git check-ignore` confirms). **Operator action required: rotate the Gemini key if this machine is shared.** |
| 2 | `frontend/opencode.json` and `frontend/.secrets/` exist locally | frontend/ | MEDIUM | Both are gitignored (`frontend/.gitignore`, root `.gitignore` `.secrets/`). Not tracked. |
| 3 | No `NEXT_PUBLIC_` variable carries a private value | `frontend/.env.example`, `render.yaml` | — | PASS — only URL + anon key (protected by RLS). |
| 4 | No secrets in client bundle | `lib/supabase.ts` reads only `NEXT_PUBLIC_*` | — | PASS. |
| 5 | `.env.example` files are complete and match code | root, backend, frontend | — | PASS — every var read by `config.py`/`api-client.ts` is documented, including optional `SUPABASE_JWT_SECRET`. |
| 6 | `render.yaml` declares secrets as `sync: false` | render.yaml | — | PASS — no secret values committed. |
| 7 | CI uses placeholder env values only | `.github/workflows/ci.yml` | — | PASS. |
| 8 | JWT-shaped anon/service keys committed in reports? | scanned `reports/`, `docs/` | — | No hits. |

## Environment-variable correctness

- Backend `Settings` requires `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` — all four documented in `backend/.env.example` and declared in `render.yaml`.
- Frontend requires `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL` — documented and declared.

## Residual risk

The service-role key bypasses RLS. It is only read by `backend/app/core/supabase.py` (server-only) and Phase 15 additionally **rejects a service-role credential presented as a bearer token** (`core/security.py`), closing client-misconfiguration abuse.

**Overall risk: LOW (posture) / HIGH (operator action: keep keys rotated, never commit `.env`).**
