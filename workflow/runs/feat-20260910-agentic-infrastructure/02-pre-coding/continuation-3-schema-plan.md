# Continuation 3 schema plan

No schema change is needed.

Date: 2026-09-10. Inspected `schema.sql` at `a64c229`. This proposal reuses the
lease columns and `execution_effects` table already implemented under the earlier
local approval. It does not approve applying that migration to the configured
database. Any such application, or any later DDL change, is **HITL: required**.

## Existing storage and compatibility

| Existing storage | Proposed use | Compatibility / rollback |
|---|---|---|
| `execution_effects.operation_key`, `request_sha256`, `result` | Separate versioned branch-update and PR-create intents; store the nonsecret canonical request in `result` from intent creation, then provider observations alongside it | Preserve old keys and hashes. Old aggregate rows without full requests stay held unless a controller reconstructs the original request and proves its hash matches. Never reinterpret an old confirmed branch-only result as a confirmed PR. No backfill invents observations. |
| `stage_executions.lease_*`, `input`, `output` | Dedicated `03-coding.babysit` maintenance attempts, with target, approval identity and observed revision binding in `input`; fenced observations/outcomes in `output` | New maintenance lease validator is distinct from stage-dispatch validation. No new status enum and no `runs.status` or approval rewrite to make maintenance fit the old predicate. Old executors remain unable to run this mode. |
| `artifacts.sha256`, `artifacts.metadata`, `stage_executions.output` | Versioned QA capture receipt: execution, recording identity, approved target policy, deployment observation, requirements and media digest | Existing receipts remain version 1 and retain their original meaning. New fields are required only for the new QA receipt version; legacy recordings are unverified, not upgraded. |
| `events.data` | Maintenance claim/recovery/hold records and retention dry-run/quarantine/delete audit | Append only. Never delete events, effects, approvals or stage rows as checkout cleanup. |

No migration, rollback SQL, index, constraint change, production-sized DDL timing
or data backfill is required for this increment. Existing indexes on run/stage,
running-stage lease expiry and effect run/time support the proposed pilot queries;
measure query plans before sustained operation rather than asserting production
performance from small tests. If a new index is needed, return with measured
evidence and forward/rollback DDL for human approval.

Maintenance acquisition serializes on the existing run row, rechecks the latest
applicable human `code_complete` decision and destination, and inserts one fresh
execution only if no active maintenance/stage owner conflicts. Renewal and writes
use server time and the exact execution ID/owner/fence. A new attempt never
resurrects an old execution. Dispatch must honor the same mutual-exclusion check;
checking only in babysitting leaves a race. Expired maintenance is held and
reconciled without changing the run's stage or pending gate.

Rollback is a coordinated code/flag rollback: stop the new maintenance and QA
dispatch, join or explicitly fence workers, inspect uncertain effects, retain all
ledger/receipt data, and disable the new modes. Do not return uncertain effects to
the old force-push path. Keep the prior isolated offline worker path available.

Filesystem retention records live under controller authority outside worker
mounts. They are not a substitute for the database ownership check. Versioned
ownership descriptors and retirement tombstones need no table additions; the
shared worker-launch/cleanup lock makes their lifecycle enforceable.
