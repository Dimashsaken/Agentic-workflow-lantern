# Delete a note from the store

- **Product repo:** C:/Users/dimas/AppData/Local/Temp/lantern-d22/tiny-notes
- **Base branch:** main
- **Working branch:**
- **Coding mode:** human
- **Requested by:** dimash
- **Date:** 2026-09-09

## Problem

`NoteStore` can add and list notes, and `delete` exists, but nothing tells a caller
whether the note it deleted was the last one, so a UI cannot decide when to show its
empty state without a second call.

## Desired outcome

A caller learns, from the delete call itself, whether the store is now empty.

## Must have

- Deleting a note reports whether the store still holds any notes.
- Deleting an id that is not present is still distinguishable from a successful delete.
- The existing add / list / delete behaviour is unchanged for every current caller.

## Non-goals

- Persistence, concurrency, or any storage change.
- A new module, a new dependency, or a CLI.

## Notes

This brief exists to prove the D22 trace hook end to end on a real model call: the
run's stage-0 research execution must leave a redacted trace file that Mission
Control's execution drawer can read.
