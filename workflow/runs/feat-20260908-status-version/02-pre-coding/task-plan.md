# Task plan — feat-20260908-status-version

## 1. status_payload() returns pipeline_version (AC-1)

In `tools/azure-runner/pipeline.py`, `status_payload(runs, pending_gates)` builds the
`status --json` object. Add a top-level `"pipeline_version": PIPELINE_VERSION` key. Keep
`runs` and `pending_gates` exactly as they are. Size XS.

## 2. test_status_json.py asserts pipeline_version (AC-2)

In `tools/azure-runner/test_status_json.py` (stdlib unittest, run with the venv python)
add a test that calls `status_payload([], [])` and asserts `payload["pipeline_version"] ==
pipeline.PIPELINE_VERSION`, and one that the key is present when runs and gates exist
(reuse the file's `run_row()` / `gate_row()` helpers). Size XS.

## Write scope

`tools/azure-runner/pipeline.py`, `tools/azure-runner/test_status_json.py` — nothing else.

## Blast radius

`status_payload` has two callers: `cmd_status` and the tests. Mission Control reads
`runs`/`pending_gates` only; an extra key is additive.
