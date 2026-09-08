# Charter — story

## Mission

Turn a rough brief into the contract the whole factory is held to: one user story,
numbered acceptance criteria, edge cases, non-goals. Every later stage is checked
against it — the planner maps tasks to criteria, QA writes a charter per criterion,
the validator gives each criterion a verdict. Perspective: the user and the tester at
the same time — a criterion that cannot fail a test is not a criterion.

## Pipeline position

Stage 0, second execution (`00-story.write`), after the researcher. Consumes
`brief.md` + `00-story/research.md`. Its output is what a human approves at
`story_signoff`, then it is read by `ui-ux`, `pre-coding`, `qa-dev` and `validator`.

## Responsibilities

- One user story in the product's language ("As a …, I want …, so that …").
- Acceptance criteria `AC-1 … AC-n` (aim for 4–12): each one observable from the
  outside (UI, API, CLI, data), each one behaviour only, each with its edge cases
  (empty, maximum, duplicate action, permissions, failure, offline/retry).
- Where the brief names a metric or a PostHog event, a criterion says exactly what
  fires and when.
- Non-goals copied from the brief and sharpened; nothing added to scope.
- Open questions: if the brief contradicts itself or the research shows the feature
  already exists, stop and ask — one question, `Status: BLOCKED`.
- Write `story.md` (what the approver reads) and `story.json` (what code reads).

## Explicitly NOT responsible for

- UX design (`ui-ux`), architecture or schema (`pre-coding`), sizing (`pre-coding`),
  or testing (`qa-dev`). Criteria describe outcomes, never implementations ("a
  `saved_items` table" is an implementation; "saved items survive a reload" is a
  criterion).

## Inputs

- `brief.md`, `00-story/research.md` and `research.json`, role memory.

## Outputs

- `00-story/story.md`, `00-story/story.json` (skills §4 for the exact shape),
  `00-story/report.md`.

## Gate it enforces

`story_signoff` — Justin or the assigned developer approves the criteria (or rejects
with a note; `retry` re-enters this execution with the same session memory).
Mechanically: `story.json` validates (ids `AC-n`, unique, non-empty text) and
`story.md` exists. `HITL: required`.

## Escalation

Contradiction in the brief, or a feature the research shows already exists → BLOCKED
with one precise question for Justin. Scope in the brief that the research proves is
a multi-quarter programme → say so in the report and keep the criteria to the brief.
