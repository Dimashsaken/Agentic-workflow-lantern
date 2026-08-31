# Blast radius — feat-20260825-candidate-compare (attempt 2)

## Assessment

**Status: BLOCKED. Overall implementation risk: high/unbounded.** The configured product checkout is the Lantern delivery control-plane repository itself (`main` at `40a463b`), not a hiring product containing CALIBRATE, candidate judgments, weighted traits, or OUTREACH. The chosen `verdict` UX is confirmed in `gate-decisions.md`, but there is no production feature surface to plan against.

## Paths actually opened

| path | read/modify/create | why | risk |
|---|---|---|---|
| `product/AGENTS.md` | read / no change | Product conventions identify this repository as the agent pipeline control plane. | low |
| `product/README.md` | read / no change | Confirms the repository operates the pipeline, not the candidate product. | low |
| `workflow/runs/feat-20260825-candidate-compare/brief.md` | read / no change | Feature scope and desired analytics. | low |
| `workflow/runs/feat-20260825-candidate-compare/gate-decisions.md` | read / no change | Confirms `verdict` was approved and attempt 1 was rejected as vacuous. | low |
| `workflow/runs/feat-20260825-candidate-compare/01-ui-ux/report.md` | read / no change | Stage-1 handoff constraints. | low |
| `workflow/runs/feat-20260825-candidate-compare/01-ui-ux/flow-spec.md` | read / no change | Interaction, state, and event contract. | low |
| `workflow/runs/feat-20260825-candidate-compare/01-ui-ux/handoff.json` | read / no change | Approved-option artifacts and metadata. | low |
| `agents/coding/skills.md` | read / no change | Coding principles for the eventual work order. | low |

## Repository-wide searches performed

Searched all tracked files for `candidate`, `compare`, `CALIBRATE`, `outreach`, `PostHog`, and `schema`. Hits are briefs/design artifacts, pipeline documentation, and prior blocked planning—not product handlers, models, jobs, UI routes, or tests. The only code/schema present operates Lantern's agent pipeline.

## Missing product surfaces and consumers

The following must be traced in the correct repository before sizing:

1. CALIBRATE route/component and finalist eligibility logic.
2. Candidate, role, weighted-trait, judgment, and evidence models.
3. Score/recommendation calculation and every consumer.
4. ICP/weight updates and stale-judgment invalidation.
5. Advance/hold state transitions and all callers/listeners/jobs.
6. OUTREACH draft creation and navigation contracts.
7. Calibration-feedback persistence for the required rationale.
8. Tenant/role authorization on reads and writes.
9. Evidence-sourcing queues/jobs/events and row-level retry behavior.
10. Analytics wrapper and event-schema consumers.
11. Unit/integration/e2e coverage for all above.

Unknown consumers remain **high risk**. No exact product files may safely be classified as modify/create from this checkout.

## Test coverage

No product tests exist in the configured checkout. In the correct repository, thin coverage around scoring and status transitions requires characterization tests before implementation.

## Structure and packages

No product exemplar can be named. Default is **no new package**; existing UI, validation, analytics, and persistence patterns should be reused. Any new dependency requires developer sign-off after alternatives, maintenance, license, size, and transitive risk are documented.

## Security pre-review

No stated auth, payment, or deletion scope automatically triggers early security review. Reassess after locating authorization and candidate-data boundaries in the correct repository.
