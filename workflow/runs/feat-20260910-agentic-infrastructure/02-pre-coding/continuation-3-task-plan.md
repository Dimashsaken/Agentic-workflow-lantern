# Continuation 3 work order proposal

## Local implementation authorization — 2026-09-11

The follow-up instruction, "do the continuation-3 of the work we are doing with
agent infrastructure thing", authorizes continuing the concrete local B–D work
below. The engineering session used that instruction for implementation, isolated
test images and disposable fixture tests. This records conversation authority;
it is not a registered pipeline approval or a fabricated gate decision. No
configured-database migration, external publication, deployment or evidence
deletion is included. The proposal text below is retained as the historical work
order; final implementation/acceptance status is in `../03-coding/report.md`.

Date: 2026-09-10. Baseline `a64c229`. **HITL: required** for the new architecture
contracts B–D below. No new schema is proposed. Section C now explicitly proposes
new isolated gateway/recorder images, dependencies and ephemeral certificate trust
for approval; nothing has been installed or activated. This is an amendment to
local tasks 9–14, not a new registered story or an approval row.

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

**Concrete proposal updated 2026-09-11; HITL: required, not implemented.** Choose
one per-execution TLS-terminating `mitmdump` gateway with a controller-owned policy
addon, and one dedicated Chromium recorder on that execution's internal Docker
network. This makes decrypted application destinations inspectable. A CONNECT
allowlist alone is insufficient on shared endpoints. The gateway becomes a trusted
processor of QA cookies and plaintext traffic; approve that trust explicitly.

### Components, dependencies and compatibility

Proposed creations: `infra/qa-gateway/Dockerfile`, `requirements.lock`, `policy.py`
and `entrypoint.py` in that directory; `infra/qa-recorder/Dockerfile`; and
`tools/azure-runner/qa_recorder_worker.py`. Previously proposed `qa_transport.py`
owns controller policy/network/lifecycle, and `qa_provenance.py` owns receipts.
The gateway image contains mitmproxy's `mitmdump`, its fully locked transitive
Python/TLS dependencies, OpenSSL tooling and an upstream CA bundle. The recorder
image derives from the approved sandbox image and adds `libnss3-tools` for its
isolated Chromium trust store. It runs only the narrow browser/recording API;
no product checkout, coding shell API or arbitrary writer to the recording root.

Inspected baseline `infra/sandbox/Dockerfile`: Ubuntu 24.04, Python 3.12,
Playwright 1.62.1/MCP 0.0.79 and `ca-certificates`; no explicit mitmproxy or
`libnss3-tools` installation. These are **proposed additions**, not pre-existing
capabilities. Leave that image, coding/quality workers, Azure controller and SDK
requirements unchanged. A separate gateway environment avoids dependency conflicts.
Before activation, review an exact direct/transitive lock with hashes, OS-package
inventory, licenses/advisories, build provenance and both image identities. Resolve
and record actual immutable image digests; no invented version, image digest or
compatibility claim appears in this proposal. No download occurs at execution
start. Dependency or protocol changes outside this proposal return for review.

### Network and protocol boundary

Only the gateway has a controlled outbound route. The recorder has no ordinary
egress and can reach only its own proxy IP/port. Controller-installed network
rules also deny direct DNS, Docker's embedded-DNS forwarding, UDP/QUIC, direct
TCP, host/metadata access and other executions; proxy variables are supplemental.
The gateway cannot route packets between interfaces. Neither container receives
Docker socket, controller credentials, harness/authority mounts or host networking;
keep nonroot UID, dropped capabilities, read-only root and bounded tmpfs/resources.
No proxy port is published on the host; no web UI, onboarding app, SOCKS listener
or control API is exposed. If the Docker host cannot enforce the required rules,
including Docker Desktop where used, external mode fails before browser launch.
Coding/quality workers retain `--network=none`.

Initial transport is HTTPS over HTTP/1.1 only. Reject HTTP/2, HTTP/3, raw TCP,
CONNECT nesting, TLS passthrough, missing/uninspectable SNI/ECH, WebSockets and
other upgrades. Targets requiring them are unsupported until a separately tested
extension; never silently switch to a tunnel or certificate-error bypass.
Controller-owned options explicitly select lazy upstream connection, disable
upstream certificate sniffing and generic TCP/HTTP2/HTTP3/WebSocket forwarding,
retain inbound-header and upstream-certificate validation, and disable onboarding,
replay, flow dumps and interactive configuration. Validate effective options at
startup against the selected package; documentation alone is not version proof.
These controls correspond to documented [mitmproxy options](https://docs.mitmproxy.org/stable/concepts/options/).

### Exact destination enforcement

1. The controller freezes a versioned policy of canonical ASCII DNS HTTPS origins
   and explicit ports. No wildcard, userinfo, IP-literal URL, ambiguous encoding or
   implicit alternate port is permitted. Resolve approved names with a trusted
   resolver, validate every answer/CNAME outcome and reject loopback, link-local,
   metadata, private, multicast, reserved and IPv4-mapped IPv6 forms. Freeze the
   numeric destinations for a bounded session, expiring no later than the recorded
   DNS validity bound. No worker DNS result or automatic fallback can change them.
   A private integration endpoint requires a separate exact origin/IP policy marked
   test-only; that exception cannot enter external configuration.
2. The gateway accepts CONNECT only for a listed canonical origin. At ClientHello,
   require SNI to equal that CONNECT name. Terminate TLS locally, then require
   each decrypted request's scheme, Host and port to equal the approved tunnel
   origin. Reject missing/duplicate/conflicting Host, absolute-target disagreement,
   malformed framing and unsupported ALPN; recheck every keep-alive request.
   A mismatch must cause zero upstream application bytes. Redirects, subresources,
   popups and service-worker requests independently traverse the same checks.
3. Before every upstream socket, a mandatory permit binds the approved origin,
   numeric address/port, execution and live policy expiry. Connect to that numeric
   address without another hostname lookup, retain the original hostname as SNI,
   and verify the upstream certificate chain and original hostname. Check the
   observed peer address against the permit; connection reuse stays bound to the
   same origin. Host egress rules allow only the frozen destinations/ports. DNS
   changes, permit expiry or a certificate failure stop the session rather than
   refreshing policy inside it.
4. Implement CONNECT, ClientHello, request-header and pre-server-connect checks
   through the documented [event hooks](https://docs.mitmproxy.org/stable/api/events.html).
   Pin address/SNI using the selected version's verified
   [connection API](https://docs.mitmproxy.org/stable/api/mitmproxy/connection.html).
   Require a positive per-request permit before forwarding; addon load/config errors,
   hook exceptions and missing permits kill the flow/session. Do not rely on the
   proxy's default exception logging to stop forwarding. Actual tests must prove
   the core neither connects early nor overwrites the pinned destination.

An allowed endpoint can itself relay data or contain application vulnerabilities.
This policy constrains the network/application destination, not the semantics of
an approved service or what that service does server-side. Use scoped QA accounts;
do not add a general-purpose relay, DNS-over-HTTPS endpoint or broad login/CDN
wildcard to make a failing test pass. Required login/assets need explicit origins.

### Ephemeral CA and recording lifecycle

The controller allocates a new execution/recording ID and gateway-private tmpfs.
Generate a fresh CA there per attempt, with at most 24-hour CA validity and a
maximum 30-minute pilot session; the policy/lease may expire earlier. Only the
public certificate and its fingerprint cross to the recorder. The private CA key
and issued private keys never enter browser mounts, controller evidence, logs,
image layers or durable artifacts. Mitmproxy supports a custom CA/config directory;
this design uses that mechanism, not a shared installed CA.
[Certificate documentation](https://docs.mitmproxy.org/stable/concepts/certificates/).

Before browser launch, import the public CA into a fresh NSS database in that
container's ephemeral home; identify the actual trust-store location used by the
pinned Chromium build. Chromium documents its Linux NSS store and certificate
import tooling in [Linux certificate management](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/linux/cert_management.md).
Never import into the host/user OS, controller, another worker or gateway upstream
trust bundle. Do not set `ignoreHTTPSErrors`, `--ignore-certificate-errors` or
passthrough exceptions. Certificate-pinned/mTLS targets are unsupported initially.
A missing, wrong or prior-execution CA must fail the positive TLS probe.

Start recording only after the gateway's policy/addon/TLS readiness and a scoped
positive probe succeed. The controller owns recorder commands, session identity,
capture directory and close/seal lifecycle. On lease loss, policy expiry, gateway
failure or cancellation, close recorder writers/connections, stop both containers,
then retire exact network/temporary trust resources. Never reuse the profile or
CA on retry. Persist only public fingerprints, policy digest and redacted diagnostic
codes; no URL queries, headers, cookies, bodies, TLS key logs or mitmproxy flow dumps.
The gateway necessarily handles QA plaintext in memory; CA deletion is not a claim
of cryptographic memory erasure. Failure to confirm cleanup holds the attempt.

Initial bounded policy: at most 32 simultaneous connections, 64 KiB headers,
8 MiB request/response body, 256 MiB aggregate session traffic, 10-second connect,
30-second request and 30-minute session limits. Disable unbounded streaming;
limit decoded content as well as wire bytes. These are pilot constraints to test,
not measured capacity claims. Larger fixtures require explicit policy review.

### Required real negative controls and provenance

Before acceptance, run the actual candidate images with an instrumented allowed
HTTPS fixture and independent forbidden endpoint/packet observations. Require:

- A valid page, explicit allowed asset and normal request succeed with both TLS
  legs verified; disallowed redirects/assets/popups/service workers cannot reach
  the forbidden endpoint. Include a permissive fixture to prove the test harness
  would observe a forbidden connection if the boundary were removed.
- On the same destination IP, CONNECT/SNI/Host disagreement, changed Host on a
  reused connection, malformed/duplicate headers and alternate port are refused.
  Prove DNS rebinding, private/mapped addresses, hostname-check mismatch, expired
  certificate and untrusted upstream CA fail; no insecure fallback exists.
- Direct sockets, Docker DNS, QUIC/HTTP3, HTTP2, ECH/no-SNI, raw tunnels and WebSocket
  upgrades fail. Another execution cannot reach the gateway, steal its CA key or
  use its trust profile. Missing/wrong/old CA fails even for the allowed fixture.
- Inject addon exceptions, failed policy load, worker/gateway/controller death,
  expiry, oversized/compressed bodies and interrupted cleanup. Require no
  unauthorized upstream bytes, no continued capture claim and no live resource
  deletion. Unit hooks alone do not satisfy these controls.

Deployment identity remains separate from checkout HEAD: obtain a controller-
observed trusted deploy descriptor/revision at start and finish, matched to the
approved target, and hold on absence/drift. An app's self-reported SHA is weaker
and cannot silently replace that descriptor. Close all media writers, fully decode,
hash and seal with execution ID/key/attempt/fence, recording ID, gateway/recorder
image identities, CA fingerprint, policy/deployment digests, times, observed test
outcomes, requirement mappings and video/trace digests. Use a separately versioned
QA receipt in fenced execution output/artifact metadata; mirrors remain display only.
Hashes establish correspondence, not semantic coverage. Preserve wrong execution/
revision, recording swap, forged worker JSON, byte tampering, decode failure,
missing/failing requirement, deployment drift and always-rejecting-verifier controls.
Record desktop/mobile valid, invalid and legacy display. Unknown live target or
credentials block external validation, not preparation of this approved design.

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

Do you approve local implementation of contracts B–D for dedicated fenced
babysitting, the TLS-inspecting QA gateway and deployment-bound recorder
(including their proposed images/dependencies and ephemeral CA trust), and
lock-protected checkout retirement, preserving all existing human gates and
excluding configured-database migration, deployment and evidence deletion?
