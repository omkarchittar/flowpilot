# FlowPilot

Read `docs/PRD.md`, `docs/architecture.md`, and `docs/implementation-plan.md` before changing scope.

- This is an independent repository. Do not edit its parent or sibling repositories.
- Backend: Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL.
- Frontend: Next.js App Router, TypeScript. User-facing claims must come from persisted API data.
- Keep providers, domain rules, persistence, and HTTP endpoints separate.
- Never log prompts, document contents, credentials, raw tax IDs, or bank details.
- Write behavior tests for correctness and security invariants. PostgreSQL tests must exercise actual PostgreSQL.
- Record verified progress and remaining requirements in `docs/implementation-plan.md`.
- Never describe synthetic fixtures or offline algorithms as live LLM benchmark results.
