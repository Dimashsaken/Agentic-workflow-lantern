"""Scorers for the factory's own evals (D20) — pure functions, stdlib only.

Each scorer takes envelopes/rows the way they sit in the run folders (or in the frozen
tools/evals/data/*.jsonl) and returns a dict with the metric plus the evidence behind it,
so REPORT.md can show WHY a number is what it is. No model, no database, no network.

    plan_coverage          story criteria → planned or deferred by the plan     (pre-coding)
    validator_agreement    validation verdict vs. what QA actually found       (validator)
    classification_accuracy triage classification vs. the size of the real fix (debug)
    repro_rate             bug runs whose repro stage produced a reproduction  (debug)
"""
from __future__ import annotations

import re

AC_ID = re.compile(r"\bAC-\d+\b")
BUG_HEAD = re.compile(r"^#{2,4}\s*((?:QA|BUG|B)-\d+)\b.*$", re.M | re.I)
SEV = re.compile(r"\bsev-?([1-4])\b", re.I)
RESOLVED = re.compile(r"\b(resolved|fixed|closed|retested?\s*(ok|pass)|verified fixed)\b", re.I)
NO_BUGS = re.compile(r"\b(no|zero)\b[^.\n]{0,40}\b(sev-?1|product bugs|bugs? found|open)", re.I)


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 3) if xs else None


# ── plan coverage ────────────────────────────────────────────────────────────

def plan_coverage(story_ids: list[str], plan: dict | None) -> dict:
    """How much of the story the plan accounts for: a criterion counts when a task
    references it or deferred_criteria names it with a reason."""
    ids = [i for i in (story_ids or []) if isinstance(i, str)]
    if not ids:
        return {"n_criteria": 0, "planned": 0, "deferred": 0, "uncovered": [], "score": None}
    plan = plan or {}
    referenced: set[str] = set()
    for t in plan.get("tasks") or []:
        if isinstance(t, dict):
            referenced.update(c for c in (t.get("criteria") or []) if isinstance(c, str))
    deferred = {d.get("id") for d in (plan.get("deferred_criteria") or [])
                if isinstance(d, dict) and isinstance(d.get("reason"), str) and d["reason"].strip()}
    planned = [i for i in ids if i in referenced]
    deferred_ids = [i for i in ids if i in deferred and i not in referenced]
    uncovered = [i for i in ids if i not in referenced and i not in deferred]
    return {"n_criteria": len(ids), "planned": len(planned), "deferred": len(deferred_ids),
            "uncovered": uncovered, "score": round((len(planned) + len(deferred_ids)) / len(ids), 3)}


# ── validator agreement ──────────────────────────────────────────────────────

def parse_bugs_md(text: str) -> dict:
    """QA's bugs.md → the bugs it lists (id, severity, open?, criteria it names) and how
    many open sev-1/sev-2 there are. Tolerant: the file is prose written by an agent."""
    bugs: list[dict] = []
    heads = list(BUG_HEAD.finditer(text or ""))
    for i, m in enumerate(heads):
        body = text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        head_line = m.group(0)
        sev = SEV.search(head_line) or SEV.search(body)
        status_line = re.search(r"^\s*[-*]?\s*\**Status:?\**:?\s*(.+)$", body, re.M | re.I)
        is_open = not (status_line and RESOLVED.search(status_line.group(1)))
        bugs.append({"id": m.group(1).upper(),
                     "severity": f"sev-{sev.group(1)}" if sev else None,
                     "open": is_open,
                     "criteria": sorted(set(AC_ID.findall(head_line + body)))})
    open_sev12 = sum(1 for b in bugs if b["open"] and b["severity"] in ("sev-1", "sev-2"))
    return {"bugs": bugs, "open_sev12": open_sev12,
            "declares_none": bool(NO_BUGS.search(text or "")) and not bugs}


def validator_agreement(validation: dict | None, qa: dict | None) -> dict:
    """Does the validator's verdict agree with what QA found on the same branch?
    predicted_pass = verdict 'pass'; actual_pass = no open sev-1/sev-2 in bugs.md.
    A criterion the validator marked `covered` while an open bug names it is a conflict."""
    validation = validation or {}
    qa = qa or {"bugs": [], "open_sev12": 0}
    predicted = validation.get("verdict") == "pass"
    actual = int(qa.get("open_sev12") or 0) == 0
    covered = {c.get("id") for c in (validation.get("criteria") or [])
               if isinstance(c, dict) and c.get("status") == "covered"}
    conflicts = sorted({cid for b in qa.get("bugs") or [] if b.get("open")
                        for cid in b.get("criteria") or [] if cid in covered})
    return {"predicted_pass": predicted, "actual_pass": actual,
            "agree": predicted == actual and not conflicts, "criterion_conflicts": conflicts}


# ── classification accuracy ──────────────────────────────────────────────────

def classification_accuracy(rows: list[dict]) -> dict:
    """rows: [{run_id, predicted, truth}] where truth comes from the size of the real fix
    (intake.classify_by_size). Rows without a truth or predicted needs-human are reported
    as unscored, never counted as wrong."""
    scored = [r for r in rows if r.get("truth") and r.get("predicted") not in (None, "needs-human")]
    correct = [r for r in scored if r["predicted"] == r["truth"]]
    confusion: dict[str, dict[str, int]] = {}
    for r in scored:
        confusion.setdefault(r["predicted"], {}).setdefault(r["truth"], 0)
        confusion[r["predicted"]][r["truth"]] += 1
    return {"n": len(scored), "correct": len(correct),
            "accuracy": round(len(correct) / len(scored), 3) if scored else None,
            "unscored": len(rows) - len(scored), "confusion": confusion,
            "misses": [{"run_id": r.get("run_id"), "predicted": r["predicted"], "truth": r["truth"]}
                       for r in scored if r["predicted"] != r["truth"]]}


# ── repro rate ───────────────────────────────────────────────────────────────

def repro_rate(rows: list[dict]) -> dict:
    """rows: [{run_id, reproduced: bool|None}] — one per bug run that reached the repro stage."""
    seen = [r for r in rows if isinstance(r.get("reproduced"), bool)]
    yes = [r for r in seen if r["reproduced"]]
    return {"n": len(seen), "reproduced": len(yes),
            "rate": round(len(yes) / len(seen), 3) if seen else None,
            "not_reproduced": [r.get("run_id") for r in seen if not r["reproduced"]]}


# ── suite-level summaries ────────────────────────────────────────────────────

def summarize_plan(rows: list[dict]) -> dict:
    per = [plan_coverage(r.get("story_ids") or [], r.get("plan")) for r in rows]
    scores = [p["score"] for p in per if p["score"] is not None]
    return {"n": len(scores), "mean_coverage": _mean(scores),
            "full_coverage": sum(1 for s in scores if s == 1.0),
            "runs": [{"run_id": r.get("run_id"), **p} for r, p in zip(rows, per)]}


def summarize_validation(rows: list[dict]) -> dict:
    per = [validator_agreement(r.get("validation"), r.get("qa")) for r in rows]
    return {"n": len(per), "agreement": _mean([1.0 if p["agree"] else 0.0 for p in per]),
            "runs": [{"run_id": r.get("run_id"), **p} for r, p in zip(rows, per)]}


def summarize_triage(rows: list[dict]) -> dict:
    return classification_accuracy([{"run_id": r.get("run_id"), "predicted": r.get("predicted"),
                                     "truth": r.get("truth")} for r in rows])


def summarize_repro(rows: list[dict]) -> dict:
    return repro_rate(rows)


SUMMARIZERS = {"plan": summarize_plan, "validate": summarize_validation,
               "triage": summarize_triage, "repro": summarize_repro}
