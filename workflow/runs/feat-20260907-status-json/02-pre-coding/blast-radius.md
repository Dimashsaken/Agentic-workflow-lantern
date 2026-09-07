# Blast radius — feat-20260907-status-json

## Overall assessment

**Risk: low.** This is a bounded CLI-output addition with no schema, auth, payment, deletion, job, event, or external-integration change. The main compatibility risk is accidentally changing the existing human-readable `status` output while adding the JSON branch.

## Runtime flow and consumers traced

`tools/azure-runner/pipeline.py` owns argument parsing, dispatch, both status queries, and console rendering. The `status` command is mentioned in `tools/azure-runner/README.md` and `docs/ORCHESTRATION.md`; no code caller of `cmd_status` exists, and grep found only the function and its dispatch site. Database fields are defined in `tools/azure-runner/schema.sql`; `coding_mode` and `product_repo` already exist. No cron, event listener, HTTP endpoint, Mission Control, or chat code calls this command.

## Touched paths

| Path | Action | Why | Risk |
|---|---|---|---|
| `tools/azure-runner/pipeline.py` | modify | Add `--json`, extend the existing active-runs SELECT with `product_repo`, shape rows in a pure helper, emit one JSON object, and preserve the current table branch exactly | medium |
| `tools/azure-runner/test_status_json.py` | create | Stdlib behavior tests with fake connection/pool rows; cover shape, ISO timestamps, exact query count/fields, valid single-object stdout, and legacy output regression | low |
| `tools/azure-runner/README.md` | modify | Document `python pipeline.py status --json` beside the existing status command | low |

## Read-only evidence / exemplars opened

| Path | Why examined |
|---|---|
| `tools/azure-runner/schema.sql` | Verified both requested fields already exist and timestamps are `timestamptz` |
| `tools/mission-control/test_gate_latency.py` | Exemplar for stdlib tests and fake async database objects |
| `tools/azure-runner/test_coding_stage.py` | Exemplar for importing sibling `pipeline.py` and focused no-database tests |
| `tools/azure-runner/test_verification.py` | Confirmed local test conventions and async test execution |
| `AGENTS.md` | Product conventions and pipeline contract |
| `README.md` | Product orientation and documented entry points |

## Consumer and compatibility analysis

- `product_git grep` found no caller besides `main()` dispatching `cmd_status`; changing its signature to accept a boolean is contained.
- Human consumers include documentation and shell usage. Keep the existing `if not runs`, run-row format, auto-coding tag, pending-gate format, ordering, and spacing byte-for-byte in the non-JSON branch.
- JSON consumers are new. Contract keys must be exact: top-level `runs`, `pending_gates`; run keys `id`, `status`, `current_stage`, `updated_at`, `coding_mode`, `product_repo`; gate keys `run_id`, `gate`, `requested_at`.
- Preserve database ordering: active runs retain `ORDER BY updated_at DESC`; pending gates currently have no declared ordering, so do not introduce sorting beyond the same query result order.
- Keep stdout clean in JSON mode: exactly one `json.dumps(...)` print; connection lifecycle must still close before return.

## Coverage and task-order impact

There is no existing dedicated status-command test, so behavior tests come first. The new tests must lock legacy rendering before implementation and test the pure shaper independently. Existing `test_coding_stage.py` imports `pipeline.py`, so avoid import-time behavior changes.

## Code structure

- Put a small pure row-shaping helper next to `cmd_status` in `tools/azure-runner/pipeline.py`.
- Keep the same two queries in `cmd_status`; pass fetched rows to the helper only for JSON mode.
- Follow the fake async object style in `tools/mission-control/test_gate_latency.py`, narrowed to `fetch()` and `close()`.
- Parse `--json` on the existing status subparser and pass it through the existing `match` dispatch.

## Package decision

No new package. Use the already-imported stdlib `json` module and stdlib `unittest`. Package sign-off is not required.

## Security / architecture

No security pre-review is needed: the output exposes only fields already available to operators through the status command/configured database, and the change does not touch auth, payments, or deletion. No architectural change is required.
