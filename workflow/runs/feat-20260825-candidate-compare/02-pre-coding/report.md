# Stage Report: 02-pre-coding — feat-20260825-candidate-compare

- **Agent/author:** pre-coding
- **Date:** 2026-08-27
- **Status:** BLOCKED

## Summary

Reviewed the brief and complete stage-1 handoff and produced a bounded provisional plan for the recommended `verdict` flow. Overall risk is **high** because no product repository/base branch, schema, or code conventions are identified; the single riskiest element is making persistence and candidate-status assumptions without tracing existing consumers. Coding must not start until the repository context is supplied and this stage is rerun to produce concrete paths and a definitive schema plan.

## Work performed

- Read the runboard, brief, stage-1 report, handoff, flow specification, options, design-system snapshot, and verdict structural JSX.
- Read the pipeline contract, coding principles, report template, and repository-orientation protocol.
- Checked the Lantern repository root; it is the control plane and contains no linked product repository for this feature.
- Mapped required product surfaces and consumers to inspect, identified schema decision points, defaulted to no new dependency, and sequenced provisional tasks with tests and gates.

## Findings / results

1. **BLOCKER:** The brief/run folder does not name the product repository or base branch, and no product clone is available in this workspace. Exact blast radius, callers/listeners/jobs, test coverage, schema, exemplars, and commands therefore cannot be established.
2. **HIGH:** Decision rationale and candidate-state persistence may require schema work, but existing models are unavailable. Any migration remains `HITL: required` and cannot be approved from speculation.
3. **MEDIUM:** Stage 1 recommends `verdict`, but the run artifacts do not include the human gate decision/note. Planning assumes `verdict`; this must be verified against pipeline state.
4. **NOTE:** No new package is expected. Any package proposal requires developer sign-off.

## Artifacts

- `blast-radius.md` — known control-plane inputs, missing product-code radius, and required consumer audit.
- `schema-plan.md` — blocked schema assessment and mandatory completion criteria.
- `task-plan.md` — provisional ordered tasks, HITL rules, risk principles, and code-complete checklist.
- `report.md` — stage verdict and precise unblock request.

## Handoff notes for the next stage

Do not begin stage 3 from this provisional plan. After the product repository/base branch is linked and available, rerun pre-coding to replace search targets with exact paths/exemplars, trace all consumers, measure test coverage, and finalize the schema decision.

## Open questions (BLOCKED status must have exactly one)

What is the product repository URL/local clone path and base branch for this run (with its `AGENTS.md` and current schema available to the pre-coding agent)?

## Memory candidates

- 2026-08-27: A feature brief must identify the product repository and base branch before pre-coding, because otherwise exact blast radius, consumer tracing, schema impact, and executable task paths cannot be established without guessing.
