# Task plan — feat-20260825-candidate-compare

## Status

**BLOCKED. This is a provisional sequencing framework, not an approved coding work order.** Concrete files, exemplars, commands, dependencies, and schema steps require the product repository/base branch and its AGENTS.md.

## Decisions carried forward

- UX: `verdict` (assumed from stage-1 recommendation; verify gate record).
- Compare only 2–3 `Yes` finalists; no new scoring model.
- Required one-line rationale for every advance/hold action.
- Never invent evidence; sourcing, stale weights, tie, and row-error states are first-class.
- Default: no new package.

## Ordered tasks after repository orientation

1. **Repository characterization and contract tests — ≤0.5 day**
   - Identify exact shell, CALIBRATE, scoring, evidence, candidate transition, OUTREACH, analytics, authz, and schema paths.
   - Name production exemplars and run documented tests.
   - Add characterization tests first where coverage is thin.
   - Commit state: tests document current finalist, scoring, and transition behavior.

2. **Finalize data/schema design — ≤0.5 day; depends on 1**
   - Decide where rationale, decision metadata, and ICP-weight version live.
   - Complete forward/rollback/index/backfill/mid-deploy analysis if needed.
   - **HITL: required if any schema change is proposed. Stop for approval before migration/code.**

3. **Comparison read model/API — ≤0.5 day; depends on 1–2**
   - Reuse existing weighted judgments; return 2–3 authorized finalists, evidence states, source weight version, totals/recommendation, tie/stale/provisional flags.
   - Test tenant/role authorization, fewer-than-two, third finalist, tie, partial sourcing, stale weights, and row-level failures.
   - Commit state: independently testable comparison contract.

4. **Decision command and OUTREACH handoff — ≤0.5 day; depends on 2–3**
   - Validate nonblank one-line rationale server-side; atomically persist advance/hold and calibration feedback.
   - Make retries idempotent and preserve held-candidate behavior.
   - Advance opens/creates the existing outreach draft through the established pattern.
   - Test invalid/unauthorized/stale/repeated submissions and partial failures.
   - Commit state: decision lifecycle works without the new UI.

5. **Verdict comparison UI — ≤0.5 day; depends on 3**
   - Add CALIBRATE entry points and implement the existing product shell using product components/tokens, not the Paper JSX as production code.
   - Render recommendation, weighted totals, 2–3 candidate evidence table, and named consequence CTAs.
   - Test accessibility and responsive bounds at the desktop target.
   - Commit state: happy path is reviewable behind the existing feature-flag pattern if one exists.

6. **Decision/rebalance interactions — ≤0.5 day; depends on 4–5**
   - Add required inline rationale, advance/hold outcomes, conversation evidence focus, rebalance-return flow, and outreach navigation.
   - Test submit locking, retry, keyboard flow, and stale-response handling.
   - Commit state: end-to-end decision path is reviewable.

7. **Non-happy states — ≤0.5 day; depends on 5–6**
   - Implement `<2`, three-finalist, sourcing/provisional, stale weights, tie, and row-level retry states exactly as the flow spec describes.
   - Commit state: each state has behavioral tests/stories according to repo convention.

8. **Analytics — ≤0.5 day; depends on 3–7**
   - Emit `compare_opened`, `compare_decision`, and `compare_rebalanced` through the existing analytics wrapper.
   - Compute `seconds_from_open` without trusting client input for durable business logic; exclude rationale text and evidence from analytics payloads.
   - Verify event names/properties and duplicate suppression.
   - Commit state: analytics contract is tested.

9. **Integration/self-review — ≤0.5 day; depends on all**
   - Run repository-required unit/integration/e2e/type/lint checks.
   - Self-review full diff, document deviations and confidence map, and confirm feature-flag default if applicable.
   - Commit state: code-complete handoff.

## Coding principles most at risk

1. **Imitate named exemplars before inventing style** — exemplars cannot be selected until product code is available.
2. **Handle errors at boundaries and degrade gracefully** — partial evidence and row errors must not collapse the entire comparison.
3. **Test behavior with each task** — scoring, stale weights, required rationale, and status transitions are contract-heavy and unsafe to defer.

## Definition of code-complete

- [ ] Exact repository paths and exemplars replace all provisional targets.
- [ ] Approved UX selection is confirmed from the gate record.
- [ ] Schema plan is finalized; any schema/package change has recorded human approval.
- [ ] Authorized 2–3 finalist comparison uses existing judgments/weights only.
- [ ] Required rationale is validated and durably feeds calibration.
- [ ] Advance hands off to the existing OUTREACH draft flow; hold remains visible in CALIBRATE.
- [ ] All specified empty/loading/error/stale/tie/third-finalist states work.
- [ ] PostHog events match the flow spec and contain no rationale/evidence text.
- [ ] Tests, type checks, lint, and product-required commands pass.
- [ ] No dead code/TODOs; self-review and deviations are recorded in stage 3.
