# Continuation 3 work order proposal

Date: 2026-09-10. Baseline `a64c229`. **HITL: required** for the new architecture
contracts B–D below. No new schema or package is proposed. This is an amendment
to local tasks 9–14, not a new registered story or an approval row.

## Authorization and acceptance scope

The earlier local plan and subsequent “continue” authorize implementing and
testing publication reconciliation (task 9 / AC-9), video provenance (task 11 /
AC-10), and review/QA integration (task 13 / AC-11). Continue conservative fixes
within those contracts now. The current request explicitly adds retention work
and requires concrete architectural plans and human approval before dependent
changes. The separately reviewed external transport, maintenance lease semantics
and retention protocol below therefore remain proposals pending that decision.
Production schema application, staging/production deployment, human approvals and
merge ownership remain unchanged. No live GitHub publication or message is
authorized merely by permission to implement the adapter.

Proposed subcriteria refine existing local AC-7–AC-12, not approved story IDs:

- **AC-9a:** Interrupted and duplicate publication reconciles branch and PR against
  observed GitHub identity; changed destination/revision or ambiguous observations
  hold, and an existing logical effect is not replayed.
- **AC-9b:** Manual and scheduled babysitting share one fenced operation, require
  the current human approval, preserve every gate/state, never merge into base,
  and reject stale results, competing owners and concurrent ref changes.
- **AC-7a / AC-10a:** External QA reaches only declared destinations, records a
  controller-owned session and deployment observation, and seals media plus
  executed requirement outcomes to its execution; negative controls stay active.
- **AC-8a / AC-11a:** Retention cannot remove any live worker mount or evidence
  still required for verification; reports show retained bytes, ages and holds.
- **AC-12:** Only after foundation acceptance, compare context/output experiments
  with a measured Azure baseline; no automatic promotion or gate change.

## A. Publication reconciliation — existing local task 9

Store a versioned nonsecret canonical request at intent creation in the existing
effect JSON. Bind run, repository identity, base ref, working ref, handoff head,
operation kind and expected old remote ref. Derive keys from the request digest;
retain compatibility checks for earlier aggregate keys. Split branch publication
and PR creation into distinct effects; optional labels/comments must be separate
idempotent effects or omitted in strict mode. Read-only reconcile does not send
comments, labels, reviews or notifications.

The controller queries GitHub directly with bounded pagination and validates
repository identity, exact head/base repository/ref, current head SHA, PR number,
state and canonical URL. A title or branch name alone does not establish identity.
Resolve refs from provider state rather than an unrefreshed mirror. Persist the
minimal observation, observation time and request hash, without credentials or
unbounded provider payloads. Never treat an HTTP error, exhausted pagination,
multiple matching PRs, moved head/base, deleted ref or closed/merged PR as success.
An already merged or closed PR is a terminal observation for a human, not authority
to recreate it or merge anything.

Confirm the branch effect only after observing the requested SHA at the bound
remote ref. Confirm the PR effect only when exactly one matching PR has the exact
bound repository/base/head and requested SHA. Confirmed receipts are re-observed
before reuse that would open a gate; a stale receipt does not prove current state.
An intended/uncertain duplicate triggers observation, never a blind mutation.
If the provider cannot prove success, hold with diagnostics. Absence does not
prove an in-flight request cannot arrive later; do not clear uncertainty based on
one empty response. A fresh explicit retry may perform only the still-unperformed
operation after quiescence/reconciliation establishes safe prerequisites.

Use expected-old-head conditional ref updates and never unconditional force.
Before every mutation recheck ownership and destination; after return fence the
receipt transaction again. On timeout/lost lease keep the effect uncertain. Legacy
aggregate rows lacking reconstructable request data remain held. Test kill after
push, kill after PR creation, duplicate response, network failure, partial success,
PR pagination, wrong base/repo/head, changed destination, stale lease and remote
head races. Unit provider fakes and disposable Git remotes are not live GitHub proof.

## B. Fenced babysitter — architecture decision

Use a dedicated maintenance execution in existing `stage_executions`; never
temporarily set a waiting/done run to executing just to satisfy stage lease code.
Acquire under the run-row lock, require auto coding plus the latest applicable
human `code_complete` approval, match that approval's publication target, refuse
newer rework/pending/rejected decisions, and snapshot the current run stage/fence,
target and approval ID. Explicit `--force` bypasses only scheduling backoff.

Dispatcher claim, rework, maintenance claim and renewal use the same exclusion
rules. Defer maintenance while another execution owns the run; reject a stage
claim while maintenance is active. No approvals or stage positions are rewritten.
Renew on a separate connection and recheck approval/target/rework binding on each
authoritative write. A changed gate or run invalidates maintenance. Expiration
holds only the maintenance attempt and its ambiguous effects, preserving the
run's actual gate/state. An attempted final write from the old owner fails.

Build the trial merge in a unique private checkout, into the working branch only.
Regate against an immutable committed snapshot before publication; a red result
enters at most the existing bounded fix path under explicitly inherited maintenance
authority, never a forged dispatcher lease. Refuse the fix path until its child
fencing and publication binding are implemented. Conflicts remain human-owned.
Publish through A with expected old head, and separately observe unchanged base
before claiming the branch was made current. Base/head movement causes a hold or
fresh pass, never overwrite. Comments are omitted in strict pilot until their own
effect handling exists. No operation merges a PR or marks a human gate approved.

Acceptance requires real disposable PostgreSQL competing-owner, heartbeat,
expiration and stale-write tests; real temporary Git conflict/head-race tests;
approval row byte-for-byte before/after comparisons; and regression of both CLI
and daemon entry points. Activation remains default off until independent review.

## C. External QA and sealed capture — architecture decision

Propose a separate per-execution internal Docker network connecting only a
dedicated browser worker to a minimal gateway. The browser worker has no ordinary
egress route. The gateway is the only component with an outbound network; it has
no controller credentials, Docker socket, harness/authority mounts or product
checkout. A proxy setting or Playwright request hook alone is not containment.
The offline worker and all coding/quality workers keep `--network=none`.

Gateway policy comes from controller-owned configuration: exact HTTPS origins
and ports, no wildcards or URL userinfo, bounded connections/body/response/time,
and DNS/IP validation at connection time. Reject loopback, link-local/metadata,
multicast, private and reserved addresses by default, including IPv6 and rebinding.
Any private test target requires an explicit exact operator-owned IP/origin
exception in isolated integration configuration; it cannot silently carry into
external policy. CONNECT permits only declared origin/port; disable alternative
direct protocols and QUIC. Every redirect/subresource/WebSocket destination must
pass the same policy, including popup/service-worker traffic. No gateway listener
or arbitrary control API is exposed to another execution. Reap gateway/network
only by exact execution IDs after worker shutdown. Prove direct-socket and
cross-execution denials on the actual image, not only browser-route unit tests.

Security pre-review refinement: CONNECT hostname checks alone do not prove the
HTTPS Host/SNI within an encrypted tunnel; shared addresses and domain fronting
can violate an exact-origin claim. Before implementation, define and test a
gateway that enforces the actual TLS/application destination, or narrow the
accepted guarantee explicitly to approved endpoint addresses. Do not advertise
exact HTTPS-origin enforcement from tunnel names or proxy variables alone. A
TLS-terminating design and any new certificate trust/dependencies require their
own concrete review before being introduced.

The controller creates the recording ID before browser start and owns its
execution-bound capture directory and lifecycle. Prefer a dedicated recorder
worker with no coding shell/file writer and narrow browser-operation API. Arbitrary
product shell access to its video directory is not a trusted capture boundary.
Close all page/context writers before hashing, full decode and sealing. Retain
trace links; redact/avoid secrets without using a worker-authored claim as proof.

Deployment identity is a separate observation from checkout HEAD. Require a
controller-observed deployment descriptor supplied by the deploy system or a
trusted revision endpoint, matched to the approved target/revision at session
start and finish. Record descriptor digest, deployment revision, target-policy
digest, recording ID, recorder image, execution ID/key/attempt/fence, timestamps,
test IDs and observed outcomes, requirement links and video/trace digests. An
application self-reported SHA is explicitly weaker evidence and cannot silently
replace a trusted deployment descriptor. Revision drift/absence fails strict
deployment verification rather than labeling the recording verified.

Version the QA receipt independently of the existing quality manifest. The
controller computes outcomes from observed assertions/command results, and maps
requirements from the approved plan/charter. Hashes prove correspondence, not
semantic coverage. Store receipt identity in fenced execution output and artifact
metadata. Mirror files remain display only. Preserve wrong execution/revision,
recording swap, forged worker JSON, altered bytes, decode failure, missing/failing
requirement, deployment drift and always-rejecting verifier controls. Recorded
desktop/mobile QA must exercise valid, invalid and legacy presentation. Unknown
external target configuration blocks live validation, not local implementation.

## D. Retention — architecture decision and security pre-review

Implement dry-run by default. Eligible disposable checkouts are terminal attempts
older than a configurable 7-day pilot default; no active lease, uncertain effect,
unresolved recovery hold, evidence pin or unknown ownership is eligible. Unknown
legacy paths are inventory only. Default evidence retention is indefinite;
do not delete manifests, diagnostics, database rows, media without a verified
durable copy, or source snapshots needed by the current verifier.

Create a controller-owned execution descriptor at checkout allocation. Worker
creation/mounting and cleanup must acquire the same per-execution OS lock outside
worker mounts and honor an irreversible retirement tombstone. Cleanup locks,
rechecks terminal database ownership with server time, verifies all container IDs
and mounts (not labels alone), and holds on any Docker/database inspection failure.
Join/terminate known local worker subprocesses before eligibility. PID absence
alone is not sufficient. A process killed between allocation and registration
leaves an unknown held descriptor, not a deletion candidate.

Under that lock, recheck canonical root confinement and reject symlinks,
junctions/reparse points, hardlink escape inputs, root directories, aliases and
unexpected identities. Mark retired and atomically quarantine within the same
filesystem, then delete only that proven quarantined directory. Never compose
PowerShell-discovered paths into another shell. Resume interrupted quarantine
only from the matching descriptor. New attempts always have distinct paths; a
stale request cannot point cleanup at the replacement. Recheck the lock/tombstone
on every worker start, including delayed starts after cancellation.

Emit inventory and audit results with bytes/ages/held reason. Test live mount,
active and expired-but-unreconciled lease, stale request, path substitution,
simultaneous launch/retirement, crash before/after quarantine, absent Docker,
Windows locked files and ordinary terminal deletion. Run destructive controls only
on owned temporary roots. Real retained evidence deletion requires an explicit
retention policy decision and verified remote retrieval, outside the initial
checkout-cleanup default.

## Ordered reviewable increments

Each task is at most half a day; split rather than extend a hidden change.

| Task | Size | Dependency / approval | Deliverable / criteria |
|---|---|---|---|
| C3-1 Preserve baseline and restore configured DB non-destructively | S | Already requested; no DDL | Exact service identity, actual memory-tool receipts; separate existing/disposable DB evidence |
| C3-2 Complete publication observation and conditional update | M | Existing local task 9 | A plus unit/temporary Git controls; AC-9a |
| C3-3 Add real disposable publication integration | S | C3-2 | PostgreSQL kill/duplicate controls; clearly separate actual GitHub observation/validation if target is available |
| C3-4 Approve and security pre-review B–D | S | **HITL: required** | Concrete architecture decision; no schema/package change |
| C3-5 Add maintenance lease and dual-entry eligibility | M | C3-4 | B acquisition/renewal/recovery/approval tests; AC-9b |
| C3-6 Fence trial merge, regate, fix and publication | M | C3-2, C3-5 | Immutable regate and bounded inherited fix, exact-target effects; AC-9b |
| C3-7 Build gateway and actual-image denial controls | M | C3-4 | C transport, independent security review; AC-7a |
| C3-8 Seal QA recording and deployment observations | M | C3-7 | Controller capture plus positive/negative receipt tests; AC-10a |
| C3-9 Add retention inventory/locks, then quarantine/apply | M | C3-4 | D temporary-root race/crash controls and metrics; AC-8a/11a |
| C3-10 Recorded browser QA, reviews and final foundation evidence | M | C3-3, C3-6, C3-8, C3-9 | QA dev, post-coding and security findings fixed, D20 regenerated; AC-11 |
| C3-11 Measure Azure context/output experiments | M | C3-10 foundation acceptance and approved experiment contract | AC-12 comparison; no production behavior promotion |

For C3-11, freeze a small representative corpus and baseline SDK/model/prompt/tool
schema revisions. Measure successful criteria/envelope validity, false acceptance,
requests, input/cached/output tokens, known cost, wall time and retries. Compare
context budgeting and structured output independently, preserving raw inputs and
failure cases. A one-stage smoke is not quality evidence for a long-context change.
Use the same Azure deployment/SDK bounds and fixed pipeline; reject regressions
or inconclusive samples and keep existing behavior. Present thresholds/corpus and
the required separate experiment approval before live experimental changes.

## Definition of code complete

- Prior baseline controls preserved; exact new test counts/logs and source hashes.
- New architectural approvals recorded honestly in local handoff; registered
  gates use their real mechanisms and are never fabricated.
- Real PostgreSQL/Docker/temporary Git integrations labeled separately from unit
  fakes and actual GitHub/deployment/Azure validation.
- Negative verifier and frozen-source controls retained; recorded browser QA
  includes a real positive execution receipt rather than only a fixture badge.
- Independent QA, post-coding and security findings resolved or explicitly held;
  staging stays NO-GO until its full target prerequisites and human gates pass.
- New policy modules included in D20 eval fingerprint; complete configured checks
  pass for each committed increment. No SDK/provider/framework replacement.
- Actual `append_memory` used on configured durable DB once reachable. No rendered
  memory edit, fake execution, remote message, publication or approval claim.

## Decision requested

Do you approve the schema-free local contracts B–D for dedicated fenced
babysitting, an allowlisted QA gateway with deployment-bound recording receipts,
and lock-protected checkout retirement, keeping live rollout and evidence deletion
subject to their existing human gates?
