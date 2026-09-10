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
