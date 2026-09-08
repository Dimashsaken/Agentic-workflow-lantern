# Runboard — the live index of runs

RENDERED from the pipeline database — do not hand-edit. `python pipeline.py runboard`
regenerates it, and every pipeline state change re-renders it automatically. First
thing every agent reads after its role files (orientation step 1 —
`docs/AGENT-TOOLING.md` §5); detail lives in the run folders.

## Active

| Run ID | What | Stage | Status | Waiting on | Updated |
|--------|------|-------|--------|------------|---------|
| feat-20260909-trace-proof | Delete a note from the store | 00-story.write | waiting_gate | gate `story_signoff` | 2026-09-08 |
| feat-20260908-note-delete |  | 03-coding | waiting_gate | gate `code_complete` | 2026-09-08 |
| feat-20260908-runboard-stage-timestamps |  | 01-ui-ux.diverge | running | runner `ec2` | 2026-09-08 |
| feat-20260908-status-version |  | 03-coding | waiting_gate | gate `code_complete` | 2026-09-08 |
| bug-20260908-help-crash-without-env |  | 02-repro | running | runner `?` | 2026-09-08 |
| feat-20260908-status-facts | Feature Brief: Status JSON carries branch and version facts | 00-story.write | waiting_gate | gate `story_signoff` | 2026-09-08 |
| feat-20260825-demo-export |  | 01-ui-ux.design | waiting_gate | gate `ux_signoff` (rec: background-job) | 2026-09-07 |
| feat-20260825-demo-billing |  | 01-ui-ux.design | running | runner `workstation` | 2026-08-31 |
| feat-20260820-demo-sso |  | 04-qa-dev | running | runner `ec2` | 2026-08-31 |
| feat-20260825-candidate-compare | Feature Brief: Candidate compare — pick who advances | 01-ui-ux.design | waiting_gate | gate `ux_signoff` (rec: verdict) | 2026-08-26 |
| feat-20260825-role-health | Feature Brief: Role health — is this pipeline alive? | 01-ui-ux.design | waiting_gate | gate `ux_signoff` (rec: diagnosis-brief) | 2026-08-26 |

## Recently completed (last 30 days)

| Run ID | What | Completed |
|--------|------|-----------|
| feat-20260810-demo-onboarding |  | 2026-08-31 |
