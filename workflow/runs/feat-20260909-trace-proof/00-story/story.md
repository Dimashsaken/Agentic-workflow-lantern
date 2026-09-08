# Story — feat-20260909-trace-proof

- **Title:** Delete reports post-delete note state
- **Author:** story agent
- **Date:** 2026-09-09
- **Grounded in:** `00-story/research.md`

## User story

As a caller of `NoteStore`, I want a delete call to report both whether it deleted a note and whether any notes remain, so that a UI can decide whether to show its empty state without making a second call.

## Acceptance criteria

| ID | Criterion (observable, one behaviour) | Edge cases QA must probe |
|----|----------------------------------------|--------------------------|
| AC-1 | When the only stored note is deleted by its id, the delete call reports that deletion succeeded and that no notes remain; listing afterward is empty. | A freshly created store with exactly one note; deleting that note after earlier notes have already been removed. |
| AC-2 | When a stored note is deleted while at least one other note remains, the delete call reports that deletion succeeded and that notes remain; only the targeted note is absent afterward. | Delete the first, middle, and last id from stores with multiple notes; duplicate note text under different ids remains independent. |
| AC-3 | When the requested id is absent, the delete call reports failure in a way distinguishable from either successful-delete outcome and leaves the store unchanged. | Empty store; unknown id in a non-empty store; deleting the same id twice, where the second call reports failure. |
| AC-4 | Existing callers that use a delete result as a boolean success signal continue to observe a truthy result for a successful deletion and a falsy result for a missing id. | Successful deletion when the store becomes empty and when notes remain; repeated deletion becomes falsy only on the second call. |
| AC-5 | Existing add and list behaviour remains unchanged: adding returns increasing integer ids, and listing returns all current `(id, text)` pairs sorted by id. | Add after deleting all notes does not reuse an old id; duplicate and empty note text remain listable as separate notes. |
| AC-6 | After the stage-0 research execution completes, it has a redacted trace artifact that Mission Control's execution drawer can load without exposing configured secret values. | Trace contains a completed model turn and tool activity; configured secret values and sensitive path segments are absent or redacted while the artifact remains readable. |

## Non-goals

- Persistence, concurrency, or any storage change.
- A new module, a new dependency, or a CLI.
- Building or changing a UI; the product checkout contains only the note-store API and its tests.
- Analytics, events, or changes to note text validation.

## Open questions

None.

---
The typed twin of this file is `story.json` (same criteria, same ids). Downstream:
`pre-coding` maps every task to criteria, `qa-dev` writes one charter section per
criterion, `validator` gives each criterion a verdict.
