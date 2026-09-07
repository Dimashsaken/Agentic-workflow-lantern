# Task plan — feat-20260907-status-json

## Structure and constraints

Use `tools/azure-runner/pipeline.py` for the pure shaper, status query/render branch, argparse flag, and dispatch. Follow the fake async database style in `tools/mission-control/test_gate_latency.py`; place the focused test in `tools/azure-runner/test_status_json.py`. No new dependencies, queries, schema, endpoints, or files beyond the three paths authorized by the brief.

## Ordered tasks

### 1. Lock the status contract with behavior tests — S (≤2h)

**Dependencies:** none  
**HITL:** not required

Create `tools/azure-runner/test_status_json.py` using stdlib `unittest`, `asyncio`, `contextlib.redirect_stdout`, and fake connection rows.

Cover:
- pure shaping returns exactly the required top-level and nested keys;
- `updated_at` and `requested_at` use `datetime.isoformat()` and preserve UTC offsets;
- nullable `product_repo` stays JSON `null` and `coding_mode` is retained;
- empty inputs produce `{ "runs": [], "pending_gates": [] }`;
- JSON mode issues exactly the same two fetches, with `product_repo` included in the runs SELECT and no additional query;
- stdout is one parseable JSON object with no table text;
- non-JSON output for representative rows and empty runs matches the current strings exactly, including spacing, timestamp minute format, `[auto-coding]`, and pending-gate line.

**Reviewable state:** failing tests precisely describe the new output and freeze old output.

### 2. Implement shaping and CLI dispatch — S (≤2h)

**Dependencies:** task 1  
**HITL:** not required

In `tools/azure-runner/pipeline.py`:
- add a pure helper accepting run rows and pending-gate rows and returning the required dict;
- call `.isoformat()` directly on each timestamp;
- extend the existing runs SELECT only with `product_repo`;
- retain the existing pending-gates query unchanged;
- change `cmd_status` to accept a JSON-mode boolean;
- in JSON mode print exactly one `json.dumps(payload)` result;
- otherwise execute the existing human-rendering block without textual changes;
- add `--json` (`store_true`) to the existing status parser and pass it through dispatch.

Run `python -m unittest test_status_json -v` from `tools/azure-runner` (or the repository's equivalent interpreter). Also run the existing focused Azure-runner tests that import `pipeline.py`, at minimum `test_coding_stage.py`, to catch import/dispatch regressions.

**Reviewable state:** implementation and tests pass; no unrelated diff.

### 3. Document and self-review — XS (≤1h)

**Dependencies:** task 2  
**HITL:** not required

Add one paragraph in `tools/azure-runner/README.md` under “The pipeline runner,” next to the existing status line. Include the command and name the two top-level arrays; avoid promising filtering or stability beyond the brief.

Self-review the full diff for:
- only `pipeline.py`, `test_status_json.py`, and README changed;
- exactly two status queries remain;
- legacy rendering statements are byte-identical;
- no new dependency or schema edit;
- plain ASCII console output;
- all tests pass.

**Reviewable state:** docs and final verification commit.

## Coding principles most at risk

1. **Test behavior, not implementation detail:** assert the public JSON shape and exact legacy stdout; inspect SQL only for the explicit two-query/product-field contract.
2. **Boring over clever:** one small helper and one explicit mode branch; no serializer abstraction or generic output framework.
3. **One task, one commit:** keep tests, implementation, and documentation in 2–3 small commits as requested; record any deviation in `03-coding/report.md`.

## HITL decision

No implementation task requires special HITL review. There is no schema migration, package addition, architecture change, or irreversible operation. The normal `plan_signoff` and later `code_complete` human gates remain mandatory.

## Definition of code-complete

- [ ] `python pipeline.py status --json` emits exactly one valid JSON object.
- [ ] The object has exactly `runs` and `pending_gates`, with the requested nested keys.
- [ ] All timestamps are produced by `datetime.isoformat()` and retain UTC offset information.
- [ ] Status still uses exactly two database queries; only the runs SELECT gains `product_repo`.
- [ ] `python pipeline.py status` output is byte-for-byte unchanged for empty, human-mode, auto-mode, and pending-gate cases.
- [ ] `tools/azure-runner/test_status_json.py` passes without a database or Azure credentials.
- [ ] Existing focused Azure-runner tests importing `pipeline.py` still pass.
- [ ] README documents the flag beside the existing status command.
- [ ] Only the three brief-authorized paths changed; no package or schema changes.
- [ ] Commits reference `feat-20260907-status-json`, and deviations are recorded in the coding report.
