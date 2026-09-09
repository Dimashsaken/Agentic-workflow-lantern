# tools/evals — the factory measures itself (D20)

Boundary's rule for a software factory: every change to the factory ships its own
metrics, and the issue database doubles as the eval set. Here the run folders under
`workflow/runs/` are that database. These tools freeze them, score what the roles
produced, replay a role on the same inputs when you want a before/after, and publish
the numbers where a reviewer sees them.

```bash
python tools/azure-runner/pipeline.py evals build                  # workflow/runs/* → data/*.jsonl
python tools/azure-runner/pipeline.py evals run --suite plan       # score one suite on the frozen data
python tools/azure-runner/pipeline.py evals run --suite triage --live   # replay the role on the real model (opt-in, costs)
python tools/azure-runner/pipeline.py evals report                 # → tools/evals/REPORT.md
python tools/evals/check_pr.py [--base main]                       # the rule, as run by the lint gate
```

Everything except `--live` is local: no database, no model, no network. The same
commands work as `python tools/evals/evals_cli.py …`.

## Suites and scorers (`scorers.py`, stdlib)

| suite | role | input → output | metric |
|-------|------|----------------|--------|
| `plan` | pre-coding | `story.json` (+ brief) → `plan.json` | **plan coverage**: story criteria referenced by a task or deferred with a reason |
| `validate` | validator | `story.json` + QA findings → `validation.json` | **validator agreement**: verdict `pass` ⇔ no open sev-1/2 in `04-qa-dev/bugs.md`; a `covered` criterion an open bug names is a conflict |
| `triage` | debug | `intake/feedback.md` → `triage.json` | **classification accuracy**: predicted `trivial/small/large` vs the size of the real fix (`03-coding/handoff.json` diffstat: ≤ 10 trivial, ≤ 60 small, else large; `needs-human` and unfixed runs are unscored) |
| `repro` | debug | `repro.json` | **repro rate**: bug runs whose repro stage reproduced the defect (frozen only) |

`build.py` writes one JSON row per run into `data/briefs.jsonl`, `stories.jsonl`,
`plans.jsonl`, `validations.jsonl`, `repros.jsonl` — deterministic, so a rebuild with no
new runs is a no-op diff. `replay.py` scores the frozen outputs, or (`--live`) asks the
role — its consult instructions on the reasoning tier, no tools — for a fresh envelope
from the same inputs and scores that; `model_call(role, prompt)` is injectable, which is
how the tests exercise the live path with a fake. `report.py` renders `REPORT.md`.

## The rule (`check_pr.py`)

A diff that touches **`agents/**`** (every role file except the rendered `memory.md` and
`_template/`), **`tools/azure-runner/factory.py`**, **`intake.py`**, **`scorers.py`**, or
— inside `orchestrator.py`, by function name — the **prompt builders**
(`build_instructions`, `PHASE_NOTES`, `product_note`, …) and the **gate functions**
(`check_postconditions`, `check_coding_handoff`, `check_stage_inputs`, …) must include an
updated `tools/evals/REPORT.md`, and the report's fingerprint must match the watched
files as they are now. Editing the report by hand does not pass; regenerating it does.
This repo's `lantern.toml` runs the check in its lint command, so a dogfood coding run
that changes a prompt is red until the agent regenerates the report — the number that
moved is the review conversation.

The base to diff against: `--base`, then `LANTERN_EVALS_BASE`, then
`origin/$LANTERN_PRODUCT_BRANCH` / `$LANTERN_PRODUCT_BRANCH` (what the coding gate has),
then `origin/main` / `main`. No resolvable base → the rule cannot apply, exit 0 with a
note; it never blocks on infrastructure the checkout lacks.

## Reading the numbers

Numbers are only as good as the data: with a handful of runs a suite reports `n/a` or
swings on one row. That is fine — the point is the *delta* when a prompt changes, and
that a change to the factory cannot ship without saying what its numbers are. Grow the
set by running the factory (every finished run is a new row); freeze with `evals build`.

## Adding a suite

1. A scorer in `scorers.py` (pure, with known-answer tests in `test_evals.py`).
2. The rows it needs in `build.rows_for_run` and a loader in `replay.frozen_rows`
   (+ `live_rows` and a role in `ROLE_FOR_SUITE` when the role can be replayed).
3. A summarizer in `scorers.SUMMARIZERS`, a headline in `replay.headline`, a section in
   `report.render`.

Tests: `../azure-runner/.venv/Scripts/python tools/evals/test_evals.py`.
