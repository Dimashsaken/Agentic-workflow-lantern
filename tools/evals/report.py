"""`pipeline.py evals report` — write tools/evals/REPORT.md (D20).

The report is the artifact the eval rule asks for: the numbers every suite produces on
the frozen data, plus the fingerprint of the watched prompt/gate files it was generated
against. check_pr.py refuses a diff that changes those files unless this file changed
with them and the fingerprint matches — so the numbers can never be older than the
prompts they describe.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import check_pr
import replay

REPORT_NAME = "REPORT.md"


def git_sha(root: Path) -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=root, capture_output=True,
                           text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def _table(rows: list[list[str]], header: list[str]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _fmt(v) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def render(results: dict[str, dict], fingerprint: str, counts: dict[str, int], sha: str,
           generated_at: datetime) -> str:
    lines = ["# Factory evals — REPORT", "",
             f"Generated {generated_at:%Y-%m-%d %H:%M} UTC at commit `{sha}` from frozen data: "
             + ", ".join(f"{n} {k}" for k, n in counts.items()) + ".", "",
             f"<!-- {check_pr.FINGERPRINT_MARK} {fingerprint} -->", "",
             "**The rule (D20):** a diff that touches `agents/**`, `factory.py`, `intake.py`, the scorers, "
             "or the orchestrator's prompt builders / gate functions must regenerate this file "
             "(`pipeline.py evals build && pipeline.py evals report`) in the same change. "
             "`tools/evals/check_pr.py` enforces it from this repo's `lantern.toml` lint command. "
             "A number that moved is the review conversation; a number that did not move is the "
             "evidence the change was safe. `evals run --suite <name> --live` replays the role on "
             "the real model for a before/after — opt-in, costs cents per row.", "",
             "## Summary", ""]
    summary_rows = []
    for suite in replay.SUITES:
        res = results.get(suite)
        if not res:
            summary_rows.append([suite, "—", "0", "—", "n/a"])
            continue
        metric, value = replay.headline(res)
        summary_rows.append([suite, res.get("mode", "frozen"), str(res.get("n_inputs", 0)), metric, value])
    lines.append(_table(summary_rows, ["suite", "mode", "n", "metric", "value"]))
    lines.append("")

    plan = (results.get("plan") or {}).get("summary") or {}
    lines += ["## plan — story criteria the plan accounts for (pre-coding)", ""]
    if plan.get("runs"):
        lines.append(_table([[r.get("run_id"), r.get("n_criteria"), r.get("planned"), r.get("deferred"),
                              ", ".join(r.get("uncovered") or []) or "—", _fmt(r.get("score"))]
                             for r in plan["runs"]],
                            ["run", "criteria", "planned", "deferred", "uncovered", "coverage"]))
    else:
        lines.append("No run with both a story and a plan yet.")
    lines.append("")

    val = (results.get("validate") or {}).get("summary") or {}
    lines += ["## validate — the validator's verdict against what QA found (validator)", ""]
    if val.get("runs"):
        lines.append(_table([[r.get("run_id"), "pass" if r.get("predicted_pass") else "fail",
                              "clean" if r.get("actual_pass") else "open sev-1/2",
                              "yes" if r.get("agree") else "NO",
                              ", ".join(r.get("criterion_conflicts") or []) or "—"] for r in val["runs"]],
                            ["run", "validation", "QA (dev)", "agree", "conflicts"]))
    else:
        lines.append("No run with both a validation.json and a QA bugs.md yet.")
    lines.append("")

    tri = (results.get("triage") or {}).get("summary") or {}
    lines += ["## triage — predicted classification vs. the size of the real fix (debug)", "",
              f"Truth from the coding handoff's diff: trivial ≤ 10 lines, small ≤ 60 (`LANTERN_SMALL_FIX_MAX_LINES`), "
              f"else large; `needs-human` and runs without a fix are unscored. "
              f"Scored: {tri.get('n', 0)}, correct: {tri.get('correct', 0)}, unscored: {tri.get('unscored', 0)}.", ""]
    if tri.get("confusion"):
        truths = sorted({t for row in tri["confusion"].values() for t in row})
        lines.append(_table([[pred] + [str(tri["confusion"][pred].get(t, 0)) for t in truths]
                             for pred in sorted(tri["confusion"])], ["predicted \\ truth"] + truths))
    if tri.get("misses"):
        lines += ["", "Misses: " + "; ".join(f"{m['run_id']} predicted {m['predicted']}, was {m['truth']}"
                                             for m in tri["misses"])]
    lines.append("")

    rep = (results.get("repro") or {}).get("summary") or {}
    lines += ["## repro — bug runs whose repro stage reproduced the defect (debug)", "",
              f"{rep.get('reproduced', 0)} of {rep.get('n', 0)} reproduced"
              + (f"; not reproduced: {', '.join(rep['not_reproduced'])}" if rep.get("not_reproduced") else "")
              + ".", "",
              "## How this file is made", "",
              "1. `pipeline.py evals build` freezes every run folder into `tools/evals/data/*.jsonl`.",
              "2. `pipeline.py evals run --suite <plan|validate|triage|repro> [--live]` scores one suite "
              "(results land in `data/results-<suite>.json`).",
              "3. `pipeline.py evals report` scores every suite on the frozen data (or reuses a fresh "
              "`--live` result) and writes this file with the fingerprint above.",
              "", "Scorers: `tools/evals/scorers.py` (stdlib, tested by `tools/evals/test_evals.py`).", ""]
    return "\n".join(lines)


def write_report(root: Path, data_dir: Path, results: dict[str, dict], counts: dict[str, int] | None = None) -> Path:
    if counts is None:
        counts = {name: len(replay.build.load(data_dir, name)) for name in replay.build.FILES}
    text = render(results, check_pr.fingerprint(root), counts, git_sha(root), datetime.now(timezone.utc))
    path = data_dir.parent / REPORT_NAME
    path.write_text(text, encoding="utf-8", newline="\n")
    (data_dir / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8", newline="\n")
    return path
