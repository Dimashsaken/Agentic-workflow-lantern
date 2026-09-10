"""Traceability matrix (Mission Control v3, D22): the contract at a glance.

Rows are the story's acceptance criteria (00-story/story.json). Columns are what each
later stage did with a criterion: the plan's tasks (02-pre-coding/plan.json), the
coding commits (03-coding/handoff.json and any builder handoffs), the QA charter
sections that name it (04-qa-dev/test-charter.md) and the validator's verdict
(05-post-coding/validation.json). Every cell is a status chip; the row's verdict is
computed, never chosen — the same rule factory.py applies to validation.json.

Matching is by identifier, deliberately: a commit subject or a charter section traces
to a criterion when it names the AC id (or a task id the plan maps to it). Prose
similarity would be a guess dressed as evidence. Pure file reads; tested by
test_traceability.py from fixture envelopes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ui import H, chip

HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)
TASK_NUM_RE = re.compile(r"(\d+)$")


def _json(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def charter_sections(text: str) -> list[dict]:
    """Split a markdown charter into {title, text} sections by heading."""
    if not text:
        return []
    out = []
    matches = list(HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end]
        out.append({"title": m.group(2).strip(), "level": len(m.group(1)),
                    "text": body, "mentions": set(re.findall(r"\bAC-\d+\b", m.group(2) + body))})
    return out


def _mentions(text: str, ac_id: str, task_ids: list[str]) -> bool:
    if re.search(rf"\b{re.escape(ac_id)}\b", text, re.I):
        return True
    for tid in task_ids:
        if re.search(rf"\b{re.escape(tid)}\b", text, re.I):
            return True
        m = TASK_NUM_RE.search(tid)
        if m and re.search(rf"\btask\s*#?{m.group(1)}\b", text, re.I):
            return True
    return False


def load_handoffs(run_root: Path) -> list[dict]:
    """The integrator's handoff plus per-builder handoffs (D18), oldest first."""
    out = []
    for p in [run_root / "03-coding" / "handoff.json",
              *sorted((run_root / "03-coding" / "builders").glob("*/handoff.json"))]:
        data = _json(p)
        if data:
            data["_builder"] = p.parent.name if p.parent.name != "03-coding" else None
            out.append(data)
    return out


def build_matrix(run_id: str, run_root: Path) -> dict:
    story = _json(run_root / "00-story" / "story.json")
    plan = _json(run_root / "02-pre-coding" / "plan.json")
    handoffs = load_handoffs(run_root)
    charter_text = _read(run_root / "04-qa-dev" / "test-charter.md")
    validation = _json(run_root / "05-post-coding" / "validation.json")
    present = {"story": story is not None, "plan": plan is not None,
               "coding": bool(handoffs), "qa": charter_text is not None,
               "validation": validation is not None}
    criteria = [c for c in (story or {}).get("acceptance_criteria", []) if isinstance(c, dict)]
    tasks = [t for t in (plan or {}).get("tasks", []) if isinstance(t, dict)]
    deferred = {d.get("id"): d.get("reason", "") for d in (plan or {}).get("deferred_criteria", [])
                if isinstance(d, dict)}
    commits = [{"sha": str(c.get("sha", ""))[:8], "subject": c.get("subject", ""),
                "builder": h.get("_builder")}
               for h in handoffs for c in (h.get("commits") or []) if isinstance(c, dict)]
    sections = charter_sections(charter_text or "")
    verdicts = {c.get("id"): c for c in (validation or {}).get("criteria", []) if isinstance(c, dict)}

    rows = []
    traced_commits: set[tuple[str, str]] = set()
    traced_sections: set[str] = set()
    for c in criteria:
        ac = c.get("id", "?")
        my_tasks = [t for t in tasks if ac in (t.get("criteria") or [])]
        task_ids = [str(t.get("id")) for t in my_tasks if t.get("id")]
        my_commits = [k for k in commits if _mentions(k["subject"], ac, task_ids)]
        traced_commits.update((k["sha"], k["subject"]) for k in my_commits)
        my_sections = [s["title"] for s in sections if _mentions(s["title"] + "\n" + s["text"], ac, task_ids)]
        traced_sections.update(my_sections)
        verdict = verdicts.get(ac)
        row = {
            "id": ac, "text": c.get("text", ""), "edge_cases": c.get("edge_cases") or [],
            "tasks": [{"id": t.get("id"), "title": t.get("title", ""), "size": t.get("size")} for t in my_tasks],
            "deferred": deferred.get(ac),
            "commits": my_commits, "charter": my_sections,
            "verdict": ({"status": verdict.get("status"), "evidence": verdict.get("evidence", "")}
                        if verdict else None),
        }
        row["plan_state"] = ("deferred" if row["deferred"] is not None else
                             "planned" if my_tasks else
                             "unplanned" if present["plan"] else "pending")
        row["coding_state"] = ("traced" if my_commits else
                               "deferred" if row["deferred"] is not None else
                               "untraced" if present["coding"] else "pending")
        row["qa_state"] = ("charter" if my_sections else
                           "deferred" if row["deferred"] is not None else
                           "uncovered" if present["qa"] else "pending")
        v = row["verdict"]["status"] if row["verdict"] else None
        row["validation_state"] = v or ("unvalidated" if present["validation"] else "pending")
        # the row verdict, computed: complete only when every stage that ran agrees
        bad = (row["plan_state"] == "unplanned" or row["coding_state"] == "untraced"
               or row["qa_state"] == "uncovered" or v in ("missing", "off-spec", "insecure", "skipped")
               or row["validation_state"] == "unvalidated")
        if row["deferred"] is not None and v in (None, "skipped"):
            row["overall"] = "deferred"
        elif bad:
            row["overall"] = "gap"
        elif v == "covered" and my_commits and my_sections and my_tasks:
            row["overall"] = "complete"
        else:
            row["overall"] = "pending"
        rows.append(row)

    notes = []
    unplanned_tasks = [t for t in tasks if not (t.get("criteria") or [])]
    if unplanned_tasks:
        notes.append(f"{len(unplanned_tasks)} plan task(s) map to no criterion: "
                     + ", ".join(str(t.get("id") or t.get("title", "?")) for t in unplanned_tasks[:6]))
    untraced = [k for k in commits if (k["sha"], k["subject"]) not in traced_commits]
    if untraced:
        notes.append(f"{len(untraced)} commit(s) name no criterion or task: "
                     + ", ".join(f"{k['sha']} {k['subject'][:50]}" for k in untraced[:4]))
    orphan_sections = [s["title"] for s in sections if s["level"] >= 2 and s["title"] not in traced_sections]
    if present["qa"] and orphan_sections:
        notes.append(f"{len(orphan_sections)} charter section(s) name no criterion: "
                     + ", ".join(orphan_sections[:5]))
    extra = sorted(set(verdicts) - {c.get("id") for c in criteria})
    if extra:
        notes.append("validation names criteria the story does not define: " + ", ".join(map(str, extra)))
    if validation:
        notes.append(f"validation verdict: {validation.get('verdict', '?')}"
                     + (f" · fix_now {len(validation.get('fix_now') or [])}" if validation.get("fix_now") else ""))

    return {"run_id": run_id, "present": present, "rows": rows, "notes": notes,
            "counts": {k: sum(1 for r in rows if r["overall"] == k)
                       for k in ("complete", "gap", "deferred", "pending")},
            "story_title": (story or {}).get("title", ""), "commit_count": len(commits),
            "task_count": len(tasks), "section_count": len(sections)}


# ── rendering ────────────────────────────────────────────────────────────────

CHIP_KIND = {
    "planned": "ok", "deferred": "warn", "unplanned": "blocked", "pending": "none",
    "traced": "ok", "untraced": "blocked", "charter": "ok", "uncovered": "blocked",
    "covered": "ok", "missing": "blocked", "skipped": "warn", "off-spec": "blocked",
    "insecure": "blocked", "unvalidated": "blocked",
    "complete": "ok", "gap": "blocked",
}


def _cell(state: str, details: list[str]) -> str:
    d = "".join(f"<span class='d' title='{H(x)}'>{H(x)}</span>" for x in details[:4])
    more = f"<span class='d'>… +{len(details) - 4}</span>" if len(details) > 4 else ""
    return f"<div class='cell'>{chip(state, CHIP_KIND.get(state, ''))}{d}{more}</div>"


def evidence_details(value) -> list[str]:
    """Render structured locations and legacy prose without exposing JSON syntax."""
    if not value:
        return []
    if not isinstance(value, list):
        return [str(value)]
    return [str(ref.get("path", "")) + (f":{ref['line']}" if ref.get("line") is not None else "")
            for ref in value if isinstance(ref, dict)]


def render_matrix(m: dict) -> str:
    p = m["present"]
    if not p["story"]:
        return ("<p class='empty' style='margin-top:16px'><b>No story yet.</b> The matrix starts "
                "from 00-story/story.json — the acceptance criteria are the rows everything else "
                "is checked against. Nothing to trace until stage 0 has run.</p>")

    def th(label, key, sub):
        state = "present" if p[key] else "not yet"
        return f"<th>{H(label)}<small>{H(sub)} · {state}</small></th>"

    head = ("<tr><th>AC</th><th>Criterion<small>00-story/story.json · present</small></th>"
            + th("Plan tasks", "plan", "02-pre-coding/plan.json")
            + th("Commits", "coding", "03-coding/handoff.json")
            + th("QA charter", "qa", "04-qa-dev/test-charter.md")
            + th("Validation", "validation", "05-post-coding/validation.json")
            + "<th>Row<small>computed</small></th></tr>")
    rows = []
    for r in m["rows"]:
        edge = f"<small>{len(r['edge_cases'])} edge case(s)</small>" if r["edge_cases"] else ""
        plan_d = [f"{t['id'] or '?'} · {t['title']}" + (f" ({t['size']})" if t.get("size") else "") for t in r["tasks"]]
        if r["deferred"] is not None:
            plan_d = [f"deferred: {r['deferred']}"] + plan_d
        commit_d = [f"{k['sha']} {k['subject']}" + (f" [{k['builder']}]" if k.get("builder") else "") for k in r["commits"]]
        val_d = evidence_details(r["verdict"].get("evidence")) if r["verdict"] else []
        rows.append(
            f"<tr><td class='ac'>{H(r['id'])}</td><td class='txt'>{H(r['text'])}{edge}</td>"
            f"<td>{_cell(r['plan_state'], plan_d)}</td><td>{_cell(r['coding_state'], commit_d)}</td>"
            f"<td>{_cell(r['qa_state'], r['charter'])}</td><td>{_cell(r['validation_state'], val_d)}</td>"
            f"<td>{chip(r['overall'], CHIP_KIND.get(r['overall'], ''))}</td></tr>")
    c = m["counts"]
    summary = (f"<div class='msum'><span><b>{len(m['rows'])}</b> criteria</span>"
               f"<span><b>{c['complete']}</b> complete</span><span><b>{c['gap']}</b> gaps</span>"
               f"<span><b>{c['deferred']}</b> deferred</span><span><b>{c['pending']}</b> pending</span>"
               f"<span>· {m['task_count']} tasks · {m['commit_count']} commits · {m['section_count']} charter sections</span></div>")
    notes = ("<div class='mnotes'>" + "<br>".join(H(n) for n in m["notes"]) + "</div>") if m["notes"] else ""
    return (f"{summary}<div class='mwrap'><table class='matrix'>{head}{''.join(rows)}</table></div>{notes}"
            "<p class='footnote'>A cell traces by identifier only — a commit or charter section counts "
            "for a criterion when it names the AC id or a plan task mapped to it. 'gap' means a stage "
            "that ran left this criterion behind; 'pending' means that stage has not run yet.</p>")
