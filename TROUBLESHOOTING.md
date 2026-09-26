# 🔧 Troubleshooting Guide — Render Deployments

Render-specific fixes for the failures you're most likely to hit with Lexi AI.

## Build failed

**Symptoms:** deploy dies during `npm run build` or `pip install`.

| Cause | Fix |
|---|---|
| Missing `NEXT_PUBLIC_*` at build time | Build logs show missing-env errors. Add the variables, then **Manual Deploy → Clear build cache & deploy** (they are inlined at build time — a plain restart won't help). |
| `npm ci` lockfile mismatch | This repo uses `npm install` in the build command, which tolerates drift. If you switch to `npm ci`, commit `frontend/package-lock.json` and keep it in sync. |
| OOM during Next.js build on free tier | Free plan has limited RAM. `optimizePackageImports` is already enabled; if you still hit OOM, reduce concurrent builds or upgrade to the starter plan. |
| Wrong Python version | Add env var `PYTHON_VERSION=3.12.6` to the backend service. |
| Wrong Node version | Add env var `NODE_VERSION=20` to the frontend service. |
| `pip install` fails on a native wheel | Check the failing package in logs (ChromaDB/PyMuPDF wheels exist for linux x86_64 on Python 3.12); pin an older version if a new release broke packaging. |

## Missing env / variable not picked up

**Symptoms:** runtime 500s, "undefined" API URL, auth calls going to `localhost`.

1. Verify the variable exists on the **correct service** (frontend vars on frontend, backend vars on backend — the #1 mistake).
2. `NEXT_PUBLIC_*` → must exist **before the build**; after editing, always **Clear build cache & deploy**.
3. No trailing slash in URLs — `api-client.ts` strips one, but the health route does not.
4. Check Render → service → **Environment** tab shows the variable (values are hidden after save; look for the key name).

## Port binding failed

**Symptoms:** deploy succeeds, health check times out, "no service detected on port".

| Cause | Fix |
|---|---|
| Hardcoded port (`--port 8000`) | Use `uvicorn app.main:app --host 0.0.0.0 --port $PORT` — Render injects `$PORT` per deploy. |
| Missing `--host 0.0.0.0` | Uvicorn defaults to `127.0.0.1`, which Render cannot reach. Always bind `0.0.0.0`. |
| Frontend port override | Do **not** set `PORT` to a fixed value on the frontend; `next start` respects Render's injected `PORT` automatically. |
| App boots but binds late | If ChromaDB init blocks startup > 90 s, the health check fails. Set `CHROMA_DB_PATH=/tmp/chroma` to start from a clean, fast path. |

## Sleeping service (free tier)

**Symptoms:** first request takes 30–60 s; app "works fine after that".

- Free instances sleep after ~15 min without inbound traffic.
- Mitigation: an external pinger (cron-job.org / UptimeRobot) hitting `https://<backend>.onrender.com/health` every 10 min keeps it warm (within fair-use limits).
- The frontend `/api/health` proxy has a 5 s timeout — a sleeping backend makes it return `502` until warm. This is expected; warm the backend first.
- A sleeping **frontend** cannot be pre-warmed by a pinger on `/api/health` alone — ping `/` too.

## 502 from health endpoint

| Cause | Fix |
|---|---|
| Backend asleep / cold-starting | Wait 30–60 s and retry; `/api/health` returns `502` only when the backend is unreachable (its 5 s fetch timeout). |
| Backend crashed on boot | Check Render → backend → **Logs**. Common: missing `GEMINI_API_KEY` (Settings validation fails fast) or a bad `SUPABASE_URL`. |
| Bad `NEXT_PUBLIC_API_URL` (typo, http vs https) | Backend URL must be `https://...onrender.com` with no trailing slash. |
| Backend deploy failed while frontend expects it | Deploy backend first, confirm `/health` → `200`, then redeploy frontend. |

## Supabase auth issues

| Symptom | Cause | Fix |
|---|---|---|
| Confirmation link goes to `localhost:3000` | Supabase Site URL not updated | Supabase Dashboard → Authentication → URL Configuration → **Site URL** = production frontend; add it to **Redirect URLs**. |
| `401` on every request after sign-in | Anon key mismatch or JWT not forwarded | Verify `NEXT_PUBLIC_SUPABASE_ANON_KEY` matches the same project as the backend's `SUPABASE_URL`; confirm the `Authorization: Bearer` header is present in Network tab. |
| `401` from backend despite valid token | Backend pointed at a different Supabase project | Backend `SUPABASE_URL`/keys must be from the **same project** that issued the token. |
| CORS errors in browser console | Backend doesn't allow the frontend origin | Set backend `FRONTEND_URL=https://<frontend>.onrender.com` and redeploy the backend. |

## Gemini timeout / failures

| Symptom | Fix |
|---|---|
| Analysis hangs, then `504`/timeout | Free-tier Gemini quota/rate limits. Retry after a minute; check quota in AI Studio. Long documents: reduce `MAX_PDF_PAGES`/`MAX_EXTRACTED_CHARACTERS`. |
| Cold start + analysis double-whammy | Wake the backend with `/health` first; the frontend polling hook keeps retrying but Render's request timeout (~100 s) can kill the trigger request — analysis status is server-side, so just re-open the page rather than re-triggering. |
| `429` in backend logs | Rate limited by Gemini — add spacing between bulk operations; the analysis service retries schema validation but not hard 429s. |
| Embeddings dimension mismatch after changing `EMBEDDING_OUTPUT_DIMENSIONALITY` | Old vectors are incompatible. Wipe `CHROMA_DB_PATH` and run `python -m scripts.reindex_cli`. |

## ChromaDB path issues

| Symptom | Fix |
|---|---|
| `Permission denied` / read-only FS writing to `../.chroma` | The default repo-root path doesn't exist on Render. Set `CHROMA_DB_PATH=/tmp/chroma`. |
| Vector store empty after redeploy | Expected — free-tier disk is ephemeral. Clauses re-index from Supabase on demand; run the reindex CLI if needed. |
| Need persistence | Attach a Render **Disk** (paid) and point `CHROMA_DB_PATH` at the mount, e.g. `/var/data/chroma`. |
| `chroma.sqlite3` errors after crash | `/tmp` is wiped on restart, so corruption is self-healing on free tier; on a disk mount, delete `chroma.sqlite3` and re-index. |

## Quick diagnosis flow

```
Deploy fails?        → Read build log from the top; fix the FIRST error only.
Deploy OK, 502?      → Logs tab → look for crash on boot → check env vars.
502 from frontend?   → curl backend /health directly → sleeping? cold start.
Auth 401 everywhere? → Same Supabase project on both services? Token in header?
CORS error?          → FRONTEND_URL set + backend redeployed?
```
