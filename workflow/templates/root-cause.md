# Root cause — <run-id>

The human-readable twin of `rootcause.json`.

- **Cause:** one falsifiable sentence — X fails when Y because Z
- **Evidence:** commit / log line / replay timestamp / test output, each one openable
- **Sibling defects:** the same pattern elsewhere (paths), or "searched: none"

## Fix plan

- **Approach:**
- **Tasks:** ordered, small
- **Write scope:** repo-relative globs the fix may touch
- **HITL:** required / no — why

For a trivial/small bug the harness turns this into `02-pre-coding/plan.json` +
`task-plan.md`; a large bug goes to the planner with this file as input.
