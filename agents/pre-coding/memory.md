# Memory — pre-coding

Long-term judgement for this role. Read fully at session start. Append at session end.

Rules: dated entries, concrete, with the *why*; append-only during runs; no secrets or
customer data. Target: under ~200 lines after consolidation.

## Learnings (append-only, newest last)

- 2026-08-24 (seed): The blast radius that bites is almost never the code you change —
  it's the untracked consumer of the thing you changed. Always grep for callers,
  cron jobs, and webhook/event listeners before sizing.
- 2026-08-24 (seed): Every schema plan ships with a rollback migration written at the
  same time as the forward one; "we'll write it if needed" means it doesn't exist
  during the incident.
