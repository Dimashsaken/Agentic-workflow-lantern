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
