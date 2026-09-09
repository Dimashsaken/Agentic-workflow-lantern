# Factory evals — REPORT

Generated 2026-09-09 05:10 UTC at commit `5c7d629dd273` from frozen data: 9 briefs, 3 stories, 1 plans, 2 validations, 1 repros.

<!-- lantern-evals-fingerprint: 1dce92c5fcc2e3158c61ee1582b46a5c6cef0292a2c3e968e26e79ff92bd6c23 -->

**The rule (D20):** a diff that touches `agents/**`, `factory.py`, `intake.py`, the scorers, or the orchestrator's prompt builders / gate functions must regenerate this file (`pipeline.py evals build && pipeline.py evals report`) in the same change. `tools/evals/check_pr.py` enforces it from this repo's `lantern.toml` lint command. A number that moved is the review conversation; a number that did not move is the evidence the change was safe. `evals run --suite <name> --live` replays the role on the real model for a before/after — opt-in, costs cents per row.

## Summary

| suite | mode | n | metric | value |
|---|---|---|---|---|
| plan | frozen | 1 | mean plan coverage | 1.00 |
| validate | frozen | 0 | validator vs QA agreement | n/a |
| triage | frozen | 1 | classification accuracy | n/a |
| repro | frozen | 0 | repro rate | n/a |

## plan — story criteria the plan accounts for (pre-coding)

| run | criteria | planned | deferred | uncovered | coverage |
|---|---|---|---|---|---|
| feat-20260908-note-delete | 3 | 3 | 0 | — | 1.00 |

## validate — the validator's verdict against what QA found (validator)

No run with both a validation.json and a QA bugs.md yet.

## triage — predicted classification vs. the size of the real fix (debug)

Truth from the coding handoff's diff: trivial ≤ 10 lines, small ≤ 60 (`LANTERN_SMALL_FIX_MAX_LINES`), else large; `needs-human` and runs without a fix are unscored. Scored: 0, correct: 0, unscored: 1.


## repro — bug runs whose repro stage reproduced the defect (debug)

0 of 0 reproduced.

## How this file is made

1. `pipeline.py evals build` freezes every run folder into `tools/evals/data/*.jsonl`.
2. `pipeline.py evals run --suite <plan|validate|triage|repro> [--live]` scores one suite (results land in `data/results-<suite>.json`).
3. `pipeline.py evals report` scores every suite on the frozen data (or reuses a fresh `--live` result) and writes this file with the fingerprint above.

Scorers: `tools/evals/scorers.py` (stdlib, tested by `tools/evals/test_evals.py`).
