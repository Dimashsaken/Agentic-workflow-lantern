# Proposed work order: isolation, recovery and evidence

Date: 2026-09-10. **HITL: required — plan and recovery schema approval pending.**
This extends the user-authorized continuation work; it does not authorize a live
pipeline transition. Parent session owns current-baseline verification and fixes.

## Proposed acceptance criteria

- **AC-7:** Real worker-shell and MCP probes cannot modify controller harness or
  gate authority, access controller credentials or other executions, or reach
  unapproved network destinations. Normal scoped coding and recorded QA still work.
- **AC-8:** Normal, failed and killed executions retain redacted durable diagnostics
  and known usage. Real Postgres tests prove lease renewal, expiry, two competing
  dispatchers, stale child rejection and no stale run advancement.
- **AC-9:** Restart reconciles known publication effects; duplicate attempts do not
  create duplicate logical effects. Ambiguous effects hold explicitly. Human gates
  and Azure provider choice survive all recovery paths unchanged.
- **AC-10:** A trusted manifest binds each claimed test/video result to run,
  execution, exact tested revision, command/test identifier, outcome and artifact
  hash. Requirement links identify executed tests. Wrong revision, stale execution,
  changed media, invalid decode and fabricated worker records fail verification.
- **AC-11:** Mission Control shows provenance and legacy/unverified limits accurately;
  recorded browser QA, independent validation/security review, and actual Azure,
  Postgres and image evidence are distinct from local unit results.
- **AC-12:** Context-budget and structured-output experiments are deferred until a
  verified live baseline exists; any experiment retains the SDK version bounds,
  fixed pipeline and human gates, with measured quality/cost before rollout.

These criteria have not been inserted into an approved story. The typed proposal
is not a valid substitute for that missing story or a registered plan signoff.

## Ordered increments

Each row is at most half a developer day; split further if evidence changes that
estimate. All runtime tasks depend on approval of this proposed work order.

| Task | Size | Dependency and approval | Owned implementation scope | Reviewable result |
|---|---|---|---|---|
| 1. Finish baseline validation and honest blockers | M | Already requested; no new schema | Current coding/QA records, existing relevant regressions | Azure/Postgres/image/browser outcomes identified by actual environment and revision |
| 2. Freeze controller/worker and evidence contracts | S | Plan + defensive security pre-review | This plan; approved decisions | Mounts, identities, request types, provenance fields and network policy finalized |
| 3. Isolate shell/MCP execution and immutable harness | M | 2; no schema | `pipeline.py`, `orchestrator.py`, sandbox entrypoint/Dockerfile, coding-stage tests | Worker gets only product/output volumes and explicit scoped tool operations |
| 4. Move gate computation and acceptance to host authority | M | 3; no schema | `factory.py`, `pipeline.py`, `review.py`, gate/review tests | Independent fresh checkout, captured policy, process exits; fake worker JSON cannot pass |
| 5. Verify network, credentials, normal coding and cleanup | M | 3-4; no schema | Isolation proof and coding tests | Actual image proves denials plus allowed work; in-process limitations explicit |
| 6. Implement and validate additive migration + rollback | M | 2; **schema approval required** | `schema.sql`, database verification tests | Disposable DB forward/rollback and old-row behavior measured |
| 7. Acquire/renew/fence run and execution ownership | M | 6 | `pipeline.py`, `builders.py`, `review.py`, verification/builder/review tests | Two dispatchers and parallel children cannot overwrite newer ownership |
| 8. Persist events and reconcile interrupted executions | M | 7 | `factory.py`, `orchestrator.py`, `pipeline.py`, journal/verification tests | Kill/restart retains flushed diagnostics; no automatic mid-tool replay |
| 9. Fence/reconcile publication intents | M | 7-8 | `pipeline.py`, `review.py`, coding/review tests | Duplicate-effect and ambiguous-outcome controls; human approvals unchanged |
| 10. Produce and verify execution manifests | M | 4; no schema for manifest storage | `evidence.py`, `factory.py`, `pipeline.py`, evidence/gate tests | Host manifest with version, run/execution, harness/image/policy hashes, exact code SHA, artifact hashes, test IDs/results and source capture |
| 11. Bind requirement tests and video provenance | M | 10; strict recovery integration also depends 7 | `evidence.py`, `orchestrator.py`, video proof, evidence tests | Positive/negative controls; decoded duration/stream and capture identity verified |
| 12. Present provenance with recorded browser QA | M | 11 | Traceability view/tests; run QA records | Revision/execution/test links and legacy limits visible in real browser recording |
| 13. Integrate, review and prepare rollout | M | 5,9,12 | Existing docs/evals and stage records | Configured quality checks, D20 regeneration, independent reviews, exact remaining blockers |
| 14. Evaluate context budget and structured outputs | M | 13 verified live baseline; separate experiment approval | Deferred | Azure baseline comparison before any prompt/runtime rollout |

Shared runtime files make parallel builders inappropriate for this increment.
Independent read-only reviewers and QA can run alongside coding after contracts
stabilize. No new runtime module names are invented here: if a task needs extraction,
record its exact new file ownership in an amended plan before implementation.

## Schema-independent versus approval-dependent work

Continue task 1 and prepare/review task 2 now. Tasks 3-5 and 10-12 can proceed
after plan approval without applying the recovery migration. Tasks 6-9 require
schema approval before dependent changes. Task 13 cannot assert full recovery
acceptance while those tasks are incomplete. No staged/prod deploy, merge, live
run registration or fabricated approval is authorized by this local plan.

## Evidence contract and controls

Host-generated manifests use a versioned JSON shape: run ID, execution key,
attempt, stage, observed lease identity where available, harness revision, image
digest, product base/head/tree state, captured quality-policy hash, start/end times,
command/test IDs and exit statuses, requirement IDs and artifact path/hash/size.
Video entries include capture session identity and decoded stream/duration facts.
Reject dirty or different tested trees unless the manifest explicitly records an
immutable tree snapshot subsequently used by the verifier. Host hashes alone do
not prove semantic coverage: reviewers still inspect what each test asserts.

Require controls that accept known-valid evidence and reject swapped execution,
swapped revision, modified artifact, wrong command outcome and missing coverage
links. Fail-to-pass tests are appropriate for regression-specific acceptance;
invariant tests that should pass before and after need separately labeled controls.
Do not require every infrastructure invariant to fail on the old revision.

## Definition of code complete

- User-approved plan and schema recorded through the existing mechanisms.
- Existing AC-1 through AC-6 regressions retained; proposed AC-7 through AC-11
  have criterion-by-criterion evidence, with local/live distinctions.
- Both executor paths, parallel builders, reviewer/regate and babysitter covered.
- Actual image isolation and real Postgres kill/restart/duplicate-effect tests pass.
- Azure end-to-end sequence stops at its real pending human gate.
- Browser recording is playable and bound to tested revision and execution.
- Independent QA, validation and security findings fixed or explicitly held.
- Required eval fingerprint and configured checks pass at each committed snapshot.
- Durable memory uses the actual append tool; no rendered view hand-edit.
- Rollout/rollback and unresolved environment blockers are explicit; no deployment
  or merge claimed without human action.

## Implementation decomposition

The approved local tasks are extracted into execution_leases.py (SQL ownership),
execution_runtime.py (dispatcher contexts), durable_execution.py (SDK diagnostics),
isolated_tools.py and tool_execution.py (worker boundary), evidence_manifest.py and
trusted_evidence.py (controller receipts and quality snapshots), plus directly
associated tests/integration drivers. This decomposition does not alter the fixed
pipeline or grant live approvals. Operational pilot limits and rollback are in
docs/EXECUTION-ISOLATION.md.
