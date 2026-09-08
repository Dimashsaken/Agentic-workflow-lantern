# Skills — story

## 1. Session start

Standard reads. Then `brief.md` (Problem, Desired outcome, Scope, Non-goals,
Constraints), then `00-story/research.md` — the research tells you what already
exists, which turns "build X" into "extend Y", and where the edge cases live. Confirm
`research.json` exists; if the researcher blocked, you block on the same question.

## 2. Derive the criteria

- Start from the brief's Desired outcome: every promise in it becomes at least one
  criterion. Then Scope: every "in" item becomes a criterion or an edge case.
- One criterion = one observable behaviour. Split "users can save and see saved
  items" into two. Merge two criteria that can only be tested together.
- Write each criterion so a tester could fail it: state the actor, the action, the
  visible result, and the limit ("within 1 s", "in save order", "only their own").
  Given/When/Then is fine; plain sentences are fine; vagueness is not.
- Metrics: the brief's PostHog event or KPI gets its own criterion naming the event
  and its properties.
- Cap at ~12. More than that means the brief is two features — say so in the report.

## 3. Edge cases and non-goals

- Per criterion, list the edge cases QA must probe: empty / maximum inputs, the same
  action twice, permissions (another user's data), failure paths (network, timeout),
  refresh mid-flow, mobile viewport if UI. Only the ones that matter for that
  criterion — an edge case list is not a checklist template.
- Non-goals: copy the brief's, then add the tempting extras the research revealed
  ("also export saved items") so nobody gold-plates.

## 4. Write the envelope

`00-story/story.md` follows `workflow/templates/story.md` — the approver reads it in
Mission Control. `00-story/story.json` is the typed twin every later stage reads:

```json
{
  "kind": "story",
  "run_id": "feat-20260908-saved-items",
  "title": "Saved items",
  "user_story": "As a signed-in user, I want to save items from a list, so that I can find them again later without searching.",
  "acceptance_criteria": [
    {"id": "AC-1", "text": "A signed-in user can save any item from the list with one action; the item shows as saved without a reload.",
     "edge_cases": ["saving the same item twice keeps one saved item", "signed-out users see no save control"]},
    {"id": "AC-2", "text": "/saved lists the user's saved items newest first and only theirs.",
     "edge_cases": ["empty state with a clear call to action", "500+ saved items paginate"]},
    {"id": "AC-3", "text": "Saving fires the PostHog event item_saved with {item_id, source: 'list'}.", "edge_cases": []}
  ],
  "non_goals": ["sharing saved lists", "saving from search results"],
  "open_questions": []
}
```

Rules the harness enforces: ids are `AC-<number>`, unique; every `text` is non-empty;
`edge_cases` and `non_goals` are lists (empty allowed). Write with `write_file`, then
re-read to be sure it parses. `story.md` and `story.json` must say the same thing —
the JSON is the contract, the markdown is its readable form.

## 5. Quality bar (before you finish)

For each criterion ask: could QA write a failing test for it today? Does it describe
an outcome, not a mechanism? Does the validator have something to look at (a screen,
a response, an event, a row)? If any answer is no, rewrite it.

## 6. Session end

Report per template: the story title, the criterion count, and what you left out of
scope on purpose. Memory: append the kinds of criteria this product keeps needing
(auth boundaries, telemetry, empty states) so the next story starts from them.
