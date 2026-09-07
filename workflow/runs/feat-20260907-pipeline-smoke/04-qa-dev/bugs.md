# Bugs — feat-20260907-pipeline-smoke (04-qa-dev, attempt 2)

## Product bugs

None found in the executed charter. Zero open sev-1/sev-2/sev-3/sev-4 defects.

## Environment findings

### ENV-1 — Provisioned QA dev credentials (attempt 1)

- **Status:** Resolved in attempt 2.
- **Retest:** `qa-dev` / provisioned password authenticated successfully at `http://172.17.0.1:8080` and redirected to the Board.
- **Evidence:** session 1, 0:00–0:30.

## Coverage notes

- Exact 24h equality, real-DB median interpolation/boundary seeding, failure isolation, and double-submit were not repeated because this smoke attempt had no safe database seeding interface and real gates were explicitly off limits. They remain covered by `tools/mission-control/test_gate_latency.py` and the earlier recorded QA run.
- The only console error was an unrelated missing `/favicon.ico` (404); no application request or JavaScript errors occurred.
