# Working in this repository

Read `README.md` first: product scope, architecture and the adapter rule live there.

## Commands

- Install: `pip install -e '.[dev]'` (Python 3.12; the factory sandbox has it)
- Test: `python3 -m pytest -q` — must stay green; it is the quality gate
- Lint: `ruff check .` — also the gate; `ruff check --fix .` before committing
- Run: `uvicorn app.main:app --reload`

## How code is written here

- Thin routers (`app/routers/`), logic in `app/services/`, models in `app/models.py`,
  external systems behind `app/adapters/`. A router that talks to SQLAlchemy directly or
  calls an HTTP API is a review finding.
- Every table has `business_id`; every query filters by it. Cross-tenant reads are sev-1.
- Server-rendered Jinja2 pages extend `app/templates/base.html`; forms post and redirect;
  every state a user can reach has an empty state and an error state.
- Tests: `tests/test_<area>.py`, pytest + FastAPI `TestClient`, a fresh SQLite database per
  test via the `client` fixture in `tests/conftest.py`. Test behaviour through HTTP, not
  internals. No network, no paid APIs — use the sandbox channel and the rule-based
  assistant.
- Secrets and configuration come only from environment variables read in
  `app/config.py`; document every new variable in `.env.example`.
- Migrations: SQLAlchemy `create_all` in dev/tests; production schema changes ship an
  Alembic migration once Alembic is introduced (a planning decision, `HITL: required`).
- Commit messages: `<run-id>: <imperative summary>`.

<!-- lantern-factory:start -->
## Built by the Lantern software factory

Since 2026-09-11 this repository is worked on by the Lantern software factory (agents propose, code disposes). Feature runs research, plan, implement and verify changes here through fixed stages with human gates. What that means for anyone — human or agent — working in this checkout:

- The coding agent works on `feat/*`, `fix/*` or `proto/*` branches only, commits as `lantern-bot`, and never pushes or merges itself; a human reviews every pull request.
- After every coding turn the commands in `lantern.toml` run **as code**; only red output goes back to the agent, for a bounded number of fix rounds, and nothing is handed off while a command fails. Keep them truthful — they are the gate:
- `test`: `pytest -q`
- `lint`: `ruff check .`
- Commits outside the approved plan's write scope are refused at handoff.
- Regression tests the factory writes live under `lantern/regressions/`; keep the test command covering that directory.
<!-- lantern-factory:end -->
