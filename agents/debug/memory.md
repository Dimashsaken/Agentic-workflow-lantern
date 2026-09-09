# Memory — debug

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data. Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-08-24 (seed): Correlate first-occurrence time with deploy history *before*
  reading code — it shrinks the suspect surface from the whole codebase to a handful
  of commits.
- 2026-08-24 (seed): A fix without a formerly-failing test is a hypothesis, not a fix.

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-09-08 [bug-20260908-help-crash-without-env · 01-triage] 2026-09-08: CLI help and parser-error paths should be tested with external-service credentials removed, because eager client construction can turn a local diagnostic path into a credential traceback before argparse runs.
