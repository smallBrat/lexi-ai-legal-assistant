# 🔑 Render Environment Variables

Complete reference for both services. Secrets go in the Render Dashboard (or Blueprint `sync: false` fields) — **never in `render.yaml` or git**.

## Backend — `lexi-ai-backend`

### Required

| Variable | Example / Source | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | Google AI Studio key | Clause extraction, risk analysis, comparison, chat, embeddings |
| `SUPABASE_URL` | `https://xxxx.supabase.co` | Server Supabase clients |
| `SUPABASE_ANON_KEY` | Supabase → Settings → API | User-scoped server operations |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Settings → API | Bypasses RLS — **backend only, never expose** |

### Required (recommended values)

| Variable | Value | Purpose |
|---|---|---|
| `ENVIRONMENT` | `production` | Disables debug verbosity |
| `DEBUG` | `false` | No verbose debug output |
| `PYTHON_VERSION` | `3.12.6` | Pins the Python runtime |
| `CHROMA_DB_PATH` | `/tmp/chroma` | Vector store inside backend filesystem (ephemeral on free tier) |

### Optional

| Variable | Value | Purpose |
|---|---|---|
| `FRONTEND_URL` | `https://lexi-ai-frontend.onrender.com` | Extra CORS origin for the deployed frontend (localhost origins are always allowed) |
| `SUPABASE_JWT_SECRET` | Supabase → Settings → API → JWT | Only if switching to local HS256 JWT verification |
| `MAX_PDF_PAGES` | `100` | Upload page limit |
| `MAX_EXTRACTED_CHARACTERS` | `300000` | Extraction cap |
| `OCR_TIMEOUT_SECONDS` | `30.0` | OCR timeout |
| `EMBEDDING_OUTPUT_DIMENSIONALITY` | `1536` | Embedding size (changing requires re-index) |

## Frontend — `lexi-ai-frontend`

### Required

| Variable | Example / Source | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://lexi-ai-backend.onrender.com` | Backend base URL (browser + `/api/health` proxy) — code reads this name |
| `NEXT_PUBLIC_BACKEND_URL` | same as above | Alias kept in `render.yaml`/template |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://xxxx.supabase.co` | Browser Supabase auth client |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase → Settings → API | Public anon key (RLS-protected) |

### Recommended

| Variable | Value | Purpose |
|---|---|---|
| `NODE_ENV` | `production` | Production build mode |
| `NODE_VERSION` | `20` | Pins the Node runtime |
| `PORT` | *(Render-injected)* | Next.js binds `0.0.0.0:$PORT` automatically — do not override with a fixed value |

### ⚠️ Build-time note

All `NEXT_PUBLIC_*` values are inlined into the JS bundle **during `npm run build`**. After changing any of them, run **Manual Deploy → Clear build cache & deploy**.

## Quick copy — Backend

```
GEMINI_API_KEY=<your-key>
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=<anon-key>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
ENVIRONMENT=production
DEBUG=false
PYTHON_VERSION=3.12.6
CHROMA_DB_PATH=/tmp/chroma
FRONTEND_URL=https://lexi-ai-frontend.onrender.com
```

## Quick copy — Frontend

```
NEXT_PUBLIC_API_URL=https://lexi-ai-backend.onrender.com
NEXT_PUBLIC_BACKEND_URL=https://lexi-ai-backend.onrender.com
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key>
NODE_ENV=production
NODE_VERSION=20
```

## Secrets handling

- Set via Dashboard → service → **Environment** (or Blueprint prompts)
- Values are write-only in the dashboard after save (Render hides them)
- Rotating a key: update the value → **Save & Deploy**. For `NEXT_PUBLIC_*`, clear the build cache
- If a secret ever leaked: rotate at the provider (Supabase dashboard / AI Studio) **before** editing Render
