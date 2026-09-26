# 🚀 Deployment Guide — Render Free Tier

Deploy Lexi AI (monorepo: `frontend/` + `backend/`) to Render as two Web Services. Supabase and Gemini stay external.

## Prerequisites

- Code pushed to a GitHub repo (public or private — Render connects with OAuth)
- A Supabase project with schema applied and a **private** storage bucket
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

## Runtime audit (pre-deploy)

| Check | Status | Notes |
|---|:---:|---|
| `frontend/package.json` scripts (`build`, `start`) | ✅ | `next build` + `next start` |
| `backend/requirements.txt` complete | ✅ | fastapi, uvicorn[standard], supabase, google-genai, chromadb, PyMuPDF, Pillow |
| `runtime.txt` / `.python-version` | not needed | Set Python 3.12 via Render env or `PYTHON_VERSION` var |
| `Procfile` | not needed | Start command is set in `render.yaml` / dashboard |
| Uvicorn `$PORT` + `0.0.0.0` binding | ✅ | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Node version | ✅ | Render default Node 20; Next.js 15 requires ≥ 18.18 |
| Python version | ✅ | 3.12 |
| ChromaDB path | ⚠️ | Set `CHROMA_DB_PATH=/tmp/chroma` (free tier disk is ephemeral) |

## Option A — Blueprint (recommended)

1. Push this repo to GitHub (`render.yaml` is at the root)
2. Render Dashboard → **New → Blueprint** → select the repo
3. Render reads `render.yaml` and creates both services
4. When prompted, fill in every `sync: false` variable (see [RENDER_ENVIRONMENT_VARIABLES.md](./RENDER_ENVIRONMENT_VARIABLES.md))
5. Apply — both services build and deploy

## Option B — Manual setup

### 1. Backend (FastAPI)

Dashboard → **New → Web Service** → connect repo:

| Setting | Value |
|---|---|
| Name | `lexi-ai-backend` |
| Runtime | Python 3 |
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/health` |
| Instance Type | Free |
| Auto-Deploy | Yes |

Add env vars (see [RENDER_ENVIRONMENT_VARIABLES.md](./RENDER_ENVIRONMENT_VARIABLES.md)) → **Create Web Service**.

> ⚠️ `PYTHON_VERSION=3.12.6` — add this env var to pin the runtime.

### 2. Frontend (Next.js)

Dashboard → **New → Web Service** → same repo:

| Setting | Value |
|---|---|
| Name | `lexi-ai-frontend` |
| Runtime | Node |
| Root Directory | `frontend` |
| Build Command | `npm install && npm run build` |
| Start Command | `npm start` |
| Health Check Path | `/api/health` |
| Instance Type | Free |
| Auto-Deploy | Yes |

Add env vars (below) → **Create Web Service**.

> `NEXT_PUBLIC_*` variables are **baked into the browser bundle at build time**. If you change one, trigger a manual **Clear build cache & deploy** — a normal restart is not enough.

## Deploy order

1. **Backend first.** Wait for `https://lexi-ai-backend.onrender.com/health` → `200`.
2. **Frontend second**, with `NEXT_PUBLIC_API_URL` pointing at the backend URL.
3. Set the backend's `FRONTEND_URL` to the frontend URL, then manually redeploy the backend (CORS).

## Post-deploy configuration

- **CORS**: the backend's middleware allows `localhost:3000` by default. On Render, set `FRONTEND_URL` to the production frontend origin.
- **Supabase Auth URL config**: Supabase Dashboard → Authentication → URL Configuration → set **Site URL** to the frontend URL and add it to **Redirect URLs**. Without this, sign-in confirmations redirect to localhost.
- **Sleep behavior**: free-tier services sleep after ~15 min of inactivity. First request after sleep takes ~30–60 s (cold start). Mitigate with an uptime pinger (e.g. cron-job.org hitting `/health` every 10 min) — or accept the cold start.
- **Ephemeral disk**: ChromaDB under `/tmp` is wiped on restart/redeploy. The backend re-indexes clauses from Supabase on demand; documents themselves are safe in Supabase Storage/Postgres.

## Rollback

Render keeps previous deploys: service → **Events** → pick a deploy → **Rollback**.
