# Release Notes — v1.0.0 "First Light"

**Release date:** 2026-09-25 · **Tag:** `v1.0.0`

Lexi AI's first public release: an AI-powered legal assistant that extracts clauses, scores risk, answers questions about your documents, and compares contracts — built on Next.js 15, FastAPI, Google Gemini, LangChain, ChromaDB, and Supabase.

## ✨ Highlights

### 📄 Document intelligence
- Upload PDF/DOCX/images (drag & drop) with size/page limits and private Supabase Storage
- Text extraction with OCR fallback for scanned documents
- Gemini-structured **clause extraction**: type, title, plain-English summary, risk per clause
- Document **risk score 0–100** (low/medium/high) with per-clause rationale — schema-validated with retry, raw model output never reaches the API

### 💬 Grounded chat (RAG)
- Ask questions about any analyzed document; answers cite the clauses they use
- Gemini embeddings (1536-dim) + persistent ChromaDB; indexed once per document
- Conversation history with clear-history support

### ⚖️ Smart comparison
- Clause-to-clause similarity mapping between any two documents

### 🔐 Security & auth
- Supabase Auth (JWT) verified server-side on every protected route
- Row-level ownership on all queries (cross-user access → 404)
- Private bucket + short-lived signed URLs; service-role key never leaves the backend

### 🔄 Engineering quality
- Registry-backed polling: one chain per document, duplicate-proof, permanent termination, 401 retry-once — enforced by a 47-test frontend stability/contract suite
- Structured logging, strict Pydantic schemas, typed frontend service layer
- GitHub Actions CI: lint · typecheck · build · tests (frontend), compileall · pytest (backend)

## 🚀 Deployment
- Render-ready: separate FastAPI & Next.js Web Services with documented build/start commands, health-check paths (`/health`, `/api/health`), and `$PORT` binding
- Full guide in [README → Deployment](./README.md#️-deployment-render)

## 📚 Documentation
- Flagship README with architecture, schema, RAG flow, polling lifecycle, and auth diagrams (Mermaid)
- `PROJECT_STRUCTURE.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY_CHECKLIST.md`

## ⚠️ Known limitations
- Render free tier has an ephemeral disk — ChromaDB re-indexes on cold start
- Analysis latency depends on Gemini quota; long documents take longer
- Educational tool — **not legal advice**

## 🙏 Thanks
Thanks to everyone who tested the pre-release builds. See [CONTRIBUTING.md](./CONTRIBUTING.md) to get involved in v1.1.
