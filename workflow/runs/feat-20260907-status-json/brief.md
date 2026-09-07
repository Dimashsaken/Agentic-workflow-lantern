# Feature Brief: Machine-readable pipeline status

- **Run ID:** feat-20260907-status-json
- **Author:** dimash (drafted via Claude session — the first auto-coding proof run, D14)
- **Assigned developer:** the `coding` agent (auto mode)
- **Date:** 2026-09-07
- **Target release:** —
- **Product repo:** https://github.com/Dimashsaken/Agentic-workflow-lantern
- **Base branch:** main
- **Coding mode:** auto

## Problem

`python pipeline.py status` prints a fixed-width table meant for eyes. Scripts, the
Slack front door that is planned next, and the chat surface all want the same two facts
("which runs are active, which gates are pending") and today have to scrape that table
or open their own database connection.

## Desired outcome

`python pipeline.py status --json` prints exactly one JSON object on stdout carrying
the facts the table shows: `runs` (a list of `{id, status, current_stage, updated_at,
coding_mode, product_repo}`) and `pending_gates` (a list of `{run_id, gate,
requested_at}`), timestamps as UTC ISO-8601 strings. Success: `python pipeline.py
status --json | python -m json.tool` succeeds, and the human-readable output is
byte-for-byte unchanged when the flag is absent.

## Scope

- A `--json` flag on the existing `status` subcommand in `tools/azure-runner/pipeline.py`.
- The JSON is built from the SAME two queries `cmd_status` already runs (extend the
  runs SELECT with `product_repo`; the `coding_mode` column already exists). No new
  queries.
- A stdlib `unittest` module `tools/azure-runner/test_status_json.py` covering the JSON
  shaping with a fake connection object (the fake-pool pattern in
  `tools/mission-control/test_gate_latency.py`; no database). The shaping should live in
  a small pure function (rows → dict) so the test needs no asyncio plumbing beyond
  `asyncio.run`.
- One short paragraph in `tools/azure-runner/README.md` under "The pipeline runner",
  next to the existing `python pipeline.py status` line.

## Non-goals

- No new database queries, tables, or columns. No change to Mission Control, the chat
  surface, or the runboard.
- No filtering, sorting, or paging options; no `--json` on any other subcommand.
- No new packages (stdlib `json` only).

## Constraints

- Timestamps: `datetime.isoformat()` of the timestamptz values (they are UTC).
- The human table must stay byte-identical when `--json` is absent (it is what people
  and existing notes rely on).
- Follow the file's conventions: argparse subparsers, `asyncio.run(cmd_…)`, plain ASCII
  in console output (Windows consoles choke on emoji and arrows).
- Two or three small commits, one per task, each with its test.

## Existing context

- `cmd_status` in `tools/azure-runner/pipeline.py` — two queries: active runs (status not
  done/cancelled) and pending approvals.
- `runs.coding_mode` and `runs.product_repo` exist (`tools/azure-runner/schema.sql`).
- This is a dogfood run: the product repo IS the control plane. Stage 1 (UI/UX) does not
  apply — the feature has no user-facing surface; `ux_signoff` is recorded as waived in
  this run's `gate-decisions.md` and the run was imported directly at `02-pre-coding`.

## Human-in-the-loop preferences

- No new packages. Report `Status: BLOCKED` with one question if the change needs
  anything beyond `pipeline.py`, one new test file, and the README paragraph.
