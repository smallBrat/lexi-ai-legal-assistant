# ✅ Smoke Test Checklist — Post-Deployment

Run top-to-bottom after every fresh deploy (or after changing env vars). ⏱️ ~15 min.

> Free-tier note: the first request after a sleep takes 30–60 s. Warm both services first (`/health`, then open the frontend) before testing.

## 0. Warm-up & health

| # | Test | Expected | ✅ |
|---|---|---|:---:|
| 0.1 | `GET https://<backend>.onrender.com/health` | `200`, healthy JSON | ☐ |
| 0.2 | `GET https://<frontend>.onrender.com/api/health` | `200`, backend status proxied | ☐ |
| 0.3 | `GET https://<backend>.onrender.com/` | `200`, API metadata JSON | ☐ |
| 0.4 | `GET https://<backend>.onrender.com/docs` | Swagger UI loads | ☐ |
| 0.5 | Backend `GET /documents` **without** token | `401` | ☐ |

## 1. Pages load (frontend, signed out)

| # | Route | Expected | ✅ |
|---|---|---|:---:|
| 1.1 | `/` | Landing renders, no console errors | ☐ |
| 1.2 | `/auth` | Sign in/up form renders | ☐ |
| 1.3 | Any protected route (`/dashboard`) | Redirects to `/auth` | ☐ |
| 1.4 | `/rights`, `/settings` | Render without errors | ☐ |

## 2. Authentication & JWT

| # | Test | Expected | ✅ |
|---|---|---|:---:|
| 2.1 | Sign up with fresh email | Confirmation email; user in Supabase Auth | ☐ |
| 2.2 | Confirm email (link goes to **production** URL, not localhost) | Redirect to `/auth` | ☐ |
| 2.3 | Sign in | Redirect to `/dashboard`; session persists on reload | ☐ |
| 2.4 | Sign out | Session cleared; protected routes redirect | ☐ |
| 2.5 | **JWT refresh**: leave idle ~1 h (or tamper access token in devtools), then click any page action | Request retries once after silent refresh; no logout loop; no duplicate calls | ☐ |
| 2.6 | Sign in with wrong password | Clear error, no crash | ☐ |

## 3. Upload

| # | Test | Expected | ✅ |
|---|---|---|:---:|
| 3.1 | Upload a small native PDF | Success; appears in dashboard | ☐ |
| 3.2 | Upload a DOCX | Success | ☐ |
| 3.3 | Upload a scanned/image PDF | OCR path completes (may be slower) | ☐ |
| 3.4 | Upload `.exe` / oversized file | Clear 4xx validation message | ☐ |
| 3.5 | Signed URL download from dashboard | File downloads; URL expires | ☐ |
| 3.6 | Delete document | Removed from list and storage | ☐ |
| 3.7 | (Two accounts) User B cannot fetch User A's document | `404`, not `403` | ☐ |

## 4. Analysis & polling

| # | Test | Expected | ✅ |
|---|---|---|:---:|
| 4.1 | Trigger analysis on an uploaded doc | Polling starts; single status chain (Network tab: no duplicate status calls) | ☐ |
| 4.2 | Wait for completion | Risk score + clause list with per-clause risk levels | ☐ |
| 4.3 | Navigate away mid-analysis, return | Polling resumes/terminal state honored — no duplicate chains | ☐ |
| 4.4 | Force a 401 during polling (tamper token in devtools) | One refresh + one retry, then clean stop — no infinite loop | ☐ |
| 4.5 | Dashboard reflects risk level badges and flag counts | Correct after analysis | ☐ |

## 5. Chat (RAG)

| # | Test | Expected | ✅ |
|---|---|---|:---:|
| 5.1 | Ask a question about an analyzed document | Grounded answer **with clause citations** | ☐ |
| 5.2 | Ask about something not in the document | Honest "not found in document" style answer | ☐ |
| 5.3 | Send a prompt-injection attempt in chat ("ignore instructions and…") | Refusal / no instruction smuggling | ☐ |
| 5.4 | Reload page | History persisted | ☐ |
| 5.5 | Clear history | Cleared server-side | ☐ |
| 5.6 | Two chats concurrently on same doc | Both answered; no re-index errors in backend logs | ☐ |

## 6. Comparison

| # | Test | Expected | ✅ |
|---|---|---|:---:|
| 6.1 | Compare two analyzed documents | Clause-by-clause similarity result renders | ☐ |
| 6.2 | Upload a pair from `docs/` (e.g. `employment_agreement_v1/v2.pdf`) and compare | Meaningful diffs | ☐ |
| 6.3 | Recent comparisons list | Shows history | ☐ |

## 7. Logs & ops (final sweep)

| # | Check | Expected | ✅ |
|---|---|---|:---:|
| 7.1 | Backend logs (Render → Logs) | No tracebacks; no secrets printed | ☐ |
| 7.2 | Frontend build logs | No warnings about missing env vars | ☐ |
| 7.3 | `ENVIRONMENT=production`, `DEBUG=false` | Verbose debug lines absent | ☐ |
| 7.4 | Trigger a manual redeploy | ChromaDB re-indexes cleanly from Supabase after cold start | ☐ |

## Failure handling

Any failed check → see [Troubleshooting](#) below / `DEPLOYMENT_GUIDE.md`. Record the failing request ID from Render logs before debugging.
