# Codebase research — feat-20260908-runboard-stage-timestamps

## What exists

- `tools/azure-runner/pipeline.py` owns the runboard end to end. `render_runboard()` selects active `runs` rows, pending `approvals`, and recent completed runs, then overwrites `workflow/RUNBOARD.md`. The active table currently has one `Updated` value per run, rendered from `runs.updated_at` at day precision (`%Y-%m-%d`); it does not query stage history.
- The state transition chain is also in `tools/azure-runner/pipeline.py`: a daemon claim updates the run to `executing`; agent execution inserts a `stage_executions` row and logs `stage_started`; completion sets `finished_at` and logs `stage_succeeded`; failures set `finished_at` and log `stage_failed`; `advance()`, gate opening/decisions, and retry update the run row. Core run creation, execution completion/failure, gate decisions, and retry paths call `render_runboard()`.
- `tools/azure-runner/schema.sql` already stores several timestamp families: run-level `created_at`, `updated_at`, and `completed_at`; execution-level `started_at`, `finished_at`, and `heartbeat_at`; approval-level `requested_at` and `decided_at`; and append-only event `at`. There is no single stage-level `updated_at` column.
- Stage identity is not one-to-one with the visible stage directory. In `tools/azure-runner/pipeline.py`, `01-ui-ux.diverge` and `01-ui-ux.design` are separate execution keys but both map to `01-ui-ux`; the human-mode `03-coding` branch opens its gate without inserting an execution row.
- `workflow/RUNBOARD.md` is the current generated artifact. Its active table exposes run, title, current stage, status, wait reason, and a date-only updated value. `docs/AGENT-TOOLING.md` identifies this file as every agent's first orientation view, so its consumers include the fleet as well as human readers.

### Existing flow

1. `tools/azure-runner/pipeline.py` mutates `runs`, `stage_executions`, `approvals`, and `events` while a run advances.
2. `tools/azure-runner/schema.sql` supplies the persisted timestamps for those mutations.
3. `tools/azure-runner/pipeline.py::render_runboard()` reads a subset of that state and rewrites `workflow/RUNBOARD.md`.
4. `docs/AGENT-TOOLING.md` directs downstream agents to read the rendered file for stage and blocking orientation.

## Patterns to imitate

- `tools/azure-runner/pipeline.py` — canonical renderer and lifecycle entry point; it keeps runboard generation in one function and refreshes the derived file after state transitions.
- `tools/mission-control/app.py` — existing stage-history aggregation. `snapshot()` fetches the latest execution per `(run_id, stage)`, then collapses execution phases through `STAGE_DIR` to a latest record per visible stage directory. The board selects an age source by state: approval request time for gates, execution start for active work, and run update time for queued/failed states.
- `tools/mission-control/ui.py` — existing human-readable elapsed-time formatter. `ago()` clamps future values to zero and formats seconds, minutes, hours, and days.
- `tools/azure-runner/test_status_json.py` — timestamp contract exemplar using fixed timezone-aware datetimes, fake connections, exact output assertions, and `datetime.isoformat()` checks.
- `tools/mission-control/test_gate_latency.py` — exemplar for operational-age behavior: fixed clocks, exact 24-hour boundary tests, future-time handling, fake database rows, and constant-query-count checks.

## Similar features

- **Mission Control stage rail and run detail** — `tools/mission-control/app.py`, `tools/mission-control/ui.py`. This already derives per-visible-stage latest execution state, renders elapsed ages, shows attempt durations, and distinguishes active, queued, failed, gate-waiting, and completed states.
- **Gate latency and stale review cards** — `tools/mission-control/app.py`, `tools/mission-control/test_gate_latency.py`. This already defines stale as strictly older than 24 hours for pending review gates and verifies boundary and empty/error states. That rule is local to Mission Control's gate review UI; the runboard renderer has no equivalent classification.
- **Machine-readable status timestamps** — `tools/azure-runner/test_status_json.py`, `tools/azure-runner/pipeline.py`. Status JSON preserves timezone offsets and exact timestamps, while the human runboard currently truncates its only timestamp to a date.

## Risks

1. **Medium — “stage last changed” has no single persisted source.** `tools/azure-runner/schema.sql` separates execution start/finish, gate request/decision, event time, and run-level update time. `runs.updated_at` also changes for non-stage metadata such as product-target and coding-mode edits in `tools/azure-runner/pipeline.py`, so it is not a clean per-stage timestamp.
2. **Medium — visible stages and execution rows differ.** `tools/azure-runner/pipeline.py` has two UI/UX execution phases sharing one visible directory, while human-mode coding has no execution row. A stage timestamp derived only from `stage_executions` would therefore have uneven coverage.
3. **Medium — the renderer has no direct behavior test.** The tracked runner tests include timestamp coverage for status JSON in `tools/azure-runner/test_status_json.py`, but no test calls `render_runboard()` or asserts the `workflow/RUNBOARD.md` table shape. A shared orientation artifact can regress without a focused test.
4. **Low — existing “stale” semantics are narrower than the brief.** `tools/mission-control/app.py` marks only pending review cards stale after 24 hours; queued, executing, failed, and completed runs choose different clocks but are not all classified as stalled. The runboard currently has neither elapsed-time formatting nor a stalled/slow distinction.

## Conventions

- `workflow/RUNBOARD.md` is generated only by `python pipeline.py runboard`; agents never edit it directly (`AGENTS.md`, `docs/AGENT-TOOLING.md`, and `tools/azure-runner/README.md`).
- The database uses `timestamptz`, and timestamp-facing tests use timezone-aware UTC datetimes (`tools/azure-runner/schema.sql`, `tools/azure-runner/test_status_json.py`).
- Runner behavior tests use stdlib `unittest` with fake connections rather than requiring live Postgres where possible. The documented commands are `python3 -m unittest test_status_json -v` from `tools/azure-runner` and `python -m unittest test_gate_latency -v` from `tools/mission-control`.
- Operational list rendering is batch-oriented. `tools/mission-control/test_gate_latency.py` asserts query count stays constant as run count grows; `tools/mission-control/app.py` builds latest-stage maps from bulk queries instead of querying once per run.
- The rendered runboard is automatically refreshed on core pipeline state changes and is consumed as a compact orientation index; detailed attempts and audit history remain in the database and run pages (`tools/azure-runner/pipeline.py`, `docs/AGENT-TOOLING.md`).

## Likely files

- `tools/azure-runner/pipeline.py` — contains the sole runboard query, table schema, formatting, write, and refresh call sites.
- `tools/azure-runner/schema.sql` — defines all existing candidate timestamp sources and their stage/run/gate relationships.
- `tools/azure-runner/test_status_json.py` — nearest runner-level fake-connection and exact timestamp-output test pattern.
