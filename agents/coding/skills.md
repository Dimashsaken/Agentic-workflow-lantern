# Skills — coding

These are Lantern's cross-project coding conventions. The product repo's own CLAUDE.md
adds project specifics; where they conflict, the product repo wins.

## 1. Session start

Standard reads, then the task plan. Work the plan top-down; don't cherry-pick the fun
tasks.

## 2. Writing code

- Imitate the exemplar file named in the structure plan before inventing style.
- Boring > clever. If a reviewer would pause, add nothing — simplify instead.
- No dead code, no commented-out blocks, no `TODO` without a run-ID reference.
- Errors: handle at the boundary, fail loud in dev, degrade gracefully for users.
- Feature-flag anything user-visible that ships ahead of full rollout; default off.

## 3. Tests

- Each task's commit includes its tests. Test behaviour, not implementation detail.
- Every bug found while coding gets a test that would have caught it — before the fix.

## 4. Commit discipline

- One task, one commit (small fix-up commits are fine before handoff).
- Message: `<run-id>: <short imperative>` + body explaining *why* when non-obvious.
- Never force-push a branch another agent/stage has already read.

## 5. Deviations and HITL

- The moment reality diverges from the plan, note it in `03-coding/report.md` under
  `## Deviations` with the reason. Batch-remembering at the end loses half of them.
- `HITL: required` tasks: present the decision with a recommendation, wait, record the
  answer in the report.

## 6. Handoff to QA (session end)

- Self-review the whole diff in one sitting; fix what embarrasses you.
- Report per template, plus a **confidence map**: the 3 areas most likely to break and
  why — QA starts there. Append memory entries for conventions that proved wrong/missing.
