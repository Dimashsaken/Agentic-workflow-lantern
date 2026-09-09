# Reproduction — <run-id>

The human-readable twin of `repro.json`. The test itself lives at
`02-repro/regressions/<file>` in this run folder and will land at
`lantern/regressions/<file>` in the product on the fix branch.

- **Reproduced:** yes / no
- **Regression test:** `lantern/regressions/<file>` — what it asserts and why it fails today
- **Evidence:** the failing assertion / output, or browser session + timestamp

## How the test was derived

From the triage plan and the code read (paths opened), not from the report's snippets.

## Attempts (when not reproduced)

What was tried, with what data, what happened; the instrumentation proposed.
