<!-- Title: follow Conventional Commits — feat: / fix: / docs: / refactor: / chore: / deploy: -->

## Summary
What does this PR do, and why? One or two sentences.

## Type of Change
- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [ ] ✨ New feature (non-breaking change that adds functionality)
- [ ] 💥 Breaking change (fix or feature that would cause existing functionality to change)
- [ ] 📝 Documentation
- [ ] ♻️ Refactor (no behavior change)
- [ ] 🔧 Chore / tooling / CI

## How Has This Been Tested?
Describe the tests you ran. e.g. `npm test`, `pytest`, manual flow steps.

## Checklist
- [ ] `npm run lint` and `npm run typecheck` pass (frontend changes)
- [ ] `npm run build` succeeds (frontend changes)
- [ ] `python -m compileall app` passes (backend changes)
- [ ] New/changed behavior is covered by tests
- [ ] Polling lifecycle guarantees preserved (if touching `use-polling` / `polling-registry`)
- [ ] No secrets, `.env` files, or hardcoded production URLs added
- [ ] API contracts unchanged, or changes are documented in `CHANGELOG.md`

## Screenshots (if UI change)
Before / after.
