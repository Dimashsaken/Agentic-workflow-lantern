# Research — feat-20260908-status-facts

## What exists

The status flow is contained in `tools/azure-runner/pipeline.py`: the `status` argparse subcommand dispatches through `asyncio.run(cmd_status(a.json))`; `cmd_status()` performs one active-runs fetch and one pending-approvals fetch; JSON mode passes both row sets to `status_payload()` and serializes the result with `json.dumps`; non-JSON mode formats those same rows directly. No code caller of `cmd_status()` or `status_payload()` exists beyond that CLI dispatch and `tools/azure-runner/test_status_json.py`.

The current JSON run object contains `id`, `status`, `current_stage`, ISO-formatted `updated_at`, `coding_mode`, and nullable `product_repo`. The current pending-gate object contains `run_id`, `gate`, and ISO-formatted `requested_at`. `tools/azure-runner/test_status_json.py` freezes those exact key sets, verifies there are exactly two queries, parses JSON-only stdout, and compares representative and empty human-readable output exactly.

The requested run facts already exist in storage. `tools/azure-runner/schema.sql` defines `pipeline_version` as non-null text and adds nullable `product_branch` and `product_working_branch` columns. `tools/azure-runner/pipeline.py` stamps `PIPELINE_VERSION` when creating or importing a run and writes the two branch columns during run creation or product-target updates. Its D15 helpers treat `product_branch` as the base branch; a null `product_working_branch` means the effective work branch is derived from the run id, so the nullable database fact and the resolved branch name are distinct concepts. `docs/DECISIONS.md` records the same compatibility rule for pre-D15 runs.

Pending-gate age has two nearby precedents. `tools/azure-runner/chat_service.py` captures one timezone-aware `now` per snapshot and computes elapsed time from `requested_at`. Mission Control passes one render-time `now` through `tools/mission-control/app.py`; `tools/mission-control/ui.py` converts elapsed seconds with `max(0, int(seconds))`, and `tools/mission-control/test_gate_latency.py` pins exact-boundary and future-timestamp behavior. These surfaces query the database independently; they do not consume `status --json`.

## Patterns to imitate

- `tools/azure-runner/pipeline.py` — established status chain: two shared reads, a small row-to-dict shaper for JSON, and a separate unchanged human renderer.
- `tools/azure-runner/test_status_json.py` — focused contract tests use plain `unittest`, dict rows, a fake async connection, query recording, JSON parsing, and exact stdout strings without a database.
- `tools/azure-runner/chat_service.py` — an existing machine-readable snapshot computes all elapsed values from one UTC `now` captured after the reads.
- `tools/mission-control/ui.py` — existing elapsed-time normalization truncates to an integer and clamps future timestamps to zero.
- `tools/azure-runner/schema.sql` — source of truth for nullability and types of all four requested database-backed facts.

## Similar features

- **Machine-readable pipeline status (direct predecessor):** `tools/azure-runner/pipeline.py`, `tools/azure-runner/test_status_json.py`, `tools/azure-runner/README.md`, and `workflow/runs/feat-20260907-status-json/brief.md`. It already supplies the flag, pure payload boundary, two-query invariant, exact human-output regression test, and adjacent documentation.
- **Gate-age rendering:** `tools/mission-control/app.py`, `tools/mission-control/ui.py`, and `tools/mission-control/test_gate_latency.py`. It already supplies a render-time clock convention, nonnegative future-time behavior, and deterministic fixed-time test fixtures.
- **Branch provenance:** `tools/azure-runner/pipeline.py`, `tools/azure-runner/schema.sql`, and `docs/DECISIONS.md`. It already distinguishes base branch, nullable stored working branch, and derived effective working branch.

## Risks

1. **Medium — pipeline-version provenance is outside the requested projection.** In this checkout `tools/azure-runner/pipeline.py` still sets `PIPELINE_VERSION = "2"`, and its `FEATURE_STAGES` begins at stage 1, while the brief says v3 is distinguished by the new stage 0. Exposing the stored column reports faithfully but cannot create a v2/v3 distinction that was not stamped when a run was created. This is the single riskiest finding.
2. **Medium — gate age introduces wall-clock behavior into a currently deterministic shaper.** `tools/azure-runner/test_status_json.py` calls `status_payload()` directly and also recomputes an expected payload after command execution. An integer-second boundary can make two calls differ unless the clock behavior is made testable; future `requested_at` values also need the brief's nonnegative invariant, which is explicitly covered in `tools/mission-control/test_gate_latency.py` for the existing UI path.
3. **Low — there is no in-repo consumer exercising the expanded status contract.** Grep found only CLI documentation, the status implementation, and its tests. `tools/azure-runner/chat_service.py` and Mission Control read their own database snapshots, while `docs/DECISIONS.md` describes Slack as a later front end. The focused status tests are therefore the only current compatibility guard for the new keys.

## Conventions

- Focused test command, quoted from `tools/azure-runner/test_status_json.py`: `python3 -m unittest test_status_json -v` (run in `tools/azure-runner`).
- CLI usage, quoted from `tools/azure-runner/README.md`: `python pipeline.py status --json`; plain `python pipeline.py status` keeps the human-readable table.
- Tests in this area are stdlib `unittest` tests with no live database; async command calls use `asyncio.run` and a fake connection (`tools/azure-runner/test_status_json.py`).
- Console output remains plain ASCII for Windows consoles, as documented beside `cmd_status()` in `tools/azure-runner/pipeline.py`.
- Timestamp serialization currently uses `datetime.isoformat()` on timezone-aware database values (`tools/azure-runner/pipeline.py` and `tools/azure-runner/test_status_json.py`).
- The status command currently performs exactly two reads, and the focused test asserts that count (`tools/azure-runner/pipeline.py`, `tools/azure-runner/test_status_json.py`).

## Likely files

- `tools/azure-runner/pipeline.py` — owns the selected columns, JSON shaper, clock imports, and unchanged human renderer.
- `tools/azure-runner/test_status_json.py` — owns fixture rows, exact nested key assertions, query assertions, JSON-only behavior, and byte-exact human-output coverage.
- `tools/azure-runner/README.md` — owns the existing status JSON contract paragraph beside the CLI command.

`tools/azure-runner/schema.sql` is an inspected dependency rather than a likely edit: all requested columns and their types already exist, and the brief excludes schema changes.
