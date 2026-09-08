# Story — Delete a note

**As a** caller of the notes API **I want** to delete a note by id **so that** a note
written by mistake does not stay forever.

## Acceptance criteria

- **AC-1** — Deleting an existing note removes it from the store and reports that it was
  deleted. Edge case: the note was already deleted.
- **AC-2** — Deleting an id that does not exist reports failure and raises nothing.
  Edge case: an id that was never created.
- **AC-3** — The API documentation describes deletion alongside create, get and list.

## Non-goals

Soft deletes, undo, bulk deletion, persistence.
