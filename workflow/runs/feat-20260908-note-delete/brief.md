# Feature Brief: Delete a note

- **Product repo:** C:/Users/dimas/AppData/Local/Temp/lantern-d18/notes-service
- **Base branch:** main
- **Working branch:**
- **Coding mode:** auto

## Problem

The notes service can create, read and list notes but has no way to remove one, so a
note written by mistake is permanent. The API documentation has the same gap.

## Desired outcome

A caller can delete a note by id and find out whether it existed, and the API docs
describe deletion alongside the other operations.

## Must-haves

1. Deleting an existing note removes it and reports success.
2. Deleting a note that is not there reports failure instead of raising.
3. The docs describe deletion.

## Non-goals

Soft deletes, undo, bulk deletion, persistence.

---
Proof run for D18 (parallel scoped builders): the plan splits stage 3 into an `api`
builder and a `docs` builder on disjoint surfaces.
