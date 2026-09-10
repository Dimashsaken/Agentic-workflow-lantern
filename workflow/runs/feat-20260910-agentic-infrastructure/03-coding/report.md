# Stage Report: 03-coding — feat-20260910-agentic-infrastructure

- **Agent/author:** Codex, developer session
- **Date:** 2026-09-10
- **Status:** PASS-WITH-NOTES

## Summary

Implemented the user-authorized infrastructure plan in
`docs/plans/agentic-infrastructure.md` on local branch `codex/agentic-infrastructure`.
This folder records local engineering evidence; it is not a database-registered
fleet execution and does not satisfy or decide a live pipeline gate.

## Work performed

Read the coding charter, skills, memory, runboard, architecture assessment,
decisions, orchestration contract and runtime code. Retained Azure OpenAI, the
Agents SDK and the fixed code-driven stage sequence. Added:

- Execution-bound file capabilities, generated capability documentation, role
  output ownership, protected harness artifacts and scoped design collection.
- A validated read-only Git grammar, protected-file exclusions for search/history,
  safe revision forms, Windows case handling, alias checks and preserved CRLF
  semantics. This filters conventional credential paths; it is not a secret scanner.
- Mandatory automatic-code tests, a quality configuration captured before the
  first model turn, typed gate-result checks, and scope inspection that fails on
  enumeration errors and includes both sides of a rename.
- Evidence paths and line resolution, review locations checked against the
  handoff's commit/diff, host-side checkout verification, and explicit report status.
- Incremental attempt diagnostics, available SDK partial errors/usage, redaction
  and failure classification. A transport retry cannot blindly replay a loop with
  tool calls. Failure cleanup preserves the known usage and closes resources.
- Structured evidence display in Mission Control, verifier controls in the eval
  report, SDK minor-version compatibility bounds, and rollout documentation (D24).

## Findings / results

The initial full configured test command passed. Independent local QA
confirmed three findings in the first implementation: Windows role/run aliases,
implicit Git credential-file reads, and a case-alias validation self-citation.
All were fixed; the unchanged independent reproduction now reports all eight
bypass booleans false. See `../04-qa-dev/adversarial-probes-before.txt`,
`adversarial-probes-after.txt`, `bugs.md` and `report.md`.

A subsequent full run caught a Windows CRLF regression from discarding global Git
configuration. Inspection now carries forward only a validated `core.autocrlf`
scalar. The original scope test and a new isolated global-config regression pass.

Final configured test/lint results are recorded in `local-quality.json` and the
complete `quality-test.log` / `quality-lint.log`. This record is explicitly marked
`fleet_execution: false`; its source hashes identify the tested local snapshot.

Final result: **384 unit tests passed, one Windows symlink test skipped** (385
total), plus passing standalone product-access and coding property scripts.
The configured test command exited 0 in 102.0 seconds. Lint (compileall and the
D20 eval/fingerprint check) exited 0 in 0.9 seconds. `git diff --check` passed.
The integrator reran QA's unchanged reproduction against the final source:
`local-probes-final.json` has all eight bypass results false.

| Criterion | Implementation and verification | Local verdict |
|---|---|---|
| AC-1 | `tool_policy.py`, actual SDK ToolContext calls, role/run interleaving, protected artifacts, exports, Windows aliases and hardlinks | Pass; real symlink creation skipped on this Windows host |
| AC-2 | `readonly_git.py`, disposable repositories, normal inspection and refusal cases, broad/history/wildcard secret-path controls, blob and alias cases | Pass |
| AC-3 | `factory.py`, missing/malformed/stale/contradictory gates, policy replacement before/during commands, renamed paths and failed Git enumeration | Pass |
| AC-4 | `evidence.py`, missing/empty/self/cross-run references, invalid lines, immutable review head/diff and Mission Control rendering | Pass |
| AC-5 | `ExecutionJournal`, actual SDK exception interface with injected model/DB boundaries; completed plus partial usage, absent usage, retries and both executors | Pass for tested process-level paths |
| AC-6 | Full configured checks, eval regeneration/fingerprint, independent QA reproduction and this handoff | Pass for local engineering; live gates remain unexecuted |

The labelled verifier controls accept zero of 14 invalid records and reject zero
of one valid record. Both an always-accepting and an always-rejecting verifier are
detected by the eval tests. The frozen plan score remains 1.00 on only two plans;
there are no scored validator-vs-QA examples. These numbers do not establish live
model performance or production false-acceptance rates.

## Artifacts

- `docs/plans/agentic-infrastructure.md` — acceptance criteria and ordered plan.
- `docs/DECISIONS.md` D24 — implementation, trust boundary and rollout decision.
- `docs/AGENT-CAPABILITIES.md` — generated policy inventory.
- `tools/evals/REPORT.md` — frozen metrics and verifier controls.
- `validate-local.py` — repeatable local configured-check runner.
- `local-quality.json`, `quality-test.log`, `quality-lint.log` — final check evidence.
- `local-probes-final.json` — the unchanged QA reproductions on the final source.
- `../04-qa-dev/` — independent local audit, findings and exact retest evidence.

## Deviations

The checked-in local virtualenv launcher references a missing Python installation.
Local tests use the bundled Python 3.12 runtime with the existing virtualenv's
packages loaded through a local, ignored `sitecustomize.py`.

Verification used bundled Python 3.12.14, installed `openai-agents` 0.22.0 and Git
for Windows. The SDK tool invocation and exception interfaces were checked against
the installed SDK. No dependency download, database migration or live model call
was required. One symlink test needs Windows privileges unavailable in this session.

The requested security subagent failed before conducting its review: the platform
risk check flagged the request for possible cybersecurity risk. No independent
security report or signoff is claimed. The QA agent completed a local regression
audit; its recorded dev-browser gate is BLOCKED because no real dev environment
was exercised. Neither status is converted into a pipeline approval.

## Handoff notes for the next stage

Deploy the host code and sandbox image together only after the normal review and
deployment gates. Old coding gate records without policy hashes no longer pass
new execution checks. Products need a meaningful `quality.test` configured before
automatic coding. Update quality policy in a separate reviewed change; do not
weaken it during a build/fix execution. New validation executions require resolvable
references; old prose artifacts remain readable in Mission Control.

This change is a tool boundary, not OS isolation or signed gate attestation. A
coding shell, an unrestricted MCP server, shared-user filesystem access, database
credentials and arbitrary secret content remain separate trust boundaries. File
and Git reference resolution does not prove test coverage or video provenance.
Hard process death before SDK return can still lose telemetry. Early setup
failures and full crash recovery need broader lifecycle work.

Recommended next implementation sequence:

1. Immutable harness mounts and authoritative host-side gate records, scoped
   credentials and constrained egress; verify on the actual execution image.
2. Renewable stage leases with fencing, restart recovery and streamed diagnostics;
   verify kill/restart and duplicate-effect scenarios against disposable Postgres.
3. Execution-stamped evidence manifests and requirement-to-test links, followed by
   live Azure and recorded dev-browser acceptance runs.
4. Context-budget management and SDK structured outputs using the resulting live
   evaluation corpus. Keep the deterministic stage graph and human gates.

No branch was published, no PR opened, no human approval written and no deployment
performed. The pre-existing untracked `.codex/` directory was left untouched.

## Open questions

No answer is needed to review the local implementation. Live rollout still needs
the normal environment, recorded QA and human gates described above.

## Memory candidates

Candidate durable learning: When restricting an existing command interface, test
normal behavior alongside refusals and preserve benign repository semantics;
otherwise a permission fix can turn valid work into a false gate failure.

The configured role-memory database timed out on a bounded read-only availability
check both inside and outside the sandbox. No `append_memory` insertion was made,
and the rendered memory file was not edited. This local engineering report is not
presented as satisfying the fleet's database-backed memory postcondition.

## Commit and continuation handoff — 2026-09-10

The user explicitly requested committing the completed files and a prompt for the
unfinished work. The tested source hashes still match `local-quality.json`; the
eval fingerprint was checked again. The commit includes implementation, tests,
evals and local evidence, plus `docs/plans/agentic-infrastructure-continuation.md`.
It excludes the pre-existing `.codex/` directory. No push, deployment or pipeline
approval is part of this commit handoff. Database-backed memory recording remains
unavailable as documented above and is included in the continuation prompt.

Status: PASS-WITH-NOTES

## Continuation increment 1 — live validation and lifecycle fixes, 2026-09-10

Status: PASS-WITH-NOTES

Resumed at 90e4fb6 on codex/agentic-infrastructure; preserved unrelated .codex/.
The existing venv now works (Python 3.12.10, Agents SDK 0.22.0). Configured checks
need Git Bash first on PATH; WindowsApps/bash is a broken WSL stub. No credentials
were printed or production database modified.

Implemented independent review findings R-1 through R-3: setup/MCP failures now
enter cleanup and diagnostic boundaries, usage bookkeeping cannot replace the
primary failure, cleanup finishes before success, and postcondition failures are
journaled. A Linux regression exposed model lookup during failure logging; the
selected model is now captured once. Docker forwards the generic turn limit.
The actual image built on Windows failed with `bash\r`; Dockerfile normalizes the
entrypoint line endings. Seven lifecycle regressions extend the original seven.

Live evidence (all databases/products disposable; no approvals decided):

| Evidence | Actual result |
|---|---|
| live-inprocess-final.json | Azure research/story succeeded, executions 5/6, stopped at pending story_signoff, two actual memory-tool rows |
| live-docker-1.json | Actual sandbox/Azure/Postgres research/story succeeded, executions 7/8, stopped at pending story_signoff, two memory-tool rows |
| live-inprocess-partial.json | MaxTurnsExceeded failed honestly; 2 requests / 18,304 tokens retained |
| live-docker-partial.json | Same failure through actual sandbox; 2 requests / 17,022 tokens retained |
| live-docker-killed.json | Actual active stage killed, execution 10 failed, no gate, usage remains null/unknown; no restart/resumption claim |
| postgres-memory-verification.log | Real Postgres concurrency/retry memory controls pass |
| linux-*.log | Candidate-image policy (19), gate (8), evidence (11), final journal (14): 52 passed; initial journal failure retained separately |
| docker-isolation-controls.json | Three independent clones, original unchanged, killed container removed, fresh container has no residue |
| ../04-qa-dev/live-browser-results.json | Authenticated actual Mission Control desktop/mobile recordings on Azure-produced run data; before/after DB state unchanged |
| ../04-qa-dev/local-browser-results.json | Separate fixture-backed structured evidence/legacy/escaping renderer recordings |

Image: sha256:933a9c0899dae9c9d7f73d5bcf76a5298e7eaccea83b17233d4d8d56e3682756.
Image Python 3.12.3 / Agents SDK 0.22.2; within the checked-in >=0.22,<0.23 bound.
This differs from Windows SDK 0.22.0 and is explicitly recorded in
environment-validation.json. Live JSON records carry tested source hashes and
physical artifact directories. Model transcripts stay in isolated ignored
workspaces; videos/traces remain local ignored media, not git binaries.
The initial live-inprocess-1.json failure used an erroneous validation-driver
Chat Completions default; the driver was corrected to the product's Responses
API default before successful runs. It is not a product regression.

Independent post-coding and defensive security reviews executed. Security also
independently checked the lifecycle corrections. Both reports remain local
engineering evidence, not registered stage signoffs. No feature-introduced new
critical/high vulnerability was confirmed; staging remains NO-GO pending the
next infrastructure work and release gates.

Local complete configured checks pass: 392 tests (391 passed, one Windows symlink
privilege skip), plus standalone property scripts; lint/evals pass. Final log,
source hashes and timings are in local-quality.json and quality-*.log.

Limitations: the configured localhost:5432 Lantern DB still refuses connections.
The actual memory tool worked in disposable runs; this does not satisfy the missing
durable manual learning in the configured DB. New container controls prove product
separation/cleanup, not immutable harness authority, scoped credentials or egress.
Hard kills still lose unknown tail usage. No lease/restart/effect guarantee is
inferred from a killed container being removed. Actual downstream validator-stage
evidence remains unexecuted; its UI rendering was separately fixture-tested.

## Next increment authorization — 2026-09-10

The concrete 02-pre-coding task plan and forward/rollback SQL were presented to the
user. Their subsequent instruction was "continue". This developer session treats
that as authorization to proceed with the presented local implementation and
disposable-schema tests. It is not a live pipeline approval row or deployment
permission. No approved story, registered plan_signoff or other fleet record is
fabricated. Live gates continue to require their existing mechanisms.

## Increment 2 — isolated controller, recovery and execution evidence

Implemented an opt-in host controller with isolated product/MCP workers, separate
execution checkouts, pinned images, no network, no controller credentials/mounts,
and descriptor-based worker file tools. Model-controlled writers stop before
handoff and media collection. Output collection rejects linked files and stages
upload bytes outside worker mounts. Product Git executes in ephemeral workers;
raw binary Git output is preserved and replacement refs are disabled.

Renewable run/child leases now fence completion, advancement, artifact and memory
acceptance, usage and publication receipts. Each parallel child gets its own DB
connection; host stages serialize while their environment helpers remain global.
Expired attempts are held, not automatically replayed. Publication intent binds
the exact destination and head; confirmed results can be reused, while ambiguous
outcomes hold. Leased legacy Docker and babysitting are explicitly refused until
they support the same lifecycle. These restrictions are documented pilot limits,
not completed implementations of those paths.

SDK callbacks fsync response usage and tool boundaries before the next turn.
Completed response usage also reaches Postgres immediately. The actual crash
test killed the controller after one Azure response: 7,955 input + 156 output =
8,111 known tokens survived, tool events survived, execution 13 was held failed,
the exact abandoned worker was removed, and no gate opened. The unfinished tail
remains unknown. Recovery never resumes serialized SDK state. Available results
from a returned SDK loop and streamed response counters are reconciled without
double-counting. Success diagnostics follow cleanup and DB completion.

Strict quality checks now use an independent read-only committed snapshot with
fresh Git metadata and image-baked dependencies. This fixes the independently
reproduced source-substitution flaw: before/after hashing had accepted a command
that changed code, passed, and restored the original. The frozen worker rejects
that command with a read-only-filesystem error. It also excludes ignored helpers.
Host gate authority, manifests and command logs stay outside worker mounts.
Requirement links are explicit plan data, and manifests bind identity, attempt,
fence, source, image, quality policy, command outcomes and artifact digests.
Harness fingerprints include uncommitted source rather than claiming HEAD alone
was tested. These receipts establish observations, not semantic test coverage.

Mission Control displays provenance from the controller's completed execution
row, including tested commit/tree, image, manifest and planned test links. Missing
or cross-execution receipts remain unverified. Long Windows trace paths use a
deterministic shortened filename, with matching lookup behavior.

### Evidence and confidence boundaries

| Evidence | What actually ran |
|---|---|
| live-leased-isolated.json | Real Azure/Postgres research and story, executions 11/12, with leases and isolated tools; pending story gate. Windows trace-path failures were found here and subsequently fixed. |
| live-leased-isolated-final.json | Real Azure/Postgres executions 14/15, both succeeded, both traces persisted, story_signoff pending, two actual disposable memory-tool rows. |
| live-controller-recovery.json | Actual Azure controller process killed; fsynced diagnostics + known DB usage survived; lease recovery held the run and exact-label cleanup removed its worker. Tested source hashes included. |
| lease-recovery-integration.json | Actual PostgreSQL migration/rollback, competing owners, renewal, stale writes, parallel child connections, process death after an fsynced local effect, duplicate holds/reconciliation, and unchanged approvals. The external effect is a disposable local file, not GitHub. |
| isolated-worker-controls.json | Actual image shell/MCP controls, offline recorded browser, credentials/mount/egress denials, binary Git fidelity, and post-policy symlink-swap file-I/O controls. |
| frozen-source-integration.json | Actual image quality command, ignored-dependency exclusion and modify/test/restore negative control; no Azure or database involved. |
| live-trusted-evidence.log | Earlier actual image manifest prototype; superseded for source immutability by frozen-source-integration.json and its final rerun. |
| ../04-qa-dev/provenance-browser-results-final.json | Recorded fixture desktop/mobile positive receipt and forged/stale/cross-run negatives. Positive receipt UI remains fixture coverage. |
| ../04-qa-dev/provenance-live-results.json | Actual authenticated current Mission Control desktop/mobile on executions 11/12; database before/after snapshots identical, approval 4 pending. Story executions correctly have no coding manifest. |

Independent post-coding review found and verified four additional fixes:
central babysitter hold, lease/legacy-Docker refusal, child-fenced artifact writes,
and success diagnostics after final lifecycle completion. Independent defensive
security review closed source substitution, memory fencing, publication-target
binding and checkout concurrency findings. Its final local-pilot verdict is
conditional GO; staging remains NO-GO. Reports contain their source hashes and
independent controls. Recorded QA found no new product bug in this increment.

### Acceptance status and remaining work

| Criterion | Current status |
|---|---|
| AC-7 | Verified for the offline isolated controller on the actual image. External browser egress, Paper transport and production least-privilege DB grants are not implemented or certified. |
| AC-8 | Verified in the disposable host-controller path with real Azure/Postgres death and recovery controls. Unknown tail stays unknown; SDK resumption is deliberately disabled. |
| AC-9 | Durable intent/fencing, duplicate holds and explicit reconciliation primitive implemented and tested on disposable effects. Actual GitHub reconciliation and fenced babysitting remain incomplete; strict mode holds these unsupported paths. |
| AC-10 | Quality-command snapshot manifests and verifier negatives implemented. Video decoding/capture-identity primitives tested, but generic QA stage media is not yet fully sealed to deployment revision and requirement outcomes through that manifest path. No semantic coverage claim. |
| AC-11 | Recorded current-app QA, explicit fixture provenance controls, and independent reviews complete as engineering evidence. This is not a registered pipeline signoff. |
| AC-12 | Context-budget/structured-output experiments remain deferred until the remaining foundation/rollout acceptance is complete. No provider or orchestration-framework change. |

The configured localhost:5432 database remains unavailable, so the missing durable
manual memory append is still blocked. Actual tool rows in disposable runs do not
satisfy it. Candidate learning: pre/post hashes cannot prove which mutable code a
test executed; use a separate read-only committed snapshot and a negative
modify/test/restore control. Additional reviewer learnings are in their reports.
No rendered memory file or runboard was hand-edited.

Operations, compatibility limits and rollback are in docs/EXECUTION-ISOLATION.md.
Checkouts and evidence are retained; post-coding recorded retention debt
LANTERN-DEBT-EXECUTION-GC. Git commands already in flight cannot be revoked, so
partial mirror changes require explicit reconciliation. No S3 upload, GitHub
publication, staging/prod deployment, merge, or human approval was performed.
Live end-to-end work stops at the real pending story approvals. These remaining
items prevent claiming the entire continuation plan or a production rollout is
complete.

### Final candidate verification

The final current-source Azure run is `live-controller-final.json`: executions 16
and 17 succeeded with leases, fenced memory, isolated file tools, writer quiescence
and unique attempt checkouts; both traces persisted, two disposable memory-tool
rows exist, and story_signoff remains pending. No downstream gate was bypassed.
The final actual-image snapshot proof is `frozen-source-final.json` plus its full
log: 25 tests passed in 123.989 seconds including the real Docker test. The
modify/test/restore command is rejected on the read-only source, while the positive
control passes; this proof uses no Azure or database.

Final configured quality command: 532 unittest cases, plus standalone property scripts;
2 explicit skips (Windows symlink privilege and opt-in live test). Test command
passed in 164.3 seconds; lint/evals passed in 2.6 seconds. Full logs, source hashes
and the quality-policy hash are in local-quality.json. Frozen eval plan coverage
remains 1.00 on two examples; insufficient validator/QA paired data stays n/a.
These frozen scores are not live model-quality measurements.

## Continuation 3 — configured database recovery (2026-09-10)

Inspected the actual checkout: branch `codex/agentic-infrastructure`, HEAD
`a64c229`, no tracked edits and only unrelated untracked `.codex/`. No reset,
replacement checkout or modification of `.codex/` was performed.

The configured database was a stopped standalone PostgreSQL installation, not a
Windows service or the disposable Docker validation database. The existing
`C:/Users/dimas/.lantern/pg.log` records a backend and startup-process failure
with Windows exception `0xC0000142` at 2026-09-09 13:23:31 CST. The log establishes
the shutdown sequence, not the underlying Windows cause. The original PostgreSQL
16 installation and `pgdata` remained present, with cluster system identifier
`7678204476830612652`. Starting that same cluster with its existing `pg_ctl.exe`
and data directory performed WAL recovery and reached ready at
2026-09-10 23:29:39 CST on loopback port 5432. No initialization, data replacement,
schema migration or disposable-database substitution occurred.

`configured-postgres-restored.json` records the authenticated identity: database
`lantern`, PostgreSQL 16.9, original data directory. Counts before/after remain
12 runs, 23 stage executions and 8 approvals; the full approval-row snapshot hash
is unchanged. `restore-memory.py` invoked the actual `make_append_memory` SDK tool
via `ToolContext` with explicit manual-engineering identities, inserting pending
coding, QA, post-coding and security learnings plus the new planner learning as
role_memory rows **48–52**. Memory count changed from 25 to 30. These are durable
configured-database rows, not fleet execution completion. The tool regenerated
its role memory views; none was hand-edited. An initial invocation used the old
SDK context type and failed before any insertion; the corrected ToolContext path
succeeded. No schema, execution, gate or approval row was created.

This closes the configured-database/durable-learning blocker. It does not certify
production readiness or close the outstanding foundation criteria. Publication,
maintenance ownership, constrained external QA, evidence and retention work follow
the existing local authorization and the concrete continuation-3 planning review.

Status: IN PROGRESS
