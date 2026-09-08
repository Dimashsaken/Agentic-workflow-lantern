# Skills — validator

## 1. Session start

Standard reads, then build the ledger before judging anything:

1. `00-story/story.json` → the list of criteria. This is the only list you validate.
2. `02-pre-coding/plan.json` → which task claims which criterion, which criteria were
   deferred (`deferred_criteria`), the `write_scope`.
3. `03-coding/handoff.json` → `files_changed`, commits; `03-coding/report.md` →
   deviations and the confidence map (start your reading where confidence is lowest).
4. `04-qa-dev/test-charter.md`, `bugs.md`, `media-manifest.json` → which criteria were
   exercised, on which video, with what result; which bugs are still open.
5. `05-post-coding/report.md` → findings already made (do not repeat them).
6. `00-story/research.json` → the patterns the build was supposed to imitate.

Then the code: `product_git('diff', ['<base_sha>..<head_sha>', '--stat'])` from the
handoff, and `read_file('product/<path>')` for every changed file that a criterion
depends on. The checkout is on the run's branch — verify with the `<env>` block.

## 2. Decide each criterion

Work the criteria in order. For each one collect three things, then decide:

| code | test | QA evidence | status |
|------|------|-------------|--------|
| implements the text | exists and targets it | charter section + video timestamp shows it | `covered` |
| nothing in the diff | — | — | `missing` |
| implements something else | any | any | `off-spec` (say what differs) |
| plan deferred it with a reason | — | — | `skipped` |
| implements it but exposes auth/data/input risk | any | any | `insecure` |

Rules: a criterion is `covered` only with code **and** evidence that it behaves —
a test or a QA session; a report sentence is neither. Edge cases in the story that
QA did not probe are noted in `evidence` and do not by themselves flip a verdict,
unless the criterion's text is the edge case. Open sev-1/sev-2 bugs against a
criterion make it `off-spec`.

## 3. Findings beyond the verdicts

- Pattern drift: the build ignored an exemplar from `research.json` — finding, not a
  verdict change.
- Scope drift: `files_changed` outside `write_scope` (the handoff gate should have
  refused it; if it passed, say so — that is a pipeline bug worth a memory entry).
- Anything built that no criterion asked for: list it; the reviewer decides whether
  it stays.

## 4. Write the envelope

`05-post-coding/validation.md` follows `workflow/templates/validation.md` (the table
the human reads). `05-post-coding/validation.json`:

```json
{
  "kind": "validation",
  "run_id": "feat-20260908-saved-items",
  "criteria": [
    {"id": "AC-1", "status": "covered",
     "evidence": "src/api/saved.py::save_item + tests/test_saved.py::test_save_once; QA session 1 0:12-0:40 (saved badge without reload)"},
    {"id": "AC-2", "status": "off-spec",
     "evidence": "/saved renders oldest first (src/ui/saved.tsx:41 sorts ascending); QA bug QA-3 sev-2 open"},
    {"id": "AC-3", "status": "skipped",
     "evidence": "plan.json deferred_criteria: PostHog project not provisioned for dev"}
  ],
  "fix_now": [
    {"id": "F-1", "title": "sort /saved newest first", "criterion": "AC-2"}
  ],
  "verdict": "fail"
}
```

Rules the harness enforces: every story criterion appears exactly once; `status` is
one of covered / missing / skipped / off-spec / insecure; `evidence` is never empty;
`verdict` is `pass` only when all are covered and `fix_now` is empty — write the
verdict the statuses imply, it is checked. A `fail` verdict is a correct outcome, not a
failure of your work: the stage stops the run and the fix goes to stage 3.

## 5. Session end

Report per template: the verdict, the count per status, the first fix_now item.
Memory: append the way this product's builds tend to miss criteria (empty states,
telemetry, permissions) so the story writer and QA tighten the next run.
