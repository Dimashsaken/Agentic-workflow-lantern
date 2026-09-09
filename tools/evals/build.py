"""`pipeline.py evals build` — turn past run folders into frozen eval data (D20).

The run folders under workflow/runs/ are the factory's issue database and its eval set
at once (Boundary's rule: every past issue is a test case). This module reads what the
stages actually wrote — envelopes, QA bug lists, coding handoffs — and freezes them as
one JSON row per run under tools/evals/data/*.jsonl, so a prompt or gate change can be
replayed against the same inputs and scored the same way.

    briefs.jsonl        run_id, kind, title, brief (markdown)
    stories.jsonl       run_id, story (story.json)
    plans.jsonl         run_id, story_ids, plan (plan.json)
    validations.jsonl   run_id, validation (validation.json), qa (parsed 04-qa-dev/bugs.md)
    repros.jsonl        run_id, feedback, triage, repro, lines_changed, predicted, truth
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "azure-runner"))
import intake  # noqa: E402  (pure functions: classify_by_size, lines_changed, feedback_body)
import scorers  # noqa: E402

FILES = ("briefs", "stories", "plans", "validations", "repros")


def _json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _title(brief: str) -> str:
    for line in brief.splitlines():
        if line.lstrip().startswith("#"):
            return line.lstrip("# ").strip()
    return ""


def rows_for_run(rd: Path) -> dict[str, dict]:
    """Every jsonl row one run folder contributes, keyed by file name."""
    run_id = rd.name
    out: dict[str, dict] = {}
    brief = _text(rd / "brief.md")
    if brief:
        out["briefs"] = {"run_id": run_id, "kind": "bug" if intake.is_bug_run(run_id) else "feat",
                         "title": _title(brief), "brief": brief}
    story = _json(rd / "00-story" / "story.json")
    story_ids = [c.get("id") for c in (story or {}).get("acceptance_criteria", [])
                 if isinstance(c, dict) and isinstance(c.get("id"), str)]
    if story:
        out["stories"] = {"run_id": run_id, "story": story}
    plan = _json(rd / "02-pre-coding" / "plan.json")
    if plan:
        out["plans"] = {"run_id": run_id, "story_ids": story_ids, "plan": plan}
    validation = _json(rd / "05-post-coding" / "validation.json")
    bugs_md = _text(rd / "04-qa-dev" / "bugs.md")
    if validation or bugs_md:
        out["validations"] = {"run_id": run_id, "story_ids": story_ids, "validation": validation,
                              "qa": scorers.parse_bugs_md(bugs_md) if bugs_md else None,
                              "has_qa": bool(bugs_md)}
    if intake.is_bug_run(run_id):
        triage = _json(rd / "01-triage" / "triage.json")
        repro = _json(rd / "02-repro" / "repro.json")
        handoff = _json(rd / "03-coding" / "handoff.json")
        lines = intake.lines_changed(handoff)
        fb = rd / intake.INTAKE_DIR / intake.FEEDBACK_FILE
        out["repros"] = {
            "run_id": run_id,
            "feedback": intake.feedback_body(_text(fb)) if fb.is_file() else None,
            "triage": triage, "repro": repro,
            "reproduced": repro.get("reproduced") if repro else None,
            "lines_changed": lines,
            "predicted": (triage or {}).get("classification"),
            "truth": intake.classify_by_size(lines),
        }
    return out


def build(runs_root: Path, out_dir: Path) -> dict[str, int]:
    """Write the five jsonl files; returns row counts. Deterministic (sorted by run id)
    so a rebuild with no new runs is a no-op diff."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: dict[str, list[dict]] = {name: [] for name in FILES}
    if runs_root.is_dir():
        for rd in sorted(p for p in runs_root.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
            for name, row in rows_for_run(rd).items():
                rows[name].append(row)
    counts: dict[str, int] = {}
    for name in FILES:
        path = out_dir / f"{name}.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows[name]),
                        encoding="utf-8", newline="\n")
        counts[name] = len(rows[name])
    return counts


def load(out_dir: Path, name: str) -> list[dict]:
    path = out_dir / f"{name}.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows
