# Contributing to Lexi AI

Thank you for considering a contribution! This guide keeps the process fast and predictable.

## 🧭 Project overview

- **`frontend/`** — Next.js 15 (App Router), TypeScript, Tailwind, React Query
- **`backend/`** — FastAPI, Python 3.12, Gemini AI, LangChain, ChromaDB
- **`supabase/`** — schema migrations

Read [`PROJECT_STRUCTURE.md`](./PROJECT_STRUCTURE.md) for a guided tour and [`README.md`](./README.md) for local setup.

## 🚀 Getting started

```bash
git clone https://github.com/your-username/lexi-ai.git
cd lexi-ai

# Backend
cp backend/.env.example backend/.env        # fill in your keys
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (second terminal)
cp frontend/.env.example frontend/.env.local
cd frontend && npm install
npm run dev
```

## 🔄 Workflow

1. **Open an issue first** for anything non-trivial — describe the bug or propose the feature before writing code.
2. Fork and create a branch from `main`:
   ```bash
   git checkout -b feat/short-description
   ```
3. Follow the [Conventional Commits](https://www.conventionalcommits.org/) style (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `deploy:`).
4. Keep PRs focused — one feature or fix per PR.
5. Push and open a PR using the provided template.

## ✅ Before you open a PR

All checks must pass locally (CI runs the same):

```bash
# Frontend
cd frontend
npm run lint
npm run typecheck
npm run build
npm test

# Backend
cd backend
python -m compileall app
pytest          # optional but encouraged for service changes
```

## 🎨 Code style

| Area | Convention |
|---|---|
| TypeScript | Strict mode; no unused variables; prefer named exports |
| React | Function components + hooks; keep components small |
| Python | Type hints everywhere; docstrings on public functions |
| Errors | Frontend: differentiate auth/network/server (see `compare/results/page.tsx` pattern). Backend: raise `HTTPException` with clear detail |
| Secrets | **Never** commit `.env` files or keys. All config via environment variables |

## 🧪 Testing expectations

- Behavior changes need tests. Frontend regression suites live in `frontend/scripts/verify-*.test.ts`; backend pytest suites in `backend/tests/`.
- Preserve the polling lifecycle guarantees (one chain per document, 401 retry-once) — the stability suite enforces them.

## 📦 Commit message guide

```
feat: add DOCX export for analysis reports
fix: stop duplicate analyze triggers in compare card
docs: expand Render deployment guide
refactor: extract clause similarity into compare service
chore: bump next to 15.5.25
```

## 🐛 Found a bug?

Open a [bug report](./.github/ISSUE_TEMPLATE/BUG_REPORT.md) with reproduction steps, expected vs actual behavior, and environment details.

## 💡 Ideas & roadmap

Check the roadmap in [`README.md`](./README.md#-roadmap) — items marked there are fair game. New ideas: open a [feature request](./.github/ISSUE_TEMPLATE/FEATURE_REQUEST.md).

---

By contributing, you agree that your contributions are licensed under the [MIT License](./LICENSE).
