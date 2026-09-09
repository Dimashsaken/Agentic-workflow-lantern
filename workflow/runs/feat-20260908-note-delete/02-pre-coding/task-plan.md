# Task plan — Delete a note

The surfaces are independent, so stage 3 runs two scoped builders in parallel (D18).

## Contract between the builders

`delete_note(note_id: int) -> bool` in `src/api/notes.py`: removes the note and returns
`True` when it existed, returns `False` when it did not, and raises nothing. The `docs`
builder documents exactly this signature; it does not need the code to exist.

## Builder `api` — write scope `src/**`, `tests/**`

1. **Task 1** — add `delete_note(note_id)` to `src/api/notes.py` following the existing
   function style (one-line docstring, no dependencies). Covers AC-1, AC-2.
2. **Task 2** — add tests to `tests/test_notes.py`: deleting an existing note returns
   `True` and removes it from `list_notes()`; deleting an unknown id returns `False` and
   raises nothing. Covers AC-1, AC-2.

## Builder `docs` — write scope `docs/**`

3. **Task 3** — document `delete_note(note_id)` in `docs/api.md` in the existing
   `## Functions` list, stating the return value for both cases. Covers AC-3.

## Definition of code-complete

`python -m unittest discover -q -s tests` is green, all three criteria are implemented,
and no builder has touched a path outside its scope.
