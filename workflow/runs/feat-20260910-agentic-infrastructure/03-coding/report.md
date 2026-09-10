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

### Continuation 3 publication v2 and verified checkpoint

Implemented observed GitHub reconciliation with persisted repository ID, base
commit, destination, desired head and expected old remote head. Interrupted and
confirmed duplicates only observe; moved/deleted refs, changed repository/base,
wrong or contradictory PR identity, incomplete pagination and unavailable reads
hold. Push uses the immutable commit and exact remote-ref comparison. Existing
unbound intents are retained and held, not silently migrated. Strict publication
does not send optional comments, labels or provider review posts. The earlier
flag-disabled behavior does not inherit strict guarantees.

Independent review caught and verified fixes for publication artifacts preceding
the final destination check, provider state becoming stale during local review,
and an unledgered external review POST. Target/fence acceptance now includes
receipt/artifact writes, reobservation precedes the human gate, and strict local
review does not POST to GitHub. A final parser control refuses fractional nested
repository IDs and contradictory open/merged state. No human gate is approved or
merged by any of these paths.

Checkpoint validation: **560 configured unittest cases: 558 passed, two explicit
skips**, plus standalone property scripts; test command 138.391 seconds, lint
1.468 seconds, both exit zero. `continuation3-quality.json` records the exact
source hashes, unchanged source during checks and policy hash. The two skips are
Windows symlink privilege and the separately invoked live Docker control. Earlier
launcher failures are retained: Windows selected an unavailable WSL Bash, then
cmd preserved single quotes in the final discovery pattern. The corrected runner
uses the existing Git Bash and UTF-8 environment and executes the unchanged
configured commands plus the additive publication suite. No gate was weakened.

The actual Docker frozen-source control passed in **94.260 seconds** against
image `sha256:933a9c0899dae9c9d7f73d5bcf76a5298e7eaccea83b17233d4d8d56e3682756`.
Positive command, ignored-helper exclusion, manifest/source negatives and the
modify/test/restore refusal all passed; source remains available for the fix
loop. Receipt `c0791cebfa2587023c66e6a4c927b4964e23edda87084df197c9ab32c35a9a9e`
and exact harness fingerprint are in `continuation3-frozen-source.json` and log.
This uses no Azure or database.

`publication-postgres-proof.json` passes six controls using actual disposable
PostgreSQL at 55432 and actual controller subprocess death. The fsynced provider
file simulates GitHub; twelve GET observations and zero replay writes reconcile
the completed effect, while stale owners, changed destinations and moved provider
heads fail. Existing validation approvals remain unchanged. This is not live
GitHub publication or exactly-once provider proof.

Actual configured GitHub reads are in `github-readonly-validation.json`: repository
ID `1344678260` and main ref returned 200; the queried agent branch was absent;
PR listing returned **403: Resource not accessible by personal access token**.
The observer held, with zero provider mutations. PR read/write authorization and
a designated external test target remain prerequisites for positive live proof.
No credential permission was changed and no alternate identity was substituted.

Recorded QA repeated four contexts: actual authenticated desktop/mobile against
preserved disposable Azure executions 16/17, plus positive/forged/stale/cross-run
fixture receipt controls. All pass; 32 scoped UI tests pass. The four VP8 videos
fully decode (18.44/20.96/7.04/4.08 seconds). Actual-app approval 6 and all protected
state are unchanged. QA-E6 records wall-clock/video-offset drift; inspected video
offsets are used in the report. Positive verified-receipt UI is still fixture
evidence, not full execution-linked deployed-target capture.

D20 evals regenerated: plan coverage 1.00 on two examples, verifier invalid
acceptance 0/14 and valid rejection 0/1; other insufficient paired data remain
n/a. Frozen scores are not new Azure model measurements. New manual learnings
were actually appended to the restored configured database as rows 53–56, with
the earlier pending learnings at 48–52. Run/execution/approval counts remain
12/23/8. All recorded memory views were generated by the tool.

The v2 checkpoint retains one aggregate effect: branch-only partial publication
holds rather than safely completing the never-issued PR operation. The distinct
branch/PR intent follow-up is still required by plan A. Contracts B–D for fenced
babysitting, restricted external QA/capture and protected retirement remain
pending the precise architecture approval already submitted to the user. No new
schema, configured-database migration, deployment, live gate decision or merge
has been performed. Context/structured-output experiments remain deferred until
foundation acceptance. Security permits only the bounded local pilot; staging
remains NO-GO.

Status: IN PROGRESS (publication partial-repair follow-up; B–D approval pending)

### Continuation 3 publication v3 — split effects and final checks

Date: 2026-09-11 (Asia/Hong_Kong; receipts record UTC on September 10).

Fresh publication now records separate fenced branch and PR intents under a
version-3 parent. Recovery observes a completed branch and may create the PR
only when its child intent never existed. An interrupted PR call is observed,
never repeated. A child intent with an absent provider result remains held.
Every legacy v1/v2 parent is refused before new child intents: those protocols
cannot prove a missing child means its external operation never started.
Destination, repository ID, base/head revisions, expected old remote ref and
request hash remain bound. Conditional push, target/fence checks, final provider
observation and human gate ownership are unchanged. No schema was added.

Independent post-coding and security review found no new fix-now or high/critical
findings. Their reports record 30 publication tests, 36 runtime tests, independent
production-callback fault injections and security's lease-loss-before-POST
control. The earlier partial-branch implementation debt is closed for fresh v3
requests. This does not close positive live GitHub or full pipeline acceptance.

| Evidence | Environment and exact result |
|---|---|
| `publication-v3-quality.json`, `publication-v3-test.log`, `publication-v3-lint.log` | Complete configured local commands: **571 unittest cases, 569 passed and two explicit skips**, plus standalone property scripts; test 183.265s, lint 1.641s; unchanged runtime source during checks. Windows symlink privilege and opt-in live Docker are the two skips; Docker ran separately below. |
| `publication-split-postgres-proof.json` and matching `.py` | Actual disposable PostgreSQL at port 55432 and two actual controller-process kills, after branch write and after PR write. Git/GitHub operations are durable local-file simulations. Each recovery ends with exactly one branch write and one PR write, both child receipts confirmed, duplicate invocation does not replay, and the stale owner is refused. Existing validation approvals are unchanged. This executes the production split driver with real lease callbacks, not the entire production orchestration against GitHub. |
| `github-v3-readonly-validation.json` | Actual configured bot, GitHub REST: repository/main GET 200, queried branch 404, PR GET 403 (`Resource not accessible by personal access token`). Observer holds; **zero provider mutations**. Repository ID 1344678260, main SHA `25bb11334b224f01e7ca81f6e96483a9aa2ad5d0`. |
| `publication-v3-frozen-source.json` and `.log` | Actual Docker image `sha256:933a9c0899dae9c9d7f73d5bcf76a5298e7eaccea83b17233d4d8d56e3682756`, one test passed in 117.678s. Positive command, manifest/source negatives, ignored dependency exclusion and mutable modify/test/restore versus read-only refusal pass. No Azure or database used. Manifest `8c049363b11f89c61f9aa5b7a5221d13df94a6d9970d8da5b584a80de3fd1998`; harness source fingerprint `d666a795620833921db1a5854824b71a8ff941689bf69f281209d77d90b4f724`. |
| `publication-v3-memory.json` | Actual append_memory: coding row **57**, post-coding row **58** in original configured localhost:5432 `lantern` database. Runs/executions/approvals remain **12/23/8**, complete approval snapshot unchanged; memory count 34→36. No migration or substitute cluster. |
| `retention-inventory.json` | Read-only inventory of the configured checkout root: eight legacy checkouts, **149,093,385 bytes**. All held without per-execution descriptors/shared retirement locks; no checkout or evidence deleted. Not an inventory of every temporary integration directory. |

Final runtime SHA-256 values match the independent reviews and disposable crash
proof: github_publication.py `d0b0b0d41cdfd74abc924361849a62f03e02abbc31ea8599a9c35816f314704e`,
pipeline.py `a564fadefd812a855fe197f44d82680982b958ee45c3597782bfa9e874db75bf`,
execution_leases.py `8693d056fd6daa506808bef6425ea9727fa09d40be30eddbb2bc4ac1c4825afd`.
Full per-file identities are in the quality record. D20 build/report regenerated;
fingerprint `d847da278368673a6d7a65a90d63a7a7a76f46e2ef722bc571b5163daca23bb0`,
frozen plan coverage 1.00 (n=2), invalid acceptance 0/14, valid rejection 0/1.
Unpaired suites remain n/a; no new Azure model measurement is claimed.

The four recorded browser QA contexts and decoded videos from the preceding
checkpoint still cover the unchanged Mission Control UI source hashes listed in
`../04-qa-dev/report.md`. No UI files changed for v3; browser QA was not repeated
for a backend-only effect split. Real-app and fixture provenance remain separate.
QA-E6's event-clock/video-offset limitation remains recorded. These videos do not
establish deployment-bound capture with requirement outcomes.

Remaining blockers: approval of architecture contracts B–D; their implementation
and race/transport/capture acceptance; an authorized GitHub test destination and
bot PR permissions for positive live publication; full execution-linked external
QA evidence. Retention deletion stays disabled. Existing legacy or ambiguous
publication intents stay held. Configured database recovery is complete, but the
underlying prior Windows startup exception is not diagnosed beyond its logs.
Foundation acceptance is incomplete, so context-budget/structured-output Azure
experiments remain deferred as requested. No human approval, merge or deployment
was performed; staging remains **NO-GO**, with only the bounded local pilot allowed.

Status: BLOCKED (remaining dependent architecture work; v3 increment complete)

Do you approve local implementation of architecture contracts B–D in
`../02-pre-coding/continuation-3-task-plan.md`, preserving every existing human
gate and excluding configured-database migration and deployment?

### Continuation 3 B–D local increment — 2026-09-11

The user requested "do the continuation-3 of the work we are doing with agent
infrastructure thing". This continues the concrete local work order above;
architecture implementation is no longer waiting on the previous question.
It does not authorize a registered gate decision, configured schema migration,
external publication, deployment or evidence deletion. No such action occurred.

The increment is isolated at `C:/Users/dimas/.lantern/worktrees/continuation-3`,
branch `codex/agentic-infrastructure-continuation-3`, based on `80babd0`.
A concurrent task changed the original checkout's Mission Control UI and branch;
its work was preserved. This worktree contains the infrastructure changes and
reviews. It changes neither Azure provider/SDK routing nor the fixed pipeline.

**Implemented behavior.** Dedicated default-off maintenance leases bind the
latest human code-complete decision, exact PR, repository/base/working refs and
run position. Maintenance never rewrites a run to executing or changes a human
approval. Claim/retry/rework/decision paths share the run lock; child conflict
checks use a fresh statement after that lock. Real concurrency testing found
and fixed the pre-wait PostgreSQL statement-snapshot race. Manual and scheduled
entry points use the same pilot, including when legacy dispatcher leasing is off.

Trial merges verify exact parent revisions and regate immutable committed source
in an image pinned by digest. Working-branch publication uses expected-old-head
conditional push, current provider observations and fenced effect receipts.
Repeated cancellation stops known workers and joins helper threads. Conflicts
and red regates hold; inherited maintenance fix authority is still absent.

Fresh isolated checkouts have controller descriptors and shared allocation,
worker-mount and retirement locks. Cleanup defaults to dry-run, verifies terminal
database state/server age/all container mounts and refuses unknown ownership,
links, path substitution and unverified Desktop mount translation. It tombstones,
quarantines and deletes only owned temporary roots in tests, with crash/audit
recovery. Evidence/output/error remains pinned indefinitely. Diagnostic inventory
reports bytes, server ages and held reasons; no cleanup scheduler is connected.

The external QA gateway is an unaccepted source/image candidate and its launcher
unconditionally refuses activation. Its 43 exact wheel hashes match the reviewed
PyPI metadata, but four selected packages have reported advisories. The build
retry was stopped; there is no accepted gateway image or host firewall adapter.
The narrow recorder image built successfully and passed a direct local HTTPS
fixture with ephemeral NSS CA trust and certificate checks enabled. Its trace is
redacted command-outcome JSON, not a Playwright replay ZIP. Controller receipts
bind the fixture deployment, image, requirements, execution/attempt/fence and
actual decoded media, and validate explicit transport mode at every boundary.
Fenced database persistence also checks the durable attempt/key. This is a local
fixture, not an external deployment or packet-denial acceptance claim.

| Evidence | Final result and scope |
|---|---|
| `bcd-final-quality.json`, `bcd-final-test.log`, `bcd-final-lint.log` | Complete configured commands passed: **616 unittest cases, 607 passed and 9 explicit skips**, plus standalone checks; test 113.422s, lint 0.359s. Runtime source unchanged during checks; full per-file hashes in JSON. Skips are seven opt-in PostgreSQL cases, one opt-in Docker evidence case and Windows symlink privilege. The opted-in suites ran separately below. |
| `bcd-final-maintenance.log` | **14/14 passed**, 26.364s, with real disposable PostgreSQL, a real temporary Git merge, immutable Docker regate and conditional local push. GitHub observations were simulated. Includes parent-lock race, competing ownership, expiration, renewal, stale effect, changed approval and unchanged run/approval checks. |
| `bcd-final-frozen-source.log` | Actual Docker test **1/1 passed**, 79.006s, image `sha256:933a9c0899dae9c9d7f73d5bcf76a5298e7eaccea83b17233d4d8d56e3682756`; positive quality command, source/manifest negatives, ignored dependency exclusion and mutable modify/test/restore versus read-only refusal. No Azure or database. |
| `bcd-capture-proof.py/json`, `bcd-capture-expected.json` | Actual recorder image `sha256:a743cef23a8d1049392135d806aeab9be3ffb3e65559616ae5a66dea5c52172f`; four browser commands passed; actual 1.0s VP8 video fully decoded. Disposable SQL persisted the matching receipt and rejected wrong attempt/key/stale owner. Test-only direct TLS, no gateway; fixture database/containers/network removed. Public CA only reached recorder; temporary private key removed with fixture files. |
| `../04-qa-dev/bcd-capture-verification.json`, `bcd-capture-supplement.md` | Independent **13/13** actual-media controls: positive full decode and 12 identity/tamper/outcome/mirror negatives. Actual frame at 0:00.5 inspected. Redacted trace and one-second fixture video do not replace full workflow diagnostics. |
| `../04-qa-dev/bcd-report.md` and baseline result/decoder JSON | Four recorded desktop/mobile real-app and fixture contexts passed on baseline UI `80babd0`; actual videos 57.16s/42.28s decoded and inspected. Existing app database approval snapshot unchanged. These browser tests remain separate from the new recorder proof; unrelated UI edits were excluded through a frozen temporary runtime. |
| `../05-post-coding/bcd-review.md` | Independent PASS-WITH-NOTES; explicit pilot routing defect fixed. Final supplement: 16 retention + 9 provenance tests pass. Temporary maintenance clone allocation and all-history descriptor scan cost remain local debt. |
| `../06-security/continuation3-bcd-prereview.md`, final snapshot and media review JSON | No remaining confirmed high B/D issue; independent final 16 retention, 9 receipt and 7 adversarial probes pass. Actual media independently rehashed and decoded. Scope permits local B/D and test-only fixture; external C and staging NO-GO. |
| `bcd-retention-inventory.json` | Existing configured root: **8 legacy checkouts, 149,093,385 bytes, zero eligible, zero deleted**. Unknown server age is null; no filesystem timestamp authorizes cleanup. Maintenance temp clones are outside this inventory and stay retained. |
| `bcd-memory.json` | Actual bound `append_memory` calls wrote coding/security/post-coding/QA rows **60–63** to existing localhost:5432 `lantern`. Runs/executions/approvals stayed **12/23/8**, complete approval snapshot unchanged; memory 37→41. No migration or fabricated stage execution. Rendered memory includes an existing concurrent task's row and was not hand-edited. |

The earlier `bcd-increment-*` failed check is retained as iteration evidence,
not final validation. Final checks above supersede it. `bcd-isolated-*` was an
intermediate passing checkpoint. D20 build/report regenerated: fingerprint
`5a980d1ebb9f8215d788435a756161286e1ec8f15d16a85ed18f6d9e64798e3e`, frozen
plan coverage 1.00 (n=2), invalid acceptance 0/14 and valid rejection 0/1.
These frozen verifier scores do not establish live Azure quality.

| Work-order item | Verdict |
|---|---|
| C3-1–3 | Existing configured database recovery and publication v3 increment preserved; positive live GitHub proof remains limited by the previously observed bot PR-read 403. No permission changes or provider mutations were made. |
| C3-4–5 | Local B–D continuation authorized; independent reviews completed. Dedicated maintenance acquisition, eligibility, fencing and recovery implemented and locally tested. |
| C3-6 | Green immutable-regate/conditional-push path implemented; red-regate inherited fix is explicitly held and incomplete. |
| C3-7 | **Incomplete / activation blocked:** gateway dependency advisory disposition, successful accepted image, effective-hook tests and host egress-denial adapter/acceptance remain. |
| C3-8 | Local direct-TLS sealed capture mechanics pass; external deployment and fleet-stage integration remain incomplete. |
| C3-9 | Conservative retirement/inventory API and temporary-root race/crash tests implemented. Legacy/real evidence deletion not performed; maintenance temp allocation and lookup scalability remain debt. |
| C3-10 | Local configured checks and independent QA/post/security reviews pass within stated scope. Full foundation acceptance is incomplete. |
| C3-11 | Deferred until foundation acceptance; no context-budget or structured-output Azure experiment run or promoted. |

Videos and binary screenshots remain local artifacts rather than git
payloads; reports retain their exact names/hashes. No artifact upload was
performed by this manual engineering session. Deployment and all human gates
remain unchanged. Follow-on work is the bounded red-regate authority path,
gateway dependency/network acceptance and complete external capture integration.

Status: PARTIAL — B/D local increment and test-only recorder proof complete;
external QA/foundation acceptance incomplete; staging NO-GO.
