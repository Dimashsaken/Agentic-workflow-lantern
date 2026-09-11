# Stage Report: 05-post-coding — feat-20260910-agentic-infrastructure

- **Agent/author:** independent post-coding reviewer; subsequently assigned bounded lifecycle fixes
- **Date:** 2026-09-10
- **Status:** BLOCKED (formal pipeline review); provisional local review completed

## Summary

Reviewed the full implementation diff from main to `90e4fb6`, then verified the bounded executor lifecycle corrections in the updated working-tree diff. Three local findings are resolved with regression evidence. This is a local engineering review, not a registered fleet execution, independent validation signoff, or authorization to advance beyond QA.

## Work performed

Read role charter, skills and memory; AGENTS.md; runboard; implementation and continuation plans; D23/D24; architecture assessment; orchestration/capability contracts; coding and QA reports. Compared policy, Git grammar, quality gates, evidence resolution, execution journal, executors, review integration, Mission Control rendering, role instructions and eval changes against AC-1 through AC-6 in `docs/plans/agentic-infrastructure.md`.

The baseline run has no `00-story/story.json`, approved `02-pre-coding/plan.json`, baseline task-plan/blast-radius documents, or `03-coding/handoff.json`. The continuation plan is not a substitute for those formal artifacts. `validation.md` therefore records a local criterion assessment instead of fabricating a passing typed fleet validation envelope.

Executed independent lifecycle probes using Python 3.12.10, openai-agents 0.22.0 and MCP 2.0.0. The MCP control starts a disposable local stdio server using the actual installed client library; executor setup and failure probes inject database/model boundaries. These probes make no Azure requests and do not exercise Docker or real Postgres. An initial probe attempted the removed `mcp.server.fastmcp` import and failed before connecting; it was corrected to the installed MCP 2.0 low-level server API before the recorded before/after results.

## Findings / results

Line references below identify the corrected working tree; original failure sites are also given against `90e4fb6`.

| ID | Area | Severity | Tag | Evidence and resolution |
|---|---|---|---|---|
| R-1 | Setup resource lifecycle | major | fix-now — resolved | At `90e4fb6`, `pipeline.py:541-563` and `orchestrator.py:1795-1818` perform session/input/MCP setup before the cleanup boundary. `lifecycle-probes-before.txt:5` records writable coding state remaining after rejected inputs; line 10 records zero database closes and MCP cleanups after connect failure. The outer boundary now begins at `pipeline.py:515` / `orchestrator.py:1798`; `lifecycle-probes-after.txt` records null writable/branch state and one database close plus one MCP cleanup. Regression tests: `test_execution_journal.py:44`, `:57`, `:94`. |
| R-2 | Failure masking and cleanup completion | major | fix-now — resolved | At `90e4fb6`, `pipeline.py:608-618` lets failed usage persistence replace a model failure and uses gather without collecting all cleanup outcomes. Updated `pipeline.py:613-637` retains the primary error, awaits all cleanup results, reports cleanup errors safely, and clears all product execution state. `orchestrator.py:1887` likewise awaits cleanup results while preserving the primary execution failure. `test_execution_journal.py:70` proves the MaxTurnsExceeded error and 200 known input tokens survive ledger failure; `:132` proves cleanup failure is journaled and cannot mark success. |
| R-3 | Missing postcondition diagnostics | moderate | fix-now — resolved | At `90e4fb6`, `pipeline.py:622-626` checks finalization/postconditions after the journal exception handler; the trace can describe completed turns without the execution's actual failure. Checks now run inside the journal boundary at `pipeline.py:603-607`. `test_execution_journal.py:82` proves a missing-memory postcondition appears in the trace, preserves 75 known input tokens and never writes succeeded. `:112` verifies the ordinary success path records success only after MCP cleanup. |

All three fix-now resolutions were verified in the updated source diff and the executed tests. No debt-ticket or waiver was created. The suspected task-ownership problem with parallel MCP cleanup was **not reproduced**: the real installed SDK/MCP stdio control passed both sequential and parallel cleanup without captured exit-stack errors. It is not a finding.

`journal-retest.txt:17` records **14 tests passed**: the original seven tests remain and seven lifecycle regressions were added to the already configured suite. `git diff --check` passed after these changes. These bounded checks are not a new complete repository test run; the integrator owns the final full gate, eval regeneration and tested-source snapshot after concurrent work finishes.

## Compatibility and scope

No schema or approval behavior changed in the lifecycle correction. Azure OpenAI and the existing stage graph remain intact. Automatic coding's requirement for configured tests and fingerprinted gates is an intentional compatibility break documented in D24: deploy host and sandbox versions together. Legacy evidence prose remains readable in Mission Control, but new validator executions require resolvable references. Validation of deleted files remains file-level, with a null line, and review lines resolve against the committed handoff revision.

The original acceptance criteria explicitly distinguish file-tool policy from OS containment and resolvable references from truth/provenance. This review does not upgrade either claim. Shell/MCP containment, scoped credentials, renewal/fencing, hard-kill telemetry, execution-linked evidence and live sequence behavior remain subjects of the continuation increment. No finding here certifies those future implementations.

## Artifacts

- `validation.md` — local AC-1 through AC-6 evidence ledger and confidence limits.
- `lifecycle-probes.py` — independent setup and real local MCP cleanup controls.
- `lifecycle-probes-before.txt`, `lifecycle-probes-after.txt` — exact observed results.
- `journal-retest.txt` — 14-test regression log.

## Handoff notes for the next stage

The initial review was independent of the implementation author; the integrator subsequently assigned the three bounded lifecycle corrections to this reviewer. Consequently the corrections have automated regression verification but still need another reviewer's final assessment. Review against the final committed source, final full-suite/eval evidence and completed QA artifacts before any formal stage transition.

The parent integrator is collecting live Azure/Postgres/Docker evidence and the QA role is recording browser behavior. This report does not adopt their in-progress results as completed or independently verified evidence. No commit, merge, deployment, fleet approval or database execution row was created by this reviewer.

## Open questions

Which registered execution and approved intent artifacts should own formal stage-5 verification after the required dev QA completes?

## Memory candidates

2026-09-10: Exercise stage setup and teardown separately from model failures; a finally block beginning after MCP connect cannot clean partially initialized resources, and success must be recorded only after cleanup and usage bookkeeping.

This candidate was sent to the parent integrator for the actual `append_memory` path. This local review has no execution-bound append tool and claims no memory insertion; the rendered role memory was not edited.

Status: BLOCKED

## Independent continuation review — increment 2, 2026-09-10

Reviewer: `postcoding_increment2`, independent from the implementation owners.
Scope: the full working-tree diff against `main`, including the prior `7f01faa`
work and the continuation's uncommitted changes. This pass concentrates on lease,
execution, failure/cleanup and publication compatibility; it consumes the earlier
stage-5 findings above and does not repeat the concurrent security review's
transient-source evidence investigation. No deployment, approval, live pipeline
transition or production data mutation was performed.

### Findings and verified resolutions

| ID | Area | Severity | Tag | Evidence and resolution |
|---|---|---|---|---|
| R-4 | Alternate babysitter entry points | major | fix-now — resolved | Suppressing the daemon tick did not stop direct `babysit_run` / CLI entry from reaching merge/push without a lease. An injected control with leases enabled reached `deps.product` once before correction. `review.py:723` now rejects at the common entry point before product I/O. The after-control observes zero calls with leases enabled and normal delegation with the flag disabled. `test_recovery_acceptance.py` retains the rejection control. |
| R-5 | Legacy Docker with lease mode | major | fix-now — resolved | The Docker wrapper allowed leases alone, while the container lacked the controller's ownership context and its cancellation branch only killed on wall-clock timeout. The before-control delegated to the Docker body once with leases enabled. `pipeline.py:742` now rejects this unsupported combination before launch. The after-control proves rejection and preserves flag-disabled Docker delegation. This is an explicit compatibility hold, not a claim that legacy Docker acquired fenced memory or crash diagnostics. |
| R-6 | Artifact child ownership | major | fix-now — resolved | `insert_artifact` originally checked only the parent fence, permitting an expired child under a current parent to insert attributed artifacts. `pipeline.py:424` now selects the child fence for child-bound calls and checks the stored execution's stage directory before INSERT. Independent controls require the exact child handle, accept its correct stage and refuse another stage before writing. Recovery acceptance tests retain the control. |
| R-7 | Premature durable success | moderate | fix-now — resolved | `durable.finish(True)` originally preceded MCP cleanup and final database completion. A later cleanup failure could therefore leave an apparently successful terminal diagnostic. `pipeline.py:734` now writes success only after cleanup and the fenced database completion. The reviewer added two regressions at `test_execution_journal.py:148` and `:165`: a cleanup failure retains incomplete diagnostics without a success claim; normal ordering is cleanup, database success, then durable success. Late failures may have incomplete diagnostics; the database remains authoritative. |
| R-8 | Per-attempt checkout retention | moderate | debt-ticket | `product_checkout` now allocates a unique checkout per execution and refuses to replace it, correctly protecting surviving worker mounts. Normal completion and recovery remove workers but retain these checkout directories. Repeated attempts can consume disk indefinitely. Local ticket **LANTERN-DEBT-EXECUTION-GC**, defined below, tracks bounded retention without deleting live mounts or evidence. |

All four fix-now resolutions were verified in the updated source and executed
controls. The reviewer changed only the two focused journal regressions and this
report; the implementation owner made the fixes. No fix-now finding was waived.

### Executed verification and source identity

Independent checks on this working tree:

- `test_execution_runtime.py`: **28 passed** (2.784 seconds on the final review rerun).
- `test_durable_execution.py`: **4 passed** (2.155 seconds).
- `test_execution_journal.py`: **16 passed** (8.482 seconds), including the two new lifecycle regressions.
- `test_recovery_acceptance.py`: **6 passed** (1.561 seconds).
- Inline injected controls: leased babysit rejected before product I/O; leased Docker rejected before body/launch; both legacy delegations preserved; child artifact fence selected; wrong stage refused before INSERT.

These are local regression controls with mocked provider/database boundaries,
except the existing durable suite's real local subprocess-death fixture. They are
not new Azure, Docker, Postgres or browser validation. The observed source hashes
at this review boundary are:

| File | SHA-256 |
|---|---|
| `tools/azure-runner/pipeline.py` | `d40e7b1683a6185186fed8815422c4854bff03b6c1209f5e1632b129620ca099` |
| `tools/azure-runner/review.py` | `8c7da99febefd9a6670b88867a12cd88ebdaca50a89f2dd4d0f3b6c3cb2c6299` |
| `tools/azure-runner/execution_runtime.py` | `e9344d7e1862f26b96097620fc77751fd130fd216ae2412cda0630816efd5783` |
| `tools/azure-runner/execution_leases.py` | `45719ccdf522284eed7434159b6db464b5730b4787b7edc50157cf5d947083e9` |
| `tools/azure-runner/durable_execution.py` | `b966e50160b99b6adbd0b6e560a27a0d45b04d32c13b6ff2b573fbb6bdbc6caf` |
| `tools/azure-runner/test_execution_journal.py` | `1583819568f660bef632bd9516adbdF8521ce823c4712ff681f45281f2d30758` |

The integrator must regenerate evals and run the final complete gate after all
concurrent fixes. Subsequent source hashes supersede this snapshot; prior live
records must retain their original tested hashes.

### Compatibility, intent and remaining acceptance limits

The additive nullable ownership columns, zero fence defaults and new effects table
permit old code to read existing rows with the forward schema present. Enabling
leases requires draining old dispatchers: mixed versions can otherwise bypass the
new protocol. Blanket startup requeue has been removed even with flags disabled;
operators must explicitly reconcile/retry interrupted legacy work. Host stages are
serialized to protect remaining process-global product context, so configured
in-process builder concurrency does not imply simultaneous model execution.

Lease-enabled babysitting and legacy Docker are now held explicitly. Existing
flag-disabled paths remain available. Publication intents prevent automatic
reinvocation of an ambiguous effect, but a local ledger cannot revoke an external
request already in flight. Actual GitHub reconciliation, constrained external
browser access, and complete leased review/regate/babysitter acceptance remain
unfinished; this review does not declare AC-7 through AC-11 fully accepted. The
plan's new module ownership, flag documentation and rollout/rollback package need
the integrator's final update before rollout.

The reviewer inspected `live-controller-recovery.json`, which records one real
Azure response totaling **8,111 tokens** before controller death and Postgres
recovery holding the run with no SDK replay. `lease-recovery-integration.json`
records real PostgreSQL 16.15 disposable migration/rollback, competing owners,
parallel connections and local external-effect reconciliation. These are evidence
produced by the integration owner, not independently rerun by this reviewer, and
neither demonstrates live GitHub reconciliation. Security's source-evidence finding
and final QA/provenance recordings are separate review gates.

### Local debt ticket: LANTERN-DEBT-EXECUTION-GC

Owner: runtime maintainer. Priority: before sustained opt-in fleet operation.
Problem: unique execution checkout directories accumulate after every attempt.
Acceptance: configurable retention; cleanup eligibility requires a terminal DB
execution and confirmation that no labeled worker still mounts the path; resolved
absolute paths must remain under the configured checkout root; preserve evidence
retention separately; test normal completion, killed worker, active lease, stale
cleanup request, and concurrent replacement. Expose disk/retained-attempt counts.
No checkout was deleted to address this ticket during review.

### Durable memory and formal status

Candidate for the actual `append_memory` path:

> 2026-09-10: Review optional lifecycle protections at every public entry point,
> including manual commands, and place durable success after resource cleanup and
> authoritative completion; disabling a scheduler path or finishing model turns
> alone does not establish the execution boundary.

Tool discovery exposed no `append_memory` tool to this reviewer. The parent owns
the configured-database connectivity blocker and actual append path. This candidate
is not an insertion, and the rendered memory file was not edited. The local
findings review is complete for the scoped implementation; formal stage-5 signoff
remains unavailable for this unregistered engineering record and incomplete live
acceptance package.

Blocking question retained for the integrator: which reachable configured database
should receive the durable role-memory append through the actual tool?

Status: BLOCKED

## Continuation 3 independent publication review — 2026-09-10

- **Agent/author:** post-coding, independent review agent.
- **Scope:** full branch diff versus `main`, using the prior review sections for
  the foundation already implemented; detailed new review of publication v2,
  ledger/wrapper/gate acceptance, review side effects and flag compatibility.
- **Result:** scoped implementation review PASS-WITH-NOTES after two fix-now
  corrections; complete foundation and formal stage acceptance remain BLOCKED.

Read the role charter, skills and memory, AGENTS, runboard, original and
continuation-3 plans/blast-radius/schema proposals, execution-isolation contract,
and latest coding, QA and security reports. Inspected actual
`codex/agentic-infrastructure` working tree with concurrent changes; preserved
those changes and unrelated `.codex/`. The reviewed source includes the full
diff's parent/child lease paths, stage and artifact acceptance, immutable evidence
boundary, review/builder entry points and UI compatibility. This is a local
engineering review, not a registered validator execution or a human gate decision.

### Findings and verified resolutions

| ID | Area | Severity | Tag | Evidence and resolution |
|---|---|---|---|---|
| C3-R1 | Publication artifacts before target acceptance | major | fix-now — resolved | Initial new strict `_publish_coding_branch` recorded artifacts and `branch_published` before its caller's destination/handoff recheck and effect confirmation. The updated helper only returns the strict payload; the wrapper checks the target, confirms/reconciles the effect and records artifacts in one fenced transaction. `test_execution_runtime.Publication.test_handoff_changes_during_provider_call_emit_no_authoritative_artifacts` passes in the independent 33-test run: changed handoff yields no confirmation or authoritative artifact, and records uncertainty. Duplicate acceptance uses the same transaction ordering. |
| C3-R2 | Unledgered provider review after strict publication | major | fix-now — resolved | Independent `continuation3-probes-before.log` reproduced a GitHub review POST from `_post_review_for` with leases enabled. `review._post_review_for` now omits provider posting in lease mode before any provider call, retaining local review results and human gates. The same three independent probes pass in `continuation3-probes-after.log`; they also prove flag-disabled advisory COMMENT behavior remains and loss of ownership between push and PR creation prevents the second effect. Configured `test_review.py` contains the corresponding refusal regression. |
| C3-R3 | Aggregate partial publication recovery | major acceptance gap | debt-ticket | Created local ticket `LANTERN-DEBT-PUBLICATION-PARTIAL` below. Current v2 still represents branch push plus PR creation as one effect. A crash after branch push with no PR holds safely; it cannot complete the plan A split-operation/quiescence recovery contract. This is outstanding work, not a waiver or full AC-9 acceptance. |
| C3-R4 | Checkout/evidence retention | medium operational debt | debt-ticket | Existing local ticket `LANTERN-DEBT-EXECUTION-GC` remains open. Continuation-3 contract D adds the required shared launch/retirement lock and tombstone; that design still needs human approval and implementation. Unique attempt directories preserve live files but accumulate retained data. No cleanup was attempted. |

Both fix-now resolutions were checked in the updated source and exercised after
the implementation owner's corrections. No finding was downgraded to waived.
The final coding gate additionally re-observes provider state after the possibly
long review loop and checks the target within its run-fenced gate transaction;
the runtime regression proves changed provider state prevents opening the gate.

### Independent checks and source identity

Python 3.12.10 / installed Agents SDK 0.22.1. These are local controls with injected
provider/database boundaries unless explicitly identified as real temporary Git:

| Evidence file | Result |
|---|---|
| `continuation3-publication-tests.log` | 21 passed; mocked GitHub pagination/identity/timeout/replay controls plus actual temporary local Git CAS creation/update/race controls. |
| `continuation3-runtime-tests.log` | 33 passed; injected lease, publication, artifact ordering, changed-target and gate controls. |
| `continuation3-recovery-tests.log` | 8 passed; existing containment/lifecycle regression controls, including temporary local files/Git. |
| `continuation3-review-retest.log` | 36 passed; legacy local Git babysitter, review and new strict provider-post refusal. |
| `continuation3-probes-after.log` | 3 independent controls passed; reproduced refusal regression, legacy advisory COMMENT once, and loss of fence between push and PR creation with read-only partial reconciliation. |

The first direct review-suite invocation had two failures because its existing
`test -f README.md` fixture ran without the Git-for-Windows shell tools on PATH;
`continuation3-review-tests.log` retains that result. Prepending the existing
`C:/Program Files/Git/usr/bin` supplied the fixture's `test` and bash tools; the
unchanged 36-test rerun passed in 11.916 seconds. This was an invocation environment
correction, not a relaxed assertion or changed runtime. `git diff --check` passed.
The integrator owns the final complete configured gate/eval run after source freeze.

| Reviewed file | SHA-256 |
|---|---|
| `tools/azure-runner/github_publication.py` | `2374ac01e3f862102eb77514011c53974bd28f23820335a27af6e6d75cdfdeb8` |
| `tools/azure-runner/pipeline.py` | `2713cbdfd8449c02e79e2b9783bece1154e8f6ccafa66beefc8c3ec7d5629284` |
| `tools/azure-runner/review.py` | `3d99e488fd1c5c4f90c4e8a0dc74a3b0f54fe638d8f07b1267a872bf6526a12b` |
| `tools/azure-runner/execution_leases.py` | `8693d056fd6daa506808bef6425ea9727fa09d40be30eddbb2bc4ac1c4825afd` |
| `tools/azure-runner/test_execution_runtime.py` | `10aa3e3dadfcf7295939d0e7c702ca7ba71e205b16b033ab4a6182aae67bca42` |
| `tools/azure-runner/test_review.py` | `c42287d9697495584fd7672e5dd9c07d65a68ef1f7ed061dfab828b4423c4f7a` |

### External evidence and compatibility limits

Inspected supplied `../03-coding/publication-postgres-proof.json`: real disposable
PostgreSQL at port 55432 and actual controller subprocess kill, six passing
controls, simulated GitHub reads from a durable local file, and unchanged
validation approvals. This reviewer did not independently repeat that database
fixture. It proves persistence/fencing with the stated simulation, not a GitHub
push/PR crash. `../03-coding/github-readonly-validation.json` records actual
GitHub repository/base GET success, absent work ref and a PR-list 403, followed by
the expected hold and zero provider mutations. Positive live GitHub reconciliation
remains unverified with the available token.

QA round 6's four decoded recordings exercise actual app executions 16/17 and
separate positive/negative receipt fixtures. Those UI records do not establish
deployment-bound normal QA capture. Prior Azure/Docker/controller-death evidence
keeps its original tested-source identity; no Azure, Docker, browser or GitHub
write was performed by this reviewer.

New requests bind canonical repository URL/ref, immutable repository ID, captured
base SHA, desired head and expected old remote head. Legacy aggregate intents,
changed destinations, unavailable/malformed reads, moved base/head, closed PRs
and conflicting PRs hold. Confirmed duplicates are observed again. CAS pushes an
immutable SHA and cannot overwrite a concurrently changed ref. No unconditional
force fallback remains in the ordinary publication helper. Flag-disabled PR reuse
is also read-only and identity checked; optional label/comment side effects were
removed there, and a rejected non-fast-forward push now requires inspection.
Flag-disabled branch-only PR-API fallback remains. Operators must account for
these deliberate conservative compatibility changes.

No new schema/package change was introduced in continuation 3. Existing additive
lease schema still requires coordinated activation/rollback and the real human
migration decision; the restored configured database was not migrated. B–D
maintenance authority, external QA transport/capture and safe retention remain
unimplemented pending their explicit architectural decision. Context/output
experiments remain deferred until foundation acceptance. Staging stays NO-GO.

### Local debt ticket: LANTERN-DEBT-PUBLICATION-PARTIAL

Owner: runtime maintainer. Priority: required before declaring AC-9/foundation
acceptance complete. Current safe behavior: one aggregate effect permits
read-only reconciliation of complete provider state and holds partial outcomes.
Acceptance: distinct durable branch and PR intents bound to the same immutable
destination/revision; demonstrate crash after each external effect, duplicate
requests, explicit quiescence/reconciliation before performing only a missing
operation, preserved legacy uncertainty, stale ownership denial and current
provider observation before a gate. Use real disposable PostgreSQL and temporary
Git controls, and label actual GitHub validation separately. Never create approval
rows or replay an ambiguous operation to close this ticket.

### Actual durable learning and handoff

The integrator invoked the actual bound `append_memory` tool on the restored,
populated configured PostgreSQL database. `../03-coding/continuation3-review-memory.json`
records post-coding row **55**, execution key
`manual:feat-20260910-agentic-infrastructure:post-coding:pending-85e73f217eb2`,
unchanged 12 runs / 23 executions / 8 approvals and unchanged approval snapshot.
This is manual engineering memory, not a fabricated fleet stage. The prior
pending post-coding learning was separately restored as row **50**.

Recorded learning: “2026-09-10: Publication receipts, artifacts and success events
must share the final target-and-fence acceptance transaction; provider success
followed by a changed destination must leave a held intent rather than
independently accepted local success evidence.” No rendered memory was hand-edited.

Open question: Do you approve the schema-free local contracts B–D in
`02-pre-coding/continuation-3-task-plan.md`, preserving the existing live rollout
and evidence-deletion gates?

Status: BLOCKED (complete foundation/formal stage); scoped publication review PASS-WITH-NOTES

## Publication v3 split-intent follow-up — 2026-09-11

- **Agent/author:** post-coding, independent reviewer.
- **Scope:** new split-publication increment after checkpoint `da8a9ad`, on the
  same branch with existing changes and unrelated `.codex/` preserved. The full
  versus-main foundation review above remains applicable; this section examines
  the new provider algorithm, production callbacks and ledger compatibility.
- **Result:** PASS-WITH-NOTES for the scoped local v3 implementation. No new
  fix-now finding. Complete foundation/formal stage and staging remain blocked.

### Findings and debt disposition

| ID | Area | Severity | Tag | Evidence and disposition |
|---|---|---|---|---|
| C3-R3 / LANTERN-DEBT-PUBLICATION-PARTIAL | Partial branch/PR recovery | prior major acceptance gap | debt-ticket — local v3 implementation resolved | `publish_split` now obtains separately fenced branch and PR intents before their respective provider mutations. Fresh provider observations may reconcile an existing branch effect; only a previously absent PR action can authorize one new POST. Existing intended/uncertain actions with no observed result hold. The 5 independent callback controls and supplied two real PostgreSQL/process-kill scenarios below verify the previously missing local recovery behavior. Actual GitHub positive validation remains a separate rollout prerequisite. |
| C3-R4 / LANTERN-DEBT-EXECUTION-GC | Checkout/evidence retention | medium operational debt | debt-ticket — open | A read-only inventory is now supplied in `../03-coding/retention-inventory.json`; it holds legacy paths with no execution descriptor/shared retirement lock. Inventory is not cleanup. Approved retention semantics, implementation and race tests remain outstanding under contract D. |

No fix-now finding was waived, and the earlier artifact-ordering and strict
provider-review guards remain in the updated source. V1 and v2 aggregate keys
are explicitly held before creating a v3 parent; no old ambiguous outcome is
reinterpreted as a missing action. New v3 parent confirmation follows both action
receipts. Confirmed parent reuse remains read-only and the final human gate still
requires a fresh provider observation and target check after review.

### Independent verification

`publication-v3-probes.py` calls the actual pipeline `_publish_coding_branch`
callback construction, `execution_leases.begin_effect` and effect confirmation/
reconciliation functions. It injects in-memory SQL storage, fence assertions and
GitHub/Git operations; it is explicitly not real database or provider validation.
All **5 controls passed** in `publication-v3-probes.log`:

- Wrong stored effect kind or canonical request hash is rejected before provider
  mutation, for both branch and PR action keys.
- A lost response after durable PR-intent insertion produces no POST; a later
  attempt sees that intent and holds rather than replaying.
- Stale ownership immediately after push prevents receipt confirmation and the
  creation of a PR intent.
- A changed handoff immediately after push likewise prevents receipt acceptance
  and the next action.
- An observed branch with no PR action creates the missing action once; the next
  invocation re-observes and produces no second external effect.

Independent configured-module reruns: **30 publication tests passed** in 1.918
seconds (`publication-v3-tests.log`) and **36 runtime tests passed** in 4.805
seconds (`publication-v3-runtime-tests.log`). The publication suite retains the
actual temporary Git CAS test alongside simulated provider crash/duplicate tests;
the runtime suite retains changed-target/gate and stale callback controls.
Python 3.12.10 / Agents SDK 0.22.1; `git diff --check` passed. The integrator owns
the final complete configured policy and eval run at the committed snapshot.

| Reviewed source | SHA-256 |
|---|---|
| `tools/azure-runner/github_publication.py` | `d0b0b0d41cdfd74abc924361849a62f03e02abbc31ea8599a9c35816f314704e` |
| `tools/azure-runner/pipeline.py` | `a564fadefd812a855fe197f44d82680982b958ee45c3597782bfa9e874db75bf` |
| `tools/azure-runner/execution_leases.py` | `8693d056fd6daa506808bef6425ea9727fa09d40be30eddbb2bc4ac1c4825afd` |
| `tools/azure-runner/test_github_publication.py` | `2c098027a34bd8f66a347c67e8d5e42af934e73a1e5b580b8e137448d8d9d9d2` |
| `tools/azure-runner/test_execution_runtime.py` | `8eedaf800092eaa0fe736b163b421cea2db885f7e1ba4eb3255edb72108eb21c` |

### Supplied integration evidence and remaining limits

Inspected `../03-coding/publication-split-postgres-proof.py` and its JSON result.
Two actual controller subprocesses were killed against real disposable PostgreSQL:
one after the simulated branch write before receipt, one after the simulated PR
write before receipt. Explicit disposable-operator recovery produced one branch
write and one PR write per scenario; duplicate recovery added no write and the
old owner could not start another action. Validation approval rows were unchanged;
the isolated fixture created no approvals. Runtime hashes match this review.

That driver invokes the production split algorithm and lease functions with its
own bound callbacks, rather than the entire pipeline stage/parent/gate sequence.
The independent controls above cover the production pipeline callback wiring.
GitHub/Git provider state in the crash driver is an fsynced local-file simulation;
it does not establish actual GitHub timing or service idempotency. No external
write, schema change, approval, deployment or destructive cleanup was performed
by this reviewer.

Actual GitHub PR-list access remains blocked by the configured token's recorded
403. Complete maintenance fencing, constrained external QA/deployment capture,
retention and then context/output experiments remain outside this implemented
increment. B–D approval is still unanswered; no dependent implementation or fake
approval was introduced. Prior browser evidence retains its original source
identity and does not need to be relabelled as new UI testing.

### Durable learning and handoff

The integrator recorded this learning through the actual bound `append_memory`
tool on the populated configured database, post-coding row **58**, evidenced by
`../03-coding/publication-v3-memory.json`. Runs/executions/approvals remain
12/23/8 with an unchanged approval snapshot. This is manual engineering memory,
not a fleet stage. Recorded learning: “2026-09-11: Absence of
a per-action intent permits first execution only when every version of that
protocol persists intent before its external call; legacy aggregate records and
lost intent responses must remain held because absence of a provider result
cannot prove the operation never started.” The prior row 55 remains valid and
no rendered memory was hand-edited.

Open question: Do you approve the schema-free local contracts B–D in
`02-pre-coding/continuation-3-task-plan.md`, preserving the existing live rollout
and evidence-deletion gates?

Status: BLOCKED (complete foundation/formal stage); scoped v3 publication review PASS-WITH-NOTES


## Continuation-3 B/C/D independent post-coding review - 2026-09-11

Reviewed the full local diff versus main 80babd0 and the untracked maintenance, retention, QA capture and image candidate files in the isolated continuation-3 worktree. Detailed findings, source hashes and evidence limits: [bcd-review.md](bcd-review.md).

| ID | Area | Severity | Tag | Evidence/disposition |
|---|---|---|---|---|
| BCD-PC-1 | Pilot flag routing | major | fix-now - resolved | Integrator changed review.babysit_run to select maintenance when the fenced pilot is enabled independently of dispatcher leasing. Independent injected call verified one fenced call and zero legacy calls. |
| BCD-PC-2 | Temporary maintenance retention | medium | debt-ticket - open | LANTERN-DEBT-EXECUTION-GC amended in bcd-review.md: retained trial clones lack allocation descriptors and are not eligible for automatic retirement. |
| BCD-PC-3 | Descriptor history overhead | medium | debt-ticket - open | Same local ticket now requires bounded mount-lookup cost without weakening ancestor checks or tombstones. Every current launch scans all historical path mappings. |
| BCD-PC-4 | External candidate acceptance | acceptance limit | waived - scope only | Keeping held candidate files is acceptable for local review. Actual external HTTPS transport/capture, version-2 receipt display, image and dependency acceptance remain unaccepted, not waived. |

Independent checks: 35 focused tests passed, seven PostgreSQL tests skipped; pilot routing probe and diff whitespace check passed. Inspected supplied 14-test real PostgreSQL/Git/Docker green-path log with simulated GitHub; no independent live service proof claimed. Final configured quality run and independent security retest remain integrator-owned. No new schema, database modification, gate movement, deployment, external publication or runtime edit was performed by this reviewer.

Memory candidate and local execution-GC ticket amendment are in bcd-review.md; integrator owns actual append_memory insertion. No rendered memory edit claimed.

Status: PASS-WITH-NOTES (scoped local B/C/D review); complete foundation/formal stage and external activation remain unaccepted.


### B/C/D narrow supplement - 2026-09-11

Reviewed the explicit direct_fixture transport contract, shared validation at capture construction/seal/verify/persist, durable attempt/key checks and read-only retirement inventory. No new fix-now finding. Independent reruns: 16 retention and 9 provenance tests passed; diff whitespace check passed. Supplied actual local TLS recorder/PostgreSQL proof was inspected, not independently rerun; it remains explicitly test-only with no gateway/external transport acceptance. BCD-PC-2/3 retention debts remain open. Updated source hashes and evidence distinctions are appended in [bcd-review.md](bcd-review.md).

Status: PASS-WITH-NOTES (narrow local supplement); full foundation and external activation remain unaccepted.

## Continuation-3 outstanding infrastructure review - 2026-09-11

Independent post-coding review of the scoped infrastructure diff found and verified fixes for D20 fingerprint coverage, retention clone-lock duration and legacy-index races, immutable maintenance scope, actual child artifact fencing and missing Git base refs. Full findings table, compatibility notes and local debt amendment: [c3-outstanding-review.md](c3-outstanding-review.md).

| ID | Area | Severity | Tag | Disposition |
|---|---|---|---|---|
| C3-PC-1 | D20 fingerprint | medium | fix-now - resolved | Actual vendor helper/upstream lock and authority entry modules covered. |
| C3-PC-2/3 | Retention locking/index | major | fix-now - resolved | Unrelated mounts no longer wait through clone; verified legacy reconciliation and old-reader sentinels preserve ancestor/ownership holds. |
| C3-PC-4 | Maintenance scope | major | fix-now - resolved | Parent revalidation uses captured child scope, policy and image. |
| C3-PC-5/6 | Actual child handoff | major | fix-now - resolved | Artifact insertion fenced with dispatcher flag 0/1; exact base ref preserved; real finalize_coding passes and earlier handoff remains unchanged. |
| C3-PC-7 | Test import | minor | fix-now - resolved | Missing asyncio import corrected; final suite green. |
| C3-PC-8 | Allocation history scan | medium | debt-ticket - open | LANTERN-DEBT-EXECUTION-GC narrowed to allocation/rebuild scaling; steady mount lookup is bounded. |
| C3-PC-9 | External acceptance | acceptance limit | waived - local scope only | Disabled candidate may remain locally; actual image/TLS/native-host and trusted deployment acceptance are not waived. |

Independent evidence: [c3-review-probes.json](c3-review-probes.json) records 16/16 custom checks, including actual Git/handoff and baseline-reader probes; [c3-retention-retest-final.log](c3-retention-retest-final.log) records 21/21 retention tests. Initial defect/failed-test logs are preserved. Inspected supplied 18/18 disposable PostgreSQL/Git/Docker maintenance integration and new QA direct-TLS recordings without relabelling scripted model/provider behavior as live acceptance. Final full checks/D20 and actual append_memory receipt remain integrator-owned at this report cutoff; no rendered memory edit is claimed.

Status: PASS-WITH-NOTES (scoped local post-coding review); full foundation, external activation and staging remain unaccepted.

### Permanent lock-identity final retest - 2026-09-11

C3-PC-10 (major, **fix-now - resolved**) covers a final old-reader race: choosing a different lock pathname after an older reader created it split the lifecycle lock. The corrected implementation always acquires the same top-level lock. [c3-lock-compat-retest.json](c3-lock-compat-retest.json) records three passing old-reader/current-holder controls; [c3-retention-lock-retest.log](c3-retention-lock-retest.log) records the final 21/21 affected-suite pass in 12.199 seconds. [c3-final-review-snapshot.json](c3-final-review-snapshot.json) records the remaining inspected source identities and a separate malformed-mapping rejection; its retention hash is superseded by the lock-retest JSON. All fix-now findings are resolved and verified; allocation-scan debt and external-foundation prerequisites remain open.

Status: PASS-WITH-NOTES (final scoped local review); external foundation and staging remain unaccepted.

### Actual append_memory completion - 2026-09-11

Inspected the integrator's actual [c3-foundation-memory.json](../03-coding/c3-foundation-memory.json) receipt: post-coding row **66**, manual key `manual:feat-20260910-agentic-infrastructure:post-coding:pending-639f48d9e2ae`. It records the legacy-index, frozen-scope and permanent-lock lessons. Configured runs/executions/approvals remain **12/23/8** with unchanged approval snapshot; no migration/new cluster or rendered-memory edit is claimed. The earlier pending memory item is complete; exact inserted learning is copied into the detailed review.

Status: PASS-WITH-NOTES (final scoped local review; memory complete); external foundation and staging remain unaccepted.

## External QA acceptance candidate review — 2026-09-11

The bounded independent source review found and verified one native cleanup defect. Full scope, findings, source hashes, compatibility limits and verification are in [external-qa-review.md](external-qa-review.md).

| ID | Area | Severity | Tag | Disposition |
|---|---|---|---|---|
| EQA-PC-1 | Native cleanup | medium | fix-now — resolved | Each owned resource is attempted independently; bounded termination/join errors are aggregated and prevent a passing result. Verified with injected observer/container failures. |
| EQA-PC-2 | Library error recovery | compatibility limit | waived — local candidate only | Terminal writer errors and close/reopen contract documented; exported symbols do not imply universal behavior compatibility. |
| EQA-PC-3 | Evidence cutoff | acceptance limit | waived — source review only | Earlier socket-fixture results are not final image-pair, browser/deployment or external transport acceptance. |
| EQA-PC-4 | Toolchain rebuild | reproducibility limit | waived — immutable candidate only | Source/base pinned; later toolchain rebuild requires fresh inventory/audit/testing. |

Independent verification: 28/28 controller/transport/firewall unit tests and three additional ordinary async/cleanup probes passed. Monitor cancellation is joined before final connection reuse; failed monitoring or cleanup cannot produce accepted receipts. No unresolved fix-now remains in this bounded review. Final configured frozen-source check, image-pair/whole-image evidence and actual append_memory receipt remain parent-owned at this cutoff. The earlier configured run's source-stability failure is retained and is not treated as a pass.

Memory candidate supplied to parent: cleanup must attempt every independently owned resource despite earlier failures and fail on uncertainty; join periodic database checks before final connection reuse. No direct rendered-memory edit, database mutation, gate approval or deployment was performed by this reviewer.

Status: PASS-WITH-NOTES (bounded disabled external QA source review); external activation and staging remain unaccepted.
