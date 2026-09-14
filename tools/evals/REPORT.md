# Factory evals — REPORT

Generated 2026-09-14 08:40 UTC at commit `811a24793b90` from frozen data: 12 briefs, 5 stories, 2 plans, 3 validations, 1 repros.

<!-- lantern-evals-fingerprint: be6d3fe7743d5b4634e06b12f817e17c5c1ff7bdd5d053eb4b7ff240a13f951f -->

**The rule (D20):** a diff that touches `agents/**`, `factory.py`, `intake.py`, the scorers, or the orchestrator's prompt builders / gate functions must regenerate this file (`pipeline.py evals build && pipeline.py evals report`) in the same change. `tools/evals/check_pr.py` enforces it from this repo's `lantern.toml` lint command. A number that moved is the review conversation; unchanged frozen scores only describe the existing corpus and do not establish runtime safety. `evals run --suite <name> --live` replays the role on the real model for a before/after — opt-in, costs cents per row.

## Summary

| suite | mode | n | metric | value |
|---|---|---|---|---|
| plan | frozen | 2 | mean plan coverage | 1.00 |
| validate | frozen | 0 | validator vs QA agreement | n/a |
| triage | frozen | 1 | classification accuracy | n/a |
| repro | frozen | 0 | repro rate | n/a |

## plan — story criteria the plan accounts for (pre-coding)

| run | criteria | planned | deferred | uncovered | coverage |
|---|---|---|---|---|---|
| feat-20260908-note-delete | 3 | 3 | 0 | — | 1.00 |
| feat-20260908-status-version | 2 | 2 | 0 | — | 1.00 |

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

## Gate integrity — labelled negative and positive controls

Invalid records accepted: **0/14**. Valid records rejected: **0/1**.

Checks cover missing tests/results, identity mismatch, contradictory exit codes, truthy strings, duplicate commands and missing policy fingerprints. These are deterministic verifier fixtures, not production false-green rates, live model evaluations, or proof of OS isolation. Regression tests also exercise the command runner, SDK tools, evidence resolver and both execution paths.
