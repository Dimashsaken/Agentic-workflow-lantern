# Stage Report: 00-story.scout — feat-20260908-runboard-stage-timestamps

- **Agent/author:** researcher
- **Date:** 2026-09-08
- **Status:** PASS-WITH-NOTES

## Summary

Mapped the runboard renderer, lifecycle timestamp sources, stage identity model, adjacent Mission Control age behavior, and test conventions. The riskiest finding is that no single field means “stage last changed,” especially because split stage phases and human coding do not map uniformly to execution rows. The primary exemplar is `tools/azure-runner/pipeline.py`, with `tools/mission-control/app.py` showing the existing per-visible-stage aggregation pattern.

## Work performed

- Read the brief twice and searched the product history for prior work under this run ID; no prior commit was found.
- Traced runboard generation and refresh call sites in `tools/azure-runner/pipeline.py`.
- Opened `tools/azure-runner/schema.sql` and mapped run, stage execution, approval, and event timestamp fields.
- Examined `tools/mission-control/app.py` and `tools/mission-control/ui.py` for latest-stage aggregation, elapsed-time formatting, and existing stale semantics.
- Examined `tools/azure-runner/test_status_json.py` and `tools/mission-control/test_gate_latency.py` for timestamp and operational-age test patterns.
- Confirmed the generated output and its agent-consumer contract in `workflow/RUNBOARD.md` and `docs/AGENT-TOOLING.md`.

## Findings / results

1. **Medium:** `runs.updated_at` is run-level and includes non-stage mutations; stage-specific facts are distributed across execution, approval, and event timestamps.
2. **Medium:** split UI/UX phases share one visible stage directory, while human-mode coding has no execution row.
3. **Medium:** no tracked test directly exercises `render_runboard()` or asserts the rendered table.
4. **Low:** Mission Control has a strict over-24-hour stale rule for pending reviews, but no general stalled/slow rule for the runboard.

## Artifacts

- `research.md` — narrative codebase map, flow, exemplars, risks, conventions, and likely files.
- `research.json` — typed research envelope for downstream stages.
- `report.md` — this execution report.

## Handoff notes for the next stage

Start with the timestamp semantics in `research.md`: the brief's phrase “each stage last changed” cannot be equated automatically with `runs.updated_at`. Preserve the distinction between execution phases, visible stage directories, and human/gate-only transitions when writing acceptance criteria.

## Open questions (BLOCKED status must have exactly one)

None.

## Memory candidates

- 2026-09-08: In Lantern, a visible stage timestamp cannot be derived uniformly from `stage_executions`: split execution phases share a stage directory, while human coding can open a gate without an execution row; stage-age research must trace execution, approval, event, and run clocks before assigning semantics.


## Story phase

- **Agent/author:** story
- **Date:** 2026-09-08
- **Status:** PASS-WITH-NOTES

### Summary

Converted the brief and research into one user story with four observable acceptance criteria covering visibility, stage-change semantics, refresh behavior, and scannable time precision. Because the brief supplied no desired outcome, scope, stale threshold, or non-goals beyond its two must-haves, the story keeps the outcome limited to active rows and does not introduce automatic stalled classification. The story is ready for human `story_signoff`.

### Work performed

- Grounded the contract in `brief.md`, `research.md`, and `research.json`.
- Defined “stage last changed” as the latest lifecycle or status change to the current visible stage, not a generic run metadata update.
- Covered split UI/UX phases, human coding without an execution row, gates, retries, same-day changes, missing timestamps, and clock skew as explicit edge cases.
- Kept a full audit timeline, completed-run age classification, and new stale thresholds or alerts out of scope.
- Re-read `story.md` and `story.json` after writing them and confirmed that their four criteria, IDs, non-goals, and open-question state agree.

### Findings / results

1. **Contract:** Four criteria (`AC-1` through `AC-4`) are independently observable and give QA a visible result to verify.
2. **Scope note:** “Each stage” is expressed as the current visible stage on every active run row; rendering all historical stages would expand the compact runboard into the detailed timeline explicitly left out of scope.
3. **Semantics note:** The stage timestamp must not advance for unrelated run metadata changes, or the runboard could make stalled work appear recent.
4. **HITL:** Human story approval is required before stage 1.

### Artifacts

- `story.md` — readable user story, acceptance criteria, edge cases, non-goals, and open questions.
- `story.json` — typed story envelope with four unique `AC-n` criteria.

### Handoff notes for the next stage

Start with AC-2: the same visible stage can span split execution phases, and human coding can reach a gate without an agent execution. UX work should make the age directly scannable without assuming this story requires an automatic “stalled” badge or threshold.

### Open questions (BLOCKED status must have exactly one)

None.

### Memory candidates

- 2026-09-08: Stage-age criteria must exclude unrelated run metadata updates and cover gate-only stages, because a generic run timestamp can make stalled work appear recent while some legitimate stage transitions have no execution row.
