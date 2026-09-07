# Skills — coding

These are Lantern's cross-project coding conventions. The product repo's own AGENTS.md
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

## 7. Auto mode — working in the sandbox (D14)

When the fleet runs this role, the product checkout under `product/` is writable, on
the run's branch, and you have `product_shell` — one command at a time in that checkout.
This is "connect to the codebase and work" the way a developer's coding agent does:

1. **Orient in the product, not in Lantern:** `product_shell('cat AGENTS.md CLAUDE.md
   README.md 2>/dev/null | head -200')`, `product_shell('ls')`, `product_git('log',
   ['--oneline','-20'])`. The product repo's own conventions, build and test commands are
   authoritative; the rest of this file yields to them.
2. **The approved plan is the ticket.** Read `02-pre-coding/task-plan.md` (and
   blast-radius.md) and work the tasks in order. A plan that turns out wrong is a
   `Status: BLOCKED` report with one precise question — never a silent re-design.
3. **Edit, run, commit — per task.** `write_file('product/<path>', …)`, then the
   product's own test command through `product_shell`, then
   `product_shell("git add -A && git commit -m '<run-id>: <task> — <message>'")`. Author
   identity and the `Lantern-Agent: coding` trailer are configured for you. Never push,
   never touch other branches, never rewrite history.
4. **Keep commands short and output filtered** — pipe through `head`/`grep`; each command
   has a timeout and the stage has a wall clock. Install dependencies with scripts
   disabled where the stack allows (`npm ci --ignore-scripts`).
5. **Finish like a developer would:** `03-coding/report.md` with the commit list,
   deviations, and the QA confidence map, then `append_memory`. The harness then bundles
   your committed branch into the run folder; the host pushes it and opens the pull
   request a human reviews at `code_complete`. Uncommitted work is auto-committed but
   flagged as such — commit deliberately instead.

Limits you should design around: no network credentials (pushes and publishes fail by
design), Python 3.12 + Node 22 + git in the image, no browser in this stage.
