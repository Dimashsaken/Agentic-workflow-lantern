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

1. **You are already oriented — check before you re-fetch (D15).** The end of your
   system prompt carries the `<env>` block (repo, origin, base branch, the branch you
   are on, working-tree state, recent commits) and the product's own `AGENTS.md`,
   `CLAUDE.md` and `README.md`, auto-loaded. Those conventions, build and test commands
   are authoritative and the rest of this file yields to them. Read the full file only
   when the block says it was **truncated** and you need a section that was cut —
   `read_file('product/AGENTS.md')`. Spend your first turns on `list_dir('product')` and
   `product_git('grep', …)` for the code you are about to change, not on re-reading docs
   you already have. Note the branch you are on: if it already had commits, only the
   ones **you** add count as this stage's work.
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

6. **The gate runs after you (D17).** The product's `lantern.toml [quality]` commands
   (test / lint / typecheck / build) run as code from the product root, plus a check
   that every changed path is inside the plan's `write_scope`. Red results come back to
   you — failures only — for at most `LANTERN_FIX_ROUNDS` rounds (default 3): fix,
   re-run the failing command yourself, commit, reply. Still red = the stage fails and
   nothing is handed off. The exact commands and the scope are in "The gate your branch
   must pass" at the end of your prompt — run them before you finish. A product with no
   `lantern.toml` gets no code gate: run its own test command through product_shell and,
   if the plan allows, add one (template: `workflow/templates/lantern.toml`).

7. **You may be ONE builder of several (D18).** When the approved plan carries a
   `builders` list, stage 3 runs one agent per builder in parallel and the top of your
   prompt says which one you are, with your tasks, your acceptance criteria and your
   write scope. What changes for you:
   - **Your branch is `<run branch>--<your name>`**, not the run's branch. Your siblings
     are committing to theirs right now; you cannot see, fetch or merge their work, and
     nothing of theirs will ever appear in your checkout. Do not look for it, do not wait
     for it, do not `git log` for it.
   - **Build against the plan's contract, not their code.** If your task needs an
     endpoint, a type or a prop another builder owns, the plan must already describe it
     — code to that description. If the plan is silent, that is a planning gap, so write
     `Status: BLOCKED` with the one question rather than guessing or reaching across.
   - **Stay inside your scope.** It is narrower than the plan's, it is enforced on every
     commit, and a path outside it fails your handoff — that path belongs to a sibling.
     Spotting a real bug in their area is a line in your report, not a commit.
   - **Your files are yours:** report, gate and handoff live in
     `03-coding/builders/<your name>/`, not in the stage directory. That is deliberate —
     a shared `report.md` would race on its last `Status:` line.
   - When every builder is done the HOST merges the branches in plan order (`--no-ff`)
     and runs ONE integrator execution on the merged result.

8. **Or you may be the integrator.** Then the merge already happened and you are standing
   on the merged branch. Your job is only to **make it green**: the seam problems that no
   builder could see alone — a symbol renamed on one side, two copies of the same helper,
   an import that now resolves differently, a test that passes alone and fails beside its
   neighbour. Read `03-coding/builders.json` and each `03-coding/builders/<name>/report.md`
   first. You have the union of their scopes, and your handoff is the stage's handoff —
   the branch the host pushes and opens the PR from. Do not re-implement their tasks or
   redesign their work; if the merged result is wrong in a way you cannot fix at the seam,
   say so with `Status: BLOCKED`.

Limits you should design around: no network credentials (pushes and publishes fail by
design), Python 3.12 + Node 22 + git in the image, no browser in this stage.

## 9. Fix executions — after the review bot, or after the merge babysitter (D19)

A `03-coding.fix` execution is you again, on the same branch, with every earlier commit
in place — and a different task. The end of your prompt says which:

- **The review's must-fix list.** The `reviewer` requested changes; its findings are
  in `03-coding/review/round-<n>.md` and the ones you must resolve are listed in your
  task block (id, severity, file:line, summary, suggestion). Work that list, not the
  plan: a test for every behaviour change, one commit per id (`<run-id>: fix R-1 — …`),
  the gate commands run by you before you finish, then a `## Fix — round <n>` section
  APPENDED to `03-coding/report.md` (own `- **Status:**` line) saying per id what
  changed. Disagree with a finding? Say so under its id in the report and leave the
  code; the next review round decides. The reviewer reviews again afterwards; the
  human sees the branch only when it approves or the rounds run out.
- **A red regate.** The merge babysitter merged the base into your branch after a human
  approved `code_complete`, and the product's quality commands went red. Fix what the
  merge broke and nothing else — no features, no plan tasks — commit, and append a
  `## Regate fix` section. The failures (only) are in your task block.

Same rules as §7 otherwise: never push, never touch another branch, never rewrite
history; the handoff is a bundle of your commits since this execution started, so an
execution that commits nothing fails honestly.
