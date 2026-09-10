# Memory — qa-dev

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data. Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-08-24 (seed): Double-submit and back-button-mid-flow find more real bugs per
  minute than any other generic probe — they're in every charter until data proves
  otherwise.
- 2026-08-24 (seed): A video nobody can navigate is write-only. Always pair the link
  with timestamps per scenario; reviewers watch 30 seconds, not 10 minutes.

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-08-26 [manual · -] 2026-08-25: When the requested run folder is absent, stop before browser execution and explicitly leave the QA gate unevaluated, because inventing expected behavior or a target environment can produce a false pass.
- 2026-09-10 [feat-20260910-agentic-infrastructure · manual-engineering-continuation] 2026-09-10: Pair negative provenance tests with a matching controller receipt and forged writable mirror, because an always-unverified UI can falsely pass negative checks without ever displaying valid evidence.
- 2026-09-10 [feat-20260910-agentic-infrastructure · manual-engineering-continuation] 2026-09-10: Verify scenario timestamps against decoded video frames because a Playwright context wall timer may start before captured media, producing offsets outside the final recording.
- 2026-09-10 [feat-20260910-agentic-infrastructure · manual-engineering-continuation] 2026-09-11: Label redacted recorder command traces separately from replayable Playwright traces, because preventing credential capture removes DOM/network evidence and a one-second video cannot replace that diagnostic detail.
