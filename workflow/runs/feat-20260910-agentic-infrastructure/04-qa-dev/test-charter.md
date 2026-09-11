# Local QA audit charter — feat-20260910-agentic-infrastructure

Date: 2026-09-10. Scope: independent audit of user-authorized local engineering work.
This is not a database-registered fleet execution or a QA gate approval. Written
before test execution. Acceptance criteria come from
`docs/plans/agentic-infrastructure.md`; the local run has no story envelope.

## Confidence-map probes

The coding report is IN-PROGRESS and supplies no confidence map. Prioritize policy
bypasses, contradictory quality results, and fabricated evidence because these are
the new trust boundaries. Distinguish an SDK tool boundary from OS isolation.

## Acceptance criteria and local checks

- AC-1: Run real SDK wrapper tests. Probe traversal, secrets, execution identity,
  sibling outputs, host artifacts, scope escape, shared reports and export paths.
- AC-2: Run Git tests against disposable real repositories. Probe option/value
  ambiguity, filesystem traversal, read-only ref behavior, and hook execution.
- AC-3: Run fail-closed code gate tests. Inspect contradictory, missing, stale and
  malformed results, test-command absence, and configuration pinning.
- AC-4: Run evidence resolution tests. Probe invalid paths/lines, self-citation,
  reviewed revision mismatch, and the UI's structured evidence HTML escaping.
- AC-5: Run execution-journal regression tests for partial failed turns,
  classification, redaction and honest usage accounting.
- AC-6: Record commands, outcomes, skips and limitations. The parent integrator
  owns the complete suite and regenerated eval artifacts.

## Edge cases and exploratory time-box

Spend at most 20 minutes on independent local adversarial probes after the supplied
tests. Focus on Windows path case/aliases, Git positional operands, and evidence
read-versus-write identity. Use only disposable test files with synthetic content.
No real credentials or customer data are part of this audit.

## UI and regression limits

No dev server is currently running per kickoff. Check only whether a dev URL is
configured in the process environment without printing its value. The qa-dev
contract says to report BLOCKED if dev is down and not test around it; do not
substitute fixture rendering for recorded dev UI evidence. Browser scenarios
(refresh, repeated expansion, hostile evidence text, mobile layout) remain pending
until a real dev environment and recorder are available. No live gate interaction,
database writes, approval, deployment, Azure call, or network integration test.

## Evidence conventions

Local test logs and reproduction scripts live beside this charter. Every recorded
browser session must use `tools/qa-recorder` and have a video and trace with exact
timestamps. If no browser runs, explicitly report zero videos rather than claiming
recorded evidence.

## Round 2 — regression scope

Rerun the original independent reproduction unchanged after the integrator's fixes,
then execute tool-policy/Git, evidence, gate-integrity, journal, Mission Control
traceability and standalone product-access checks. Preserve before/after output.
Keep the dev browser gate and independent security review separate from this local
regression result.

## Round 3 — continuation baseline and local browser regression

Written before execution on 2026-09-10. The completed coding confidence map now
identifies real database/model execution, OS isolation and browser behavior as
unverified. The process and dotenv-backed environment contain no configured dev
URL or dev login credentials. Consequently the real dev stage stays BLOCKED.

Independently rerun the existing adversarial probes and relevant policy, evidence,
gate, journal and Mission Control suites against baseline 90e4fb6. Preserve logs
and source hashes. The parent owns real Postgres/Docker/Azure diagnosis.

As separate local engineering evidence, record the production Mission Control
traceability and validation renderers against disposable synthetic envelopes.
This component server creates no database rows and has no gate actions. It cannot
substitute for authenticated dev application QA or live integration evidence.

- AC-4 desktop: structured file/line references, Unicode, literal HTML-shaped text,
  long references, legacy evidence prose, empty story, refresh and browser back.
- AC-4 mobile: matrix horizontal scrolling keeps every evidence column reachable;
  inspect text truncation/tooltips and page overflow.
- Exploratory session: switch theme, navigate repeatedly and inspect console
  errors. Test structured evidence in the gate validation table too.
- Record each context with qa-recorder's Playwright video/trace pattern. Keep
  named local videos outside git, record timestamps and hashes, and explicitly
  label all generated pages as fixtures. Do not invent an execution ID or upload.

## Round 4 — authenticated local dev integration

The parent has completed genuine Azure/Postgres researcher and story executions
in an isolated harness, with the resulting run stopped at pending story_signoff.
Use that existing disposable run; do not create fixture validation records.
Before recording, snapshot its run status, execution IDs and approval decision
fields directly from disposable Postgres. Launch the actual isolated Mission
Control application using process-only local auth and an environment-provided URL.

- Verify unauthenticated navigation requires login, then authenticate through UI.
- Record real run lanes, story evidence and the traceability matrix. Later stages
  must remain pending because the story gate has not been approved.
- Open actual researcher/story execution drawers, compiled-prompt/tool-call
  diagnostics, typed envelopes and memory sections; refresh without mutations.
- Mobile: real matrix scroll and later-stage pending evidence remain legible.
- Do not click gate, retry, rework, chat-send or other modifying controls. Reject
  unexpected non-GET browser requests after login. Re-read Postgres afterwards
  and require run/execution/gate decision state to remain identical.
- Video covers login with the password masked. Tracing begins after login so it
  never records credential payloads. All session links carry timestamps and hashes.
- This is authenticated local dev integration against real disposable data, not
  a registered 04-qa-dev pipeline execution or deployed-environment signoff.

## Round 5 — execution provenance continuation

Written before execution, 2026-09-10. AC-10/AC-11 component probes use explicitly
synthetic execution rows with the production drawer renderer: a matching verified
receipt, no receipt with a forged gate mirror, a stale execution receipt, a
cross-run receipt, Unicode/HTML-shaped test names, and narrow-screen readability.
Record short video/trace contexts, scroll the actual evidence section into the
viewport, refresh/back and switch theme. Verify no markup is interpreted.

Separately launch current Mission Control against existing disposable Azure run
data. Record authenticated execution drawers and missing-provenance labels without
inserting fixture receipts into its database. Snapshot run, execution and approval
state before/after. Existing live story gates remain pending. Actual controller
manifest generation, tamper refusal, lease recovery and Azure calls are covered
by the integrator's separate evidence, not inferred from renderer fixtures.

## Round 6 — continuation 3 UI regression

Written before execution, 2026-09-10. Use the copied current application and
preserved disposable Azure executions 16/17; require the launcher to reject the
configured database and accept only the designated disposable endpoint. No new
Azure call, execution row, receipt or approval may be manufactured for this test.

- AC-10/11: record desktop and mobile authentication/evidence navigation, absent
  provenance, reload and return to run. Compare protected DB state before/after.
- Repeat separately labelled renderer fixtures: matching controller receipt,
  forged writable mirror, stale attempt and cross-run receipt; Unicode/HTML names,
  viewport geometry, back/refresh and theme switch. Keep positive controls.
- Run existing drawer and route regressions. Decode every new video and inspect
  representative frames, preserving timestamps, source/video hashes and traces.
- Time-box exploration to the existing navigation/theme probes. No gate action,
  retry, chat send, publication or authenticated non-GET request after login.
- Publication reconciliation has no changed UI surface; these sessions cannot
  prove provider reconciliation, maintenance fencing, external QA transport or
  deployment-bound recording receipts. Those acceptance items remain separate.

## Continuation 3 outstanding-foundation QA charter — 2026-09-11

Author: qa-dev. Baseline `09fdb11c18f8a12f8b625d4c2e7ceeebd1deb8e5`, isolated branch `codex/agentic-infrastructure-continuation-3`. This charter precedes new execution. No registered story/brief exists in this local engineering run; the approved local continuation work order and `02-pre-coding/continuation-3-task-plan.md` supply the proposed acceptance mappings. Existing UI recordings and immutable-source controls remain prior evidence; no unchanged proof is repeated.

### Confidence-map probes (priority order)

| Probe | Criteria | Required observation | Classification |
|---|---|---|---|
| M1 Red maintenance regate repairs once | AC-9b | Actual temporary Git merge fails immutable gate, bounded repair inherits exact maintenance parent/target/approval binding, fresh immutable gate passes, conditional local ref update succeeds once. Run position and human approval rows remain identical. | Disposable SQL/Git/Docker integration; provider observation simulated |
| M2 Failed, stale and cancelled repair | AC-9b | Exhausted repair limit, lost/changed parent authority, policy/source change, stale expected ref and repeated cancellation cannot publish. Child workers quiesce; terminal evidence remains. | Bounded disposable integration and targeted injected fault controls |
| Q1 Fleet capture entry | AC-10a/11 | Real QA execution routing invokes controller plan, start/end trusted descriptor observation, always-on recorder, full decode, seal and fenced receipt persistence. Exact command/result identity and complete requirements required. | Actual fleet code path with disposable direct-TLS fixture; explicitly test-only |
| Q2 Capture denial boundaries | AC-10a | Direct fixture never acquires verified external status; deployment drift, missing requirement, wrong execution/attempt/fence, swapped media, stale controller, malformed outcome and open writers hold receipt acceptance. | New-path integration/fault controls; existing pure verifier proofs reused when unchanged |
| Q3 Cancellation/expiry | AC-10a | Recorder is stopped and joined before return; no receipt or continued capture claim survives a lost lease, cancellation, expired policy or descriptor failure. Temporary trust/process resources have owned cleanup receipts. | Disposable process/container controls |
| G1 External gateway | AC-7a | Independently audited actual image, effective TLS hooks, allowed TLS positive, transport/destination/host-network denials with observable forbidden endpoint and permissive control. Launcher stays disabled until every required real control passes. | Security-owned actual-image evidence; no fixture promoted to live acceptance |
| R1 Maintenance descriptor lifecycle | AC-8a/11a | New maintenance checkout is registered under shared lock; indexed lookup avoids all-history scan, absent/legacy descriptors stay held; evidence remains indefinitely. | Post-coding/security review and targeted disposable lifecycle controls |

### Edges and regressions

Prioritize duplicate command IDs, malformed and missing outcomes, empty/max plans, stale descriptor between capture start/finish, second cancellation during join, delayed worker start, and conditionally updated refs changing after the repair gate. External browser transport is not a prerequisite for the separately marked direct-TLS controller integration. A down intended dev environment blocks live QA rather than authorizing a substitute target.

No Mission Control UI source is in this increment, so double-submit/back/refresh/mobile/theme/legacy receipt UI proofs are reused from the previous recorded round. New capture recordings use the controller recorder in `tools/qa-recorder`'s always-on Playwright model; traces are redacted command outcomes, explicitly not replayable Playwright network traces. Each retained video will be decoded and linked with media-relative timestamps.

### Exploratory time-box and stopping rule

After code handoff, spend one bounded adversarial session tracing malformed recorder output and lease loss across the new fleet boundary. Record only browser-dependent cases. Do not migrate the configured database, change human gates, contact external targets, publish, deploy, or delete existing evidence. Use fresh named databases/containers only. Exact environment/credential values come from process environment and never enter reports.

### Initial prerequisites

The Docker CLI is present, but the Linux-engine named pipe is absent at initial inspection; no image/listener readiness is claimed. No QA target, deployment descriptor, image or database configuration is exposed in this QA agent's process environment. Python asyncpg/cryptography are present in the established virtual environment; the recorder uses its own image-local Node Playwright. `append_memory` is not exposed to this child agent; a dated learning will be sent to the integration owner for the actual tool invocation.

Status: PREPARED — initial execution blocked on Docker readiness and injected disposable configuration; external foundation acceptance remains blocked on its own target and network prerequisites.

### Execution checkpoint — 2026-09-11

Q2 and the injected Q3 shutdown boundary: 16/16 new real-SQL probes pass (`c3-qa-controller-sql.json`); exact code hashes retained. Q1 actual browser execution and container-level Q3 are blocked on Docker runtime recovery. No repeated unchanged UI proofs, no new video, and no external acceptance. M1/M2 and R1 integration evidence is pending the implementation owner's handoff; G1 remains security-owned.

### Actual recording checkpoint — 2026-09-11

Q1 passes through the production controller function with an explicit direct-TLS test injection and actual pinned recorder; it does not certify a registered fleet launch or external gateway. Q2 adds three actual-recording negatives: final assertion failure, injected trusted-descriptor drift and real SQL fence loss; each quiesces the recorder and leaves no seal/receipt. Q3 repeated cancellation remains the executed real-SQL/injected-stop control. Four new recordings are decoded and linked in report.md at verified media offsets. Total unique controls in this QA checkpoint: 16 SQL/injected boundary cases plus four actual recorder cases. Full external G1 acceptance and integrated M1/M2/R1 final evidence remain separate.
