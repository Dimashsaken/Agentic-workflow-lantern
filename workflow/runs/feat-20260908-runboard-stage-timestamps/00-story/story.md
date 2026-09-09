# Story — feat-20260908-runboard-stage-timestamps

- **Title:** Runboard stage timestamps
- **Author:** story agent
- **Date:** 2026-09-08
- **Grounded in:** `00-story/research.md`

## User story

As a runboard reader, I want to see when each active run's current pipeline stage last changed, so that I can distinguish recently progressing work from work that may be stalled without opening each run.

## Acceptance criteria

| ID | Criterion (observable, one behaviour) | Edge cases QA must probe |
|----|----------------------------------------|--------------------------|
| AC-1 | Every active run row shows a last-changed value clearly associated with its currently displayed pipeline stage, and the value is visible directly on the runboard without opening run details. | No active runs produces a valid empty active section; a legacy or incomplete run with no trustworthy stage-change time shows an explicit unavailable value rather than a misleading timestamp. |
| AC-2 | The displayed value represents the most recent lifecycle or status change for the current visible stage, rather than a generic update to other run metadata. | The two UI/UX execution phases count as the same visible stage; a human coding stage that reaches a gate without an agent execution still has a stage-change value; editing repository targeting or coding mode alone does not make the stage look newer. |
| AC-3 | After the current stage starts, succeeds, fails, enters or leaves a human gate, or is retried, the next generated runboard reflects the new last-changed value for that run while values for unaffected runs remain unchanged. | Multiple changes in quick succession use the latest one; retrying the same stage advances its value; advancing to a new stage associates the value with the new current stage. |
| AC-4 | Last-changed values use a consistent, scannable date/time or elapsed-age presentation with finer-than-calendar-day precision, so same-day and multi-day stage ages can be compared at a glance. | Two changes on the same date remain distinguishable; ages around 24 hours remain unambiguous; future-skewed timestamps never render as a negative age. |

## Non-goals

- A full execution-attempt or audit timeline on the runboard; detailed history remains in existing run details and persisted records.
- New automatic stalled thresholds, alerts, escalations, or changes to Mission Control's existing stale-review classification.
- Showing or classifying stage age for recently completed runs, which cannot be stalled; this story concerns active run rows.

## Open questions

None.

---
The typed twin of this file is `story.json` (same criteria, same ids). Downstream:
`pre-coding` maps every task to criteria, `qa-dev` writes one charter section per
criterion, `validator` gives each criterion a verdict.
