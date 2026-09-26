# Project Structure

A guided tour of the Lexi AI repository.

```
lexi-ai/
│
├── frontend/                        # Next.js 15 App Router (TypeScript)
│   ├── app/                         # File-based routes
│   │   ├── page.tsx                 # Landing page
│   │   ├── auth/                    # Sign in / sign up
│   │   ├── upload/                  # Document upload (drag & drop)
│   │   ├── processing/              # Analysis in-progress view
│   │   ├── dashboard/               # Document list + [id] detail view
│   │   ├── compare/                 # Document comparison + results
│   │   ├── report/                  # Analysis report view
│   │   ├── rights/                  # Rights assistant
│   │   ├── saved/                   # Saved documents
│   │   ├── settings/                # User settings
│   │   ├── api/health/route.ts      # Health proxy → backend /health (5s timeout, 502 on unreachable)
│   │   ├── icon.svg                 # Static favicon (avoids /_not-found compiles)
│   │   └── layout.tsx               # Root layout, theme, providers
│   ├── components/                  # UI components
│   │   ├── shared/                  # risk-badge, clause-card, document-card, page-transition…
│   │   ├── compare/                 # compare-upload-card (once-ref analyze guards)
│   │   └── ui/                      # Primitives (badge, button…)
│   ├── hooks/
│   │   └── use-polling.ts           # Registry-backed polling: startFresh/terminatePolling,
│   │                                #   401 refresh-once retry-once, terminal-state stop
│   ├── lib/
│   │   ├── polling-registry.ts      # One timer chain per document ID; lifecycle logger
│   │   ├── api-client.ts            # Typed fetch wrapper (base URL from env)
│   │   └── supabase.ts              # Browser Supabase client
│   ├── services/                    # API service layer (upload, analyze, chat, compare, health)
│   ├── types/                       # Shared TypeScript types
│   ├── scripts/                     # node:test suites
│   │   ├── verify-analyze-request.test.ts
│   │   ├── verify-chat-request.test.ts
│   │   └── verify-frontend-stability.test.ts   # 14-suite guardrail incl. polling guarantees
│   ├── instrumentation.ts           # Dev-only Windows EPIPE/EIO guard (no lifecycle observers)
│   ├── next.config.mjs              # optimizePackageImports, webpack watch excludes
│   └── package.json                 # dev/build/start/lint/typecheck/test
│
├── backend/                         # FastAPI (Python 3.12)
│   ├── app/
│   │   ├── main.py                  # App factory, CORS, root endpoint, health router
│   │   ├── api/                     # Routers (thin controllers)
│   │   │   ├── upload.py            # POST /upload — multipart → storage + DB
│   │   │   ├── analyze.py           # POST /analyze/{id} — async risk analysis
│   │   │   ├── documents.py         # CRUD + signed-url + filters
│   │   │   ├── chat.py              # RAG chat + history endpoints
│   │   │   ├── compare.py           # Clause-by-clause comparison
│   │   │   └── health.py            # GET /health
│   │   ├── services/                # Business logic
│   │   │   ├── analysis_service.py  # Gemini structured output → validated clauses + risk score
│   │   │   ├── chat_service.py      # Grounded Q&A with citations
│   │   │   ├── compare_service.py   # Clause similarity mapping
│   │   │   ├── embedding_service.py # Gemini embeddings → ChromaDB
│   │   │   ├── retrieval_service.py # Top-k clause retrieval
│   │   │   ├── gemini_provider.py   # Swappable Gemini client
│   │   │   ├── ocr_service.py       # Scanned-doc OCR (timeout-guarded)
│   │   │   ├── storage_service.py   # Supabase Storage + signed URLs
│   │   │   └── document_service.py  # Document metadata logic
│   │   ├── repositories/            # Supabase data access (user-scoped queries)
│   │   ├── schemas/                 # Strict Pydantic models (analysis, compare, chat, document)
│   │   ├── core/
│   │   │   ├── config.py            # Pydantic Settings (env vars, SecretStr)
│   │   │   ├── security.py          # JWT verification via Supabase Auth, bearer dependency
│   │   │   ├── supabase.py          # Server Supabase client
│   │   │   └── logging.py           # Structured level-aware logging
│   │   └── router.py                # Router registration
│   ├── scripts/                     # reindex_cli.py, Gemini smoke tests
│   ├── tests/                       # pytest suites (validation, documents, compare, chat…)
│   └── requirements.txt
│
├── supabase/                        # Schema migrations
├── docs/                            # Sample legal PDFs (acts, clauses, NDAs…)
│   ├── assets/                      # Logo (see README hero)
│   ├── screenshots/                 # README gallery images
│   └── demo/                        # Demo GIFs
├── reports/                         # Integration verification artifacts
├── .github/
│   ├── ISSUE_TEMPLATE/              # Bug report, feature request
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/ci.yml             # Frontend + backend CI
├── .env.example                     # Root reference for all env vars
├── backend/.env.example
├── frontend/.env.example
├── SECURITY_CHECKLIST.md            # Security audit & pre-launch actions
├── CLEANUP_REPORT.md                # Production cleanup record
├── CHANGELOG.md · CONTRIBUTING.md · CODE_OF_CONDUCT.md · LICENSE
└── README.md                        # Flagship documentation
```

## Data flow at a glance

1. **Upload** → `frontend/services` → `POST /upload` → OCR/text extraction → Supabase Storage + `documents` row
2. **Analyze** → `POST /analyze/{id}` → Gemini structured clause extraction → validation/retry → risk score → persist → index clauses into ChromaDB
3. **Poll** → `use-polling` → registry-owned timer → status endpoint → terminal state stops the chain
4. **Chat** → embed question → ChromaDB top-k → grounded Gemini answer with citations → history persisted
5. **Compare** → `POST /compare` → clause similarity → comparison report

## Key invariants (enforced by tests)

- Exactly one polling chain per document; no polling after a terminal state
- 401 → session refresh once → retry once → terminate cleanly
- No raw model output reaches an API contract without schema validation
- Only `NEXT_PUBLIC_*` variables are browser-exposed; service-role key stays server-side
