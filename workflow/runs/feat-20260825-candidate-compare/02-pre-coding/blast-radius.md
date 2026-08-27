# Blast radius — feat-20260825-candidate-compare

## Assessment

**Status: BLOCKED. Overall risk: high while the product repository is unidentified.** The run contains design artifacts but no product repository, base branch, assigned developer, code conventions, schema, or current implementation. Therefore concrete paths, consumers, test coverage, and integration boundaries cannot be traced without guessing.

Chosen flow assumed from the approved gate: **`verdict`**, the stage-1 recommendation. The approval note/actor is not present in the run folder.

## Product-code paths

| path | read/modify/create | why | risk |
|---|---|---|---|
| Product repository (not named) | read | Locate shell, CALIBRATE, IDEAL CANDIDATE, OUTREACH, analytics, API, models, schema, tests, and AGENTS.md | high |
| Product implementation paths | unknown | Cannot classify exact changes until the repository is available | high |

## Control-plane paths examined

| path | read/modify/create | why | risk |
|---|---|---|---|
| `workflow/runs/feat-20260825-candidate-compare/brief.md` | read | Scope, outcomes, states, events | low |
| `workflow/runs/feat-20260825-candidate-compare/01-ui-ux/report.md` | read | Stage-1 findings and handoff | low |
| `workflow/runs/feat-20260825-candidate-compare/01-ui-ux/flow-spec.md` | read | Recommended interaction/state contract | low |
| `workflow/runs/feat-20260825-candidate-compare/01-ui-ux/handoff.json` | read | Options and recommended selection | low |
| `workflow/runs/feat-20260825-candidate-compare/01-ui-ux/jsx/verdict.jsx` | read | Structural design exemplar only; explicitly not production code | low |
| `workflow/runs/feat-20260825-candidate-compare/01-ui-ux/design-system.snapshot.md` | read | UI constraints | low |

## Expected functional surfaces to trace once unblocked

These are search targets, not claimed file paths:

1. CALIBRATE finalist selection and its consumers.
2. Existing per-trait judgments, weights, evidence sourcing state, and score calculation.
3. ICP/weight versioning and stale-judgment detection.
4. Candidate advance/hold transitions and OUTREACH draft creation.
5. Calibration feedback ingestion for the required decision rationale.
6. Conversation-panel prompts/replies and evidence-row focus.
7. PostHog wrapper and event schema.
8. Authorization boundaries for role/candidate evidence and decisions.
9. Background evidence-sourcing jobs/events and cache invalidation.
10. Tests for all above surfaces.

## Consumer and integration audit

Not executable without product code. Required searches include callers and listeners for candidate status changes, role-weight edits, judgment writes, outreach draft creation, evidence completion, analytics dispatch, scheduled sourcing jobs, and any external API clients. Unknown consumers remain **high risk**.

## Test coverage

Unknown. If decision persistence, scoring, or status-transition coverage is thin, characterization tests must precede implementation.

## Security pre-review

Not automatically required from known scope: no auth, payments, or deletion change is stated. Reassess after tracing the product code; candidate evidence and decisions still require tenant/role authorization review.

## Proposed structure and dependencies

Exact structure cannot be named without repository exemplars. Default decision is **no new package**: comparison arithmetic, validation, UI state, and analytics should use the existing stack. Any dependency proposal requires developer sign-off with maintenance, license, size, and transitive-risk evidence.
