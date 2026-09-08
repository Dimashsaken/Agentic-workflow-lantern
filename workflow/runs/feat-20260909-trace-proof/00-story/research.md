# Research — feat-20260909-trace-proof

## What exists

The product is the in-memory `NoteStore` in `src/notes.py`. It owns a private dictionary and monotonic integer id counter; `add` inserts text and returns the id, `list` returns the sorted `(id, text)` pairs, and `delete` removes by id and returns a `bool` indicating whether removal occurred. There is no persistence, service layer, route, CLI, UI, event, analytics, or other product module in the tracked checkout.

The only traced caller is `tests/test_notes.py`: it imports `NoteStore`, adds one note, lists it, deletes it, and verifies the list is empty. The end-to-end flow present in the repository is therefore `tests/test_notes.py` → `src/notes.py` (`add` → in-memory dictionary → `list` → `delete` → in-memory dictionary → `list`). Repository-wide searches found no other `NoteStore` import or `delete` caller.

## Patterns to imitate

- `src/notes.py` is the exemplar for the product API: one small class, private in-memory state, snake_case methods, built-in type annotations, and direct return values without an intermediate service/model layer.
- `tests/test_notes.py` is the exemplar for verification: standard-library `unittest`, a local store per test, direct method calls, and assertions against public return values and observable list state.

## Similar features

- The existing note lifecycle in `src/notes.py` already provides id allocation, insertion, sorted listing, removal, and a missing-id signal from `delete`; the requested outcome concerns additional state information at that same public operation boundary.
- `tests/test_notes.py` already covers the successful one-note add/list/delete lifecycle and establishes the current successful-delete truthiness and empty-list observations. No second product feature exists in the repository.

## Risks

- **High — public return-contract consumers cannot be fully traced.** `src/notes.py` explicitly annotates `delete` as returning `bool`, while the only in-repository caller in `tests/test_notes.py` checks truthiness. There is no packaging or downstream consumer inventory in the checkout, so external callers relying on exact boolean identity or type cannot be ruled out.
- **Medium — boundary coverage is thin.** `tests/test_notes.py` has one test with one successful deletion. It does not exercise a missing id, deletion while another note remains, repeated deletion, or the exact return value/type, so the distinctions named in the brief are not currently characterized by tests.
- **Low — the requested UI consumer is absent.** `README.md` describes “One module, one test file,” and all tracked product files confirm there is no UI here; product-level research can map only the store contract, not a UI integration.

## Conventions

- `README.md` describes the product as: “A minimal note store used to exercise the Lantern factory. One module, one test file.”
- `lantern.toml` defines the only quality command as `$LANTERN_PYTHON tests/test_notes.py` with a 120-second timeout.
- `tests/test_notes.py` uses standard-library `unittest` and inserts `src` into `sys.path`; no external test framework is present.
- `src/notes.py` uses four-space indentation, snake_case methods, private attributes prefixed with `_`, and built-in generic type annotations.
- No lint, formatting, build, dependency, migration, or feature-flag convention is declared in the four tracked files (`README.md`, `lantern.toml`, `src/notes.py`, `tests/test_notes.py`).

## Likely files

- `src/notes.py` — contains the complete `NoteStore` implementation and the existing `delete` return contract.
- `tests/test_notes.py` — contains the sole product consumer and all current behavioral coverage.
