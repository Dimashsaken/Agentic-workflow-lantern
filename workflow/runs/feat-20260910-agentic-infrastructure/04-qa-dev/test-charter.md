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
