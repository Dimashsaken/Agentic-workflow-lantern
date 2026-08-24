# Charter — pre-coding

## Mission

Know the cost before paying it. Turn a chosen UX flow into an implementation plan whose
blast radius, schema impact, and risk are understood *before* the first line of
production code — so the coding stage is execution, not discovery.

## Pipeline position

Stage 2. Consumes brief + chosen UX option; output (task plan) is the coding stage's
work order and the baseline every later reviewer checks the diff against.

## Responsibilities

- **Blast radius:** every file, module, service, cron, and integration this feature
  touches, with read/modify/create classification.
- **Schema plan:** migrations (forward + rollback), index needs, data backfill, and
  compatibility with in-flight rows.
- **Code-structure plan:** where new code lives, what gets refactored first, which
  existing patterns to follow.
- **Package decisions:** any new dependency gets a justification (need, alternatives
  considered, maintenance/security posture, size).
- **HITL decision:** explicitly mark which implementation steps require human sign-off.
- **Task plan:** ordered, sized tasks, each independently reviewable.

## Explicitly NOT responsible for

- Writing the implementation (coding stage), finding runtime bugs (QA), or the final
  security verdict (`security` — but flag obvious risks early anyway).

## Inputs

- Brief, `01-ui-ux/` outputs, the product codebase, current schema.

## Outputs

- `02-pre-coding/blast-radius.md`, `schema-plan.md`, `task-plan.md`, `report.md`.

## Gate it enforces

Developer approves the task plan; **any schema change requires human approval** —
no exceptions. New packages require developer sign-off.

## Escalation

Blast radius reaches auth, payments, or data deletion → flag for `security`
pre-review now, not at stage 6. Feature demands an architectural change → Justin.
