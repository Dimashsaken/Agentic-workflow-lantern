# Story — feat-20260908-status-facts

- **Title:** Status JSON carries branch and version facts
- **Author:** story agent
- **Date:** 2026-09-08
- **Grounded in:** `00-story/research.md`

## User story

As an integration consuming pipeline status, I want run and pending-gate JSON to include branch, pipeline-version, and age facts, so that Slack and chat can link work to its branch and distinguish pipeline generations without changing the human-readable status command.

## Acceptance criteria

| ID | Criterion (observable, one behaviour) | Edge cases QA must probe |
|----|----------------------------------------|--------------------------|
| AC-1 | Every run returned by `pipeline.py status --json` contains `product_branch` and `product_working_branch` as their stored string values or JSON `null`, and `pipeline_version` as its stored string value, while retaining every previously reported run field. | The two branch fields independently support null and non-null values; a null stored working branch remains JSON `null` rather than being replaced by a derived branch; runs created by different pipeline generations report their respective stored version strings; no runs produces a valid JSON response with an empty `runs` array. |
| AC-2 | Every pending gate returned by `pipeline.py status --json` contains `age_seconds`, an integer equal to the non-negative whole seconds elapsed from `requested_at` to the time the status output is produced, while retaining every previously reported gate field. | An age below one second is `0`; a future `requested_at` is clamped to `0`; multiple pending gates each receive an integer age; no pending gates produces a valid JSON response with an empty `pending_gates` array. |
| AC-3 | Invoking `pipeline.py status` without `--json` produces byte-for-byte the same human-readable output as before this feature. | Representative populated output; no active runs; no pending gates. |
| AC-4 | One status invocation obtains the run list and pending-gate list with exactly the existing two database reads and introduces no additional query. | Populated and empty result sets; JSON and human-readable modes. |

## Non-goals

- Changing the value stamped into `pipeline_version`, including version-3 or stage-0 stamping work.
- Filtering or pagination.
- A stability promise for the JSON schema.
- Changes to Slack, chat, or Mission Control consumers.
- Resolving a null stored `product_working_branch` into an effective branch in this payload.
- Database schema changes.
- Third-party dependencies or non-ASCII console output.

## Open questions

None.

---
The typed twin of this file is `story.json` (same criteria, same ids). Downstream:
`pre-coding` maps every task to criteria, `qa-dev` writes one charter section per
criterion, `validator` gives each criterion a verdict.
