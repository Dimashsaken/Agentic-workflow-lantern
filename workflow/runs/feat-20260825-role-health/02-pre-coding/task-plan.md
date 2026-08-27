# Task plan — feat-20260825-role-health

## Status

**BLOCKED — not an executable coding work order.** The prerequisite discovery and approval tasks below are ordered, but implementation tasks cannot be made path-specific, independently reviewable, or safely sized until the target product repository/base branch and chosen UX option are recorded.

## Prerequisites

1. **Confirm brief ownership and target (≤1 hour) — `HITL: required`.** Record Justin’s confirmation, assigned developer, product repository, base branch, and dev/test commands in the run folder. End state: authoritative implementation target exists.
2. **Record UX choice (≤15 minutes) — `HITL: required`.** Approve one of `diagnosis-brief`, `progressive-drilldown`, or `channel-lanes`; do not silently treat the recommendation as approval. End state: one chosen option is named in the gate decision.
3. **Orient to product git state (≤1 hour).** Fetch/prune, inspect remote branches and base history, search commits for this run ID, read product `AGENTS.md`, and list open `agent:pre-coding` PRs. End state: reproducible baseline recorded.
4. **Trace domain and consumers (≤ half day).** Locate Live route, role authz, source/candidate/trait/calibration data, jobs/events/API clients and all callers. Inventory exact paths and tests in `blast-radius.md`. End state: no unknown consumer remains unlabelled; unknowns stay high risk.
5. **Resolve data strategy (≤ half day) — `HITL: required` if schema changes.** Measure representative query plans and choose compute-on-read versus additive materialization; write forward/rollback and deploy compatibility if needed. End state: approved `schema-plan.md`.
6. **Security pre-review of paid action (≤2 hours) — `HITL: required`.** Confirm authorization, price source, confirmation UX, provider idempotency, auditability, and failure semantics for “Renew LinkedIn slot — $99/mo.” End state: security constraints precede coding.
7. **Rewrite implementation work order (≤2 hours) — `HITL: required` for plan signoff.** Replace this blocked plan with exact files, exemplars, package decision, ≤half-day commits, and acceptance tests for the chosen option.

## Expected implementation slices (must be rewritten with exact paths)

These are scope guards, not coding authorization:

1. Tests-first health-state classifier/read model: healthy, stalling, stalled, just-launched, stale, and partial-source failure.
2. Authorization-scoped role-health query/API with bounded query count and explicit stale/partial errors.
3. Chosen Live-panel UI behind a default-off feature flag, imitating the product’s existing route/component/test exemplars.
4. One-action state transitions: paid action confirmation, success/failure, dismissal expiry, retry, and request-access.
5. PostHog events: `role_health_opened`, `health_action_taken`, `health_action_dismissed`, `health_stall_detected`; exclude personal data and validate property enums.
6. Regression coverage for navigation, healthy value, under-20 just-launched semantics, no permission, stale data, one-source failure, and duplicate paid-action submission.

## Package decision

Default: **no new package**. Existing framework/charting/query dependencies cannot be evaluated until the product manifest is available. Any proposed dependency requires developer signoff plus need, existing/stdlib alternatives, maintenance/download posture, license, bundle size, and transitive security review.

## Coding principles most at risk

- **Imitate an exemplar before inventing style:** no product exemplar can be named yet.
- **Errors at boundaries; graceful degradation:** one source must fail locally without hiding other evidence or misreporting health.
- **Feature flag user-visible work, default off:** the Live-panel replacement and paid action must not leak before complete rollout.
- **Tests with each task:** thin/unknown coverage means behavior tests come before classifier, API, and action changes.

## Definition of code-complete

- [ ] Approved brief, UX choice, repository/base, schema plan, and final task plan are recorded.
- [ ] Every final task maps to one reviewable commit and names its tests.
- [ ] All six health/data states and authorization behavior are covered.
- [ ] Paid action is authorized, price-confirmed, idempotent, audited, and failure-safe after security pre-review.
- [ ] No new dependency lacks explicit developer approval.
- [ ] PostHog events fire once with documented, non-sensitive properties.
- [ ] Feature flag defaults off; rollback does not require destructive data changes.
- [ ] Full product test/lint/typecheck commands pass.
- [ ] Coding report records deviations and a three-area confidence map.
