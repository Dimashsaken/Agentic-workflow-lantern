# Blast radius — feat-20260825-role-health

## Planning basis and limitation

The run brief does not identify an external product repository, base branch, assigned developer, or approved UX option. The only implementation currently available in this checkout is Lantern Mission Control (`tools/mission-control/`), which is a pipeline-control UI and does not contain the launch/distribution/calibration product surfaces or role/candidate data required by the brief. Accordingly, the paths below are the verified discovery surface, not a production implementation inventory.

## Verified repository paths

| Path | Classification | Why | Risk |
|---|---|---|---|
| `workflow/runs/feat-20260825-role-health/brief.md` | read | Product requirements and analytics outcomes. | low |
| `workflow/runs/feat-20260825-role-health/01-ui-ux/report.md` | read | Handoff status and unresolved human gates. | high — says brief confirmation and option choice remain required. |
| `workflow/runs/feat-20260825-role-health/01-ui-ux/handoff.json` | read | Lists three presented options and only a recommendation, not a chosen option. | high |
| `workflow/runs/feat-20260825-role-health/01-ui-ux/flow-spec.md` | read | Detailed recommended `diagnosis-brief` states, interactions, and events. | medium |
| `workflow/runs/feat-20260825-role-health/01-ui-ux/options.md` | read | Option trade-offs and recommendation. | medium |
| `tools/mission-control/app.py` | read / no change planned | Checked whether the local web UI is the target. It only renders orchestration runs, gates, artifacts, and audit events; it has no role-health domain. | low |
| `tools/azure-runner/schema.sql` | read / no change planned | Checked local schema for reusable role, candidate, source, trait, or calibration records; none exist. | low |
| `tools/azure-runner/pipeline.py` | read / no change planned | Confirms the local schema and UI serve pipeline orchestration, not the requested product. | low |

## Required product-code trace once the repository is supplied

The developer must not infer these paths. Pre-coding must inspect and classify the actual:

- post-launch `11 · Live` route and its shell/navigation entry;
- role authorization and request-scoping boundary;
- launch/distribution source records (boards, outreach, inbound, referrals);
- candidate pipeline/status history used for volume trends;
- trait definitions, weights, calibration/match scoring, and quality buckets;
- health/stall computation, scheduler/materialization job, cache, and event consumers;
- action handlers for paid renewal, dismissal, retry, and request-access;
- PostHog wrapper and event schemas;
- tests, fixtures, API clients, background jobs, notifications, weekly digest links, and all consumers of modified contracts.

## Consumers and integrations

Known from the design handoff but not traceable without the product repository:

1. The LAUNCH tab replaces/extends the existing Live panel.
2. Lantern can announce changed health from other screens.
3. A weekly digest can deep-link into role health.
4. A suggested action may renew a paid board slot; this touches payments and therefore requires a security pre-review before implementation.
5. PostHog consumes four specified events.

All implementation consumers are currently unknown and therefore **high risk**. Test coverage is likewise unknown; tests must be planned before production changes once the codebase is available.

## Overall blast-radius verdict

**High / unbounded.** The target product code and its git state are absent, so the required file-, caller-, job-, and integration-level inventory cannot be completed reliably.
