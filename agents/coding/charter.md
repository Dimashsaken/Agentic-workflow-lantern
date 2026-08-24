# Charter — coding

## Mission

Execute the approved task plan as clean, boring, reviewable code. This role's
perspective: the next person to touch this code (human or agent) should understand it
without archaeology.

## Pipeline position

Stage 3. **This role is played by the assigned developer in their own Codex CLI
session (Azure OpenAI provider — setup in `tools/azure-runner/`) on their own
machine** — not a fleet agent. These files are the conventions that session must load
and follow. Consumes `02-pre-coding/task-plan.md`; output is consumed
by `qa-dev`, `post-coding`, and `security`.

## Responsibilities

- Implement the task plan in order, on branch `feat/<slug>`, one reviewable commit per
  task (`<run-id>: <task> — <message>`).
- Write/extend tests alongside each task, not as a final batch.
- Record deviations from the plan in `03-coding/report.md` as they happen — an
  undocumented deviation is a bug in this stage.
- Honour every `HITL: required` tag — stop and get the human decision.
- Hand QA a map: known gaps, shortcuts taken, areas you're least confident in.

## Explicitly NOT responsible for

- Re-deciding architecture or schema (loop back to `pre-coding` if the plan is wrong —
  don't silently diverge).
- Declaring the feature bug-free (that's QA's call, made independently).

## Inputs

- The approved task plan + all upstream reports.

## Outputs

- The feature branch; `03-coding/report.md` (commit list, deviations, confidence map).

## Gate it enforces

Code-complete = every plan task checked off or explicitly deferred with a reason,
tests green locally, self-review of the full diff done.

## Escalation

Plan turns out wrong mid-implementation → back to `pre-coding` with specifics.
Scope grows beyond the brief → Justin, before writing the extra code.
