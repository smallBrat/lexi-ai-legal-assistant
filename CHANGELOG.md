# Changelog

All notable changes to Lexi AI are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org).

## [1.0.0] — 2026-09-25

First public release. 🎉

### Added
- **Document upload** — drag-and-drop PDF/DOCX/image with size & page limits, private Supabase Storage, short-lived signed download URLs.
- **AI risk analysis** — Gemini-structured clause extraction (type, title, summary, risk per clause), document-level 0–100 risk score bucketed low/medium/high, validated with strict Pydantic schemas and retry.
- **Chat with document (RAG)** — grounded Q&A with clause citations and confidence scores; Gemini embeddings (1536-dim) + persistent ChromaDB; conversation history with delete.
- **Smart document comparison** — clause-to-clause similarity mapping between two documents.
- **Rights assistant** — know-your-rights guidance UI.
- **Dashboard** — search, risk-level filter, sorting, flag counts; report page with full analysis export view.
- **Authentication** — Supabase Auth (JWT) with server-side verification, automatic session refresh, row-level ownership on every query.
- **Resilient polling lifecycle** — registry-backed timers guaranteeing one polling chain per document, duplicate-proof `startFresh()`, permanent `terminatePolling()`, 401 → refresh once / retry once.
- **Health endpoints** — backend `/health` plus a production-clean 5s-timeout `/api/health` proxy for Render health checks.
- **OCR fallback** — scanned PDFs/images with timeout guard.
- **Developer tooling** — reindex CLI, Gemini smoke-test scripts, structured logging with level control.
- **CI** — GitHub Actions pipeline: frontend lint/typecheck/build/tests + backend compileall/pytest.

### Security
- Strict env-var hygiene: only `.env.example` templates committed; service-role key backend-only.
- 47-test frontend stability/contract suite including regression guards against debug instrumentation.

### Deployment
- Render-ready: separate FastAPI and Next.js Web Services with documented build/start commands, health-check paths, and `$PORT` binding.

[1.0.0]: https://github.com/your-username/lexi-ai/releases/tag/v1.0.0
