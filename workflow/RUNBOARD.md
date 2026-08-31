# Runboard — the live index of runs

RENDERED from the pipeline database — do not hand-edit. `python pipeline.py runboard`
regenerates it, and every pipeline state change re-renders it automatically. First
thing every agent reads after its role files (orientation step 1 —
`docs/AGENT-TOOLING.md` §5); detail lives in the run folders.

## Active

| Run ID | What | Stage | Status | Waiting on | Updated |
|--------|------|-------|--------|------------|---------|
| feat-20260831-gate-latency | Feature Brief: Gate latency on the board | 01-ui-ux.design | running | runner `workstation` | 2026-08-31 |
| feat-20260825-candidate-compare | Feature Brief: Candidate compare — pick who advances | 02-pre-coding | failed | rework, then `pipeline.py retry` | 2026-08-31 |
| feat-20260825-role-health | Feature Brief: Role health — is this pipeline alive? | 02-pre-coding | failed | rework, then `pipeline.py retry` | 2026-08-31 |

## Recently completed (last 30 days)

| Run ID | What | Completed |
|--------|------|-----------|
| — | | |
