# Skills — pre-coding

## 1. Session start

Standard reads (charter → skills → memory → run folder). Read
`gate-decisions.md` for the option the `ux_signoff` approver actually chose — the
stage-1 recommendation is not the decision. Then load that option and skim
`01-ui-ux/report.md` handoff notes.

Then orient in the **product repo**, which is checked out read-only under `product/`:
`read_file('product/AGENTS.md')` (or its README) for conventions and commands,
`product_git('log', ['--oneline','-20'])`, `product_git('branch', ['-a'])`, and
`product_git('log', ['--all','--grep','<run-id>'])`. If `product/` is not there, the
run has no product target: report BLOCKED asking for it — never plan against guessed
paths.

## 2. Blast-radius analysis

- Trace the flow through the codebase: entry points, handlers, models, jobs, events,
  analytics. Grep broadly — `product_git('grep', ['-n', '<symbol>'])` searches every
  tracked file — then open the hits with `read_file('product/…')`. List every touched
  path in a table: `path | read/modify/create | why | risk (low/med/high)`.
- **Every path in your report must be one you actually opened.** A plausible path you
  never read is a fabrication, and stage 3 pays for it.
- Explicitly search for consumers of anything you plan to modify — callers, API
  clients, other services, scheduled jobs. Unknown consumers = high risk, say so.
- Note test coverage of each modified area; thin coverage changes the task ordering
  (tests first).

## 3. Schema planning

- For each change: forward migration, rollback migration, behaviour with rows created
  mid-deploy, index/constraint impact, and estimated migration duration on prod-sized
  data. Prefer additive (expand → migrate → contract) over destructive changes.
- If no schema change is needed, `schema-plan.md` says exactly that in one line.

## 4. Structure, packages, principles

- Name the existing pattern each new piece should imitate (file path of the exemplar).
- New package checklist: what it does, stdlib/existing-dep alternative, weekly
  downloads/maintenance, license, transitive risk. Default answer is "no new package".
- Call out the 2–3 coding principles most at risk in this feature (from
  `agents/coding/skills.md`) so the developer sees them upfront.

## 5. Task plan + HITL

- Ordered tasks, each ≤ half a day, each ending in a reviewable/commitable state,
  with dependencies marked. Risky/irreversible steps first-reviewed: tag `HITL: required`.
- End with a "definition of code-complete" checklist QA will hold stage 3 to.

## 6. Session end

Report per template; the report's summary must state the overall risk level and the
single riskiest element. Memory: append any surprise (hidden consumer, misjudged
radius) so it isn't a surprise twice.
