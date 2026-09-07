# Stage Report: 03-coding — feat-20260907-status-json

- **Agent/author:** coding
- **Date:** 2026-09-07
- **Status:** PASS

## Summary

Implemented and documented `pipeline.py status --json` with a pure payload shaper and focused behavior tests. The command retains exactly two database queries and the legacy human output is regression-tested. All focused tests pass; the committed branch is ready for human code review and QA.

## Work performed

- Added `tools/azure-runner/test_status_json.py` to cover exact payload keys, UTC ISO-8601 timestamps, nullable repository values, empty inputs, query count/selection, parseable JSON-only stdout, and exact legacy stdout.
- Added `status_payload`, the `--json` argparse flag, JSON dispatch, and `product_repo` to the existing runs query in `tools/azure-runner/pipeline.py`.
- Documented the JSON form beside the status command in `tools/azure-runner/README.md`.
- Self-reviewed the complete diff from `8e0094c` through `b192ee9`; only the three approved product paths changed and the working tree is clean.

## Findings / results

1. **PASS:** `cd tools/azure-runner && /tmp/status-json-venv/bin/python -m unittest test_status_json -v` — 5 tests passed.
2. **PASS:** `cd tools/azure-runner && /tmp/status-json-venv/bin/python test_coding_stage.py` — all auto-coding properties hold.
3. **PASS:** `python3 -m py_compile tools/azure-runner/pipeline.py tools/azure-runner/test_status_json.py` and `git diff --check 8e0094c..HEAD`.
4. **Environment note:** the system Python lacked the repository dependencies, so focused tests used a temporary virtual environment populated from `tools/azure-runner/requirements.txt`; no product dependency files changed.

## Artifacts

- `report.md` — implementation and QA handoff.
- Product commits:
  - `dd62c33` — task 1: lock status output contract.
  - `40df07c` — task 2: add JSON status output.
  - `b192ee9` — task 3: document JSON status output.

## Deviations

None.

## QA confidence map

1. **Highest risk — legacy stdout compatibility:** exercise empty, human-mode, auto-mode, and pending-gate rows; exact representative strings are covered, but production row combinations remain worth checking.
2. **JSON timestamp assumptions:** verify real asyncpg `timestamptz` rows carry UTC-aware datetimes and render the expected `+00:00` suffix.
3. **CLI/database integration:** run both `status` and `status --json` against a populated development database to confirm parser dispatch, row access, and clean stdout end to end.

## Handoff notes for the next stage

Start with `tools/azure-runner/test_status_json.py`, then compare both CLI modes against a populated development database. No schema, package, query-count, sorting, Mission Control, chat, or runboard behavior changed.

## Open questions (BLOCKED status must have exactly one)

None.

## Memory candidates

2026-09-07: For a CLI machine-output mode, execute shared database reads before branching into renderers and freeze legacy stdout with exact-string tests, because this preserves query parity and catches accidental compatibility changes.
