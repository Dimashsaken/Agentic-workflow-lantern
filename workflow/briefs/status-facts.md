# Feature Brief: Status JSON carries branch and version facts

- **Run ID:** feat-20260908-status-facts
- **Author:** dimash (drafted via Claude session — the first stage-0 proof run, D17)
- **Assigned developer:** dimash
- **Date:** 2026-09-08
- **Target release:** —
- **Product repo:** C:/Users/dimas/OneDrive/Documents/GitHub/Agentic-workflow-lantern
- **Base branch:** main
- **Working branch:**
- **Coding mode:** human

## Problem

`pipeline.py status --json` (shipped by feat-20260907-status-json) reports each run's
id, status, stage, coding mode and product repo, but not which branch the work lands
on, nor which pipeline version created the run. The Slack front door and the chat
surface need both: to link a run to its branch, and to tell runs of different pipeline
generations apart (stamping a new version is a separate change, not this one).

## Desired outcome

`pipeline.py status --json` gains, per run, `product_branch` (nullable),
`product_working_branch` (nullable) and `pipeline_version` (string), and per pending
gate an `age_seconds` integer computed at print time. The human-readable output stays
byte-identical. Success: `python pipeline.py status --json | python -m json.tool`
shows the new keys and every existing test still passes.

## Must-haves (optional — seeds the story's acceptance criteria)

- every entry of `runs` carries `product_branch`, `product_working_branch`, `pipeline_version`
- every entry of `pending_gates` carries `age_seconds`, an integer ≥ 0
- the non-JSON table output is unchanged
- no new database queries — widen the existing SELECTs only

## Scope

`tools/azure-runner/pipeline.py` (`status_payload`, `cmd_status`),
`tools/azure-runner/test_status_json.py`, one paragraph in `tools/azure-runner/README.md`.

## Non-goals

Filtering, pagination, a stability promise for the schema, Mission Control changes.

## Constraints

Standard library only; plain ASCII on stdout (Windows consoles); no schema change.

## Existing context

`status_payload()` is the pure shaper introduced by feat-20260907-status-json (PR #1);
`test_status_json.py` freezes the human-readable output. Run rows already come from one
SELECT in `cmd_status`; the `runs` table has `product_branch`, `product_working_branch`
and `pipeline_version` columns (D15, schema.sql).

## Human-in-the-loop preferences

None beyond the standard gates.

## Decisions

- 2026-09-08, claude-for-dimash (the session building D17, driving this proof run on
  dimash's behalf — not a human decision): answering the story
  phase's question — success is LIMITED to exposing the stored `pipeline_version`
  value as-is. Version stamping (`PIPELINE_VERSION = "3"`, stage 0) lands separately
  with D17; the checkout you inspected is `main` before that commit. Do not include
  version-stamping or stage-0 work in this story; write the criteria against the four
  must-haves only.
