# Proposed schema and recovery contract

The user authorized this local forward/rollback contract through the subsequent
"continue" instruction (see 03-coding/report.md). Migration and rollback have now
been implemented and exercised only on disposable PostgreSQL. **HITL: required**
for application to a registered/live environment; no approval row is fabricated.

## Schema-free work

Isolation configuration, worker/controller separation, immutable gate files,
incremental filesystem diagnostics and evidence verification need no table change.
Existing `artifacts.sha256` plus `artifacts.metadata` can bind a versioned manifest
to an execution, source revision and test identifiers. That JSON contract still
needs plan approval. Do not invent provenance for historical artifacts.

## Additive migration proposal

1. Add nullable `lease_owner text` and `lease_expires_at timestamptz`, and
   `lease_fence bigint NOT NULL DEFAULT 0`, to `runs`. This is dispatcher ownership.
2. Add the same three fields to `stage_executions`. Execution renewals also update
   existing `heartbeat_at`. Persist parent run fence in execution `input` metadata;
   validation requires it, never trusts a caller-supplied value alone.
3. Add `execution_effects`: `operation_key text PRIMARY KEY`,
   `run_id text NOT NULL REFERENCES runs(id)`,
   `stage_execution_id bigint NOT NULL REFERENCES stage_executions(id)`,
   `lease_fence bigint NOT NULL`, `kind text NOT NULL`,
   `request_sha256 text NOT NULL`, `status text NOT NULL`,
   `external_ref text`, `result jsonb`, `created_at timestamptz NOT NULL DEFAULT now()`,
   `updated_at timestamptz NOT NULL DEFAULT now()`.
   Allowed statuses: `intended`, `confirmed`, `uncertain`. Operation keys identify
   a logical publication target/revision independent of attempt, preventing a retry
   from treating the same operation as new. Reusing a key with different request
   hash fails. Results contain no credentials.
4. Add partial expiry indexes on `runs(lease_expires_at)` where status is
   `executing`, and `stage_executions(lease_expires_at)` where status is `running`.
   Add `execution_effects(run_id, created_at)` for recovery inspection.

Use PostgreSQL server time for renewal and expiry. Suggested initial TTL: 120
seconds, renewal every 20 seconds on a dedicated connection; these are configurable
operational defaults, not tests that rely on wall-clock sleeps. Acquisition and
takeover increment the fence atomically. Every completion/advance/publish mutation
compares owner, fence, unexpired lease and expected status in the same transaction.
Lease loss cancels local work and prevents accepting any subsequent outputs.

## Safe restart semantics

A sweeper marks an expired attempt interrupted/failed with redacted diagnostics and
retains its artifacts; it does not silently make old writes authoritative. Only
read-only work or work whose effects can be reconciled can start a new attempt.
Pending human gates remain pending and are never replayed or auto-approved.
Before branch push/PR creation, the host records intent after checking fences.
After process death it inspects the actual target revision or PR identity and
confirms an already-performed operation. If the outcome cannot be established,
record `uncertain` and hold for a person. A database lease cannot make an external
API exactly-once; use provider idempotency or conditional ref updates where
available, and do not claim stronger guarantees for arbitrary MCP services.

Existing SDK `run_state` fields are not a safe resumption implementation. Do not
enable mid-tool replay. Fresh attempts get explicit recovery context with durable
event boundaries; preserving partial usage means retaining known values and marking
unknown tail usage incomplete. SDK resume is a later, live-tested change bound to
SDK/prompt/tool-schema/product revision versions.

## Migration rollout, duration and rollback

Drain dispatchers and wait for active workers or terminate them explicitly before
activation. Inventory row counts, active leases, database version and duplicate
operation targets on a disposable copy first. Nullable additions/default zero
require no semantic backfill: completed rows retain fence zero; pending gates retain
their current approvals. Old active rows with no lease are held for explicit
reconciliation, never assigned fabricated ownership. Rows created mid-rollout are
possible only while old workers run, so mixed old/new dispatchers are unsupported.

Use a bounded lock timeout and statement timeout. Build expiry indexes concurrently
outside a transaction if measured table size makes blocking builds unacceptable.
Estimated runtime is **unmeasured** until disposable data and production-sized row
counts are available; do not promise a duration from unit tests. Record DDL lock
wait, index duration and rollback duration in integration evidence.

Rollback: stop new dispatch and workers; reconcile uncertain effects; export the
effect ledger and execution diagnostics; revert runtime; drop new indexes, then
the new ledger table and lease columns in reverse order only after human approval
of the data removal. Prefer retaining additive columns/table during a runtime
rollback, because dropping the ledger destroys deduplication evidence. Restoring
old startup recovery with in-flight new executions is unsupported.

No approvals table changes, no gate bypass and no production migration are part
of this proposal's preparation.

## Reviewable SQL proposal (not executed)

Run only against a disposable database after schema approval. Indexes below use
ordinary creation for that small database; production uses the measured rollout
choice above. The runtime activation is a separate step after integration passes.

```sql
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
ALTER TABLE runs
  ADD COLUMN IF NOT EXISTS lease_owner text,
  ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS lease_fence bigint NOT NULL DEFAULT 0;
ALTER TABLE stage_executions
  ADD COLUMN IF NOT EXISTS lease_owner text,
  ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS lease_fence bigint NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS execution_effects (
  operation_key text PRIMARY KEY,
  run_id text NOT NULL REFERENCES runs(id),
  stage_execution_id bigint NOT NULL REFERENCES stage_executions(id),
  lease_fence bigint NOT NULL,
  kind text NOT NULL,
  request_sha256 text NOT NULL,
  status text NOT NULL CHECK (status IN ('intended', 'confirmed', 'uncertain')),
  external_ref text,
  result jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_runs_active_lease
  ON runs(lease_expires_at) WHERE status = 'executing';
CREATE INDEX IF NOT EXISTS idx_stage_active_lease
  ON stage_executions(lease_expires_at) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS idx_execution_effects_run
  ON execution_effects(run_id, created_at);
COMMIT;
```

Destructive rollback SQL is for the disposable proof, or a separately authorized
rollback after draining workers and exporting/reconciling the effect ledger:

```sql
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
DROP INDEX IF EXISTS idx_execution_effects_run;
DROP INDEX IF EXISTS idx_stage_active_lease;
DROP INDEX IF EXISTS idx_runs_active_lease;
DROP TABLE IF EXISTS execution_effects;
ALTER TABLE stage_executions
  DROP COLUMN IF EXISTS lease_owner,
  DROP COLUMN IF EXISTS lease_expires_at,
  DROP COLUMN IF EXISTS lease_fence;
ALTER TABLE runs
  DROP COLUMN IF EXISTS lease_owner,
  DROP COLUMN IF EXISTS lease_expires_at,
  DROP COLUMN IF EXISTS lease_fence;
COMMIT;
```
