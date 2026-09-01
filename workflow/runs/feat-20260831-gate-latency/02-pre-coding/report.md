# Stage Report: 02-pre-coding — feat-20260831-gate-latency (attempt 2)

- **Agent/author:** pre-coding
- **Date:** 2026-09-01
- **Status:** PASS-WITH-NOTES

## Summary

Overall risk is medium; this attempt replaces the rejected run-detail-first plan with the corrected `statusline-ledger` Board implementation. No schema or package change is needed. The single riskiest element is changing `snapshot()`'s shared aggregate/result shape without regressing its `/runs` consumer.

## Work performed

- Re-read role guidance, rendered memory/runboard, corrected gate record, complete stage-1 handoff, attempt-1 artifacts, product conventions/history, Mission Control code, schema, tokens, docs, dependencies, tests, and coding principles.
- Traced all consumers of `snapshot()`, `build_card()`, `gate_card()`, and `ago()` and verified the existing scalar `decided` aggregate is not rendered.
- Rewrote blast radius and task plan around the authoritative full-width Board ledger; retained only existing run-detail pending age from the rejected option.

## Findings / results

1. **Corrected authority:** `plan_signoff` rejected attempt 1 because it targeted `run-detail-context`; stage-1 handoff now marks `statusline-ledger` chosen.
2. **Medium risk:** `snapshot()` serves both Board and Runs; the new grouped 30-day result must not break `/runs`.
3. **Existing coverage gap:** Mission Control has no tracked tests, so behavior tests remain the first implementation task.
4. **No schema/package change:** current approval fields and dependencies are sufficient; an index requires separate evidence and approval.
5. **Scope guard:** run detail already shows pending age through `gate_card()`; adding rejected median/evidence composition there would violate the corrected decision.

## Artifacts

- `blast-radius.md` — corrected path inventory, consumer tracing, and risks.
- `schema-plan.md` — no-migration plan and precise 30-day grouped query semantics.
- `task-plan.md` — corrected implementation work order, HITL, and code-complete checklist.

## Handoff notes for the next stage

Start with the behavior tests, then change the shared snapshot aggregate. Implement the full-width ledger between the existing statusline and Board columns, preserve all approval controls, and do not carry forward attempt 1's rejected run-detail redesign. **HITL: required:** developer approves this corrected plan; any index requires a separate schema gate.

## Open questions

None.

## Memory candidates

- A rejected downstream plan followed by a corrected UX decision must trigger a clean re-plan from the authoritative gate record, not an incremental patch to the old plan, because stale scope can otherwise survive in tasks and become accidental implementation.
