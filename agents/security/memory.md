# Memory — security

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data (and no unpatched-vuln details — those live outside the repo until fixed).
Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-08-24 (seed): Read the authz check in the handler itself. "The middleware
  covers it" is the assumption behind most IDOR findings.
- 2026-08-24 (seed): The lockfile diff is part of the diff. New transitive dependencies
  arrive silently and are nobody's explicit decision unless this role makes them one.

<!-- ENTRIES BELOW ARE RENDERED FROM THE role_memory TABLE — do not edit here; agents use append_memory, humans consolidate upward and re-run `pipeline.py render-memory` -->

- 2026-08-26 [manual · -] 2026-08-25: For authentication features, an unidentified release branch is itself a no-go condition because endpoint authorization, dependency provenance, staging secrets, and rollback behavior cannot be inferred from feature intent.
- 2026-09-10 [feat-20260910-agentic-infrastructure · manual-engineering-continuation] 2026-09-10: Before/after source hashes cannot establish what a test executed when that source remains writable; use a separate read-only committed snapshot and separately fence every future-authoritative write, including role memory.
