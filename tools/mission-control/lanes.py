"""Swim lanes for a run (Mission Control v3, D22): one lane per stage execution key,
time flowing to the right, a gate diamond between lanes where the pipeline has one.

The IndyDevDan bar: "sessions as swim lanes, per-phase cost, restart from here". A lane
is a stage key (`00-story.scout`, `03-coding.api`, `03-coding.review` …); each attempt
of it is a bar whose horizontal position is the attempt's ordinal in the run's time
line and whose fill is its duration relative to the longest execution. Executed lanes
come first in the order they started; stages the run has not reached yet trail as
ghost lanes in pipeline order, so a run at stage 0 still shows the whole road ahead.

Pure functions over rows (dicts or asyncpg records) — no database, no HTML in
build_lanes(); render_lanes() turns the model into markup. Tested by test_lanes.py.
"""

from __future__ import annotations

from datetime import datetime

from intake import is_bug_run
from orchestrator import ROLE_FOR_STAGE, tier_for
from pipeline import FEATURE_STAGES, STAGE_DIR, STAGE_INDEX, est_cost_usd
from ui import H, chip, dur, fmt_k, fmt_money

GATE_FOR_STAGE = {s[0]: s[3] for s in FEATURE_STAGES}
STAGE_TYPE = {s[0]: s[2] for s in FEATURE_STAGES}
STAGE_RUNNER_OF = {s[0]: s[4] for s in FEATURE_STAGES}
MIN_WIDTH_PCT = 10          # a 2-second attempt still gets a visible bar
STATUS_KIND = {"succeeded": "ok", "failed": "bad", "running": "run",
               "waiting_gate": "wait", "skipped": "skip", "pending": ""}
STATUS_LABEL = {"succeeded": ("Succeeded", "ok"), "failed": ("Failed", "blocked"),
                "running": ("Running", "ok"), "waiting_gate": ("Waiting", "gate"),
                "skipped": ("Skipped", ""), "pending": ("Pending", "")}
GATE_KIND = {"pending": "wait", "approved": "ok", "rejected": "bad", "expired": "dim"}

# Sub-phases of stage 3 that later sessions add (D18 builders, D19 review loop). Any
# unknown "03-coding.<x>" key is a coding-role lane unless named here.
CODING_PHASE_ROLE = {"review": "reviewer", "fix": "coding", "integrate": "coding",
                     "regate": "coding"}


def role_for(stage: str) -> str:
    role = ROLE_FOR_STAGE.get(stage)
    if role:
        return role
    sdir, _, phase = stage.partition(".")
    if sdir == "03-coding":
        return CODING_PHASE_ROLE.get(phase, "coding")
    return ROLE_FOR_STAGE.get(sdir, "?")


def tier_of(stage: str) -> str:
    return tier_for(role_for(stage), stage)


def pipe_index(stage: str) -> float:
    """Position in the fixed pipeline; sub-phases the pipeline table does not list sit
    just after their stage dir's main key (03-coding.api → 5.5)."""
    if stage in STAGE_INDEX:
        return float(STAGE_INDEX[stage])
    sdir = stage.split(".", 1)[0]
    base = [i for s, i in STAGE_INDEX.items() if s.split(".", 1)[0] == sdir]
    return (max(base) if base else len(STAGE_INDEX)) + 0.5


def seconds_of(e, now: datetime) -> float | None:
    started = e.get("started_at") if hasattr(e, "get") else e["started_at"]
    if not started:
        return None
    end = (e.get("finished_at") if hasattr(e, "get") else e["finished_at"]) or now
    return max(0.0, (end - started).total_seconds())


def _g(row, key, default=None):
    try:
        v = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if v is None else v


def exec_cost(e) -> float:
    return est_cost_usd(_g(e, "input_tokens"), _g(e, "cached_input_tokens"),
                        _g(e, "output_tokens"), _g(e, "model"))


def _new_lane(stage: str, run_id: str) -> dict:
    sdir = STAGE_DIR.get(stage, stage.split(".", 1)[0])
    phase = stage.split(".", 1)[1] if "." in stage else ""
    return {"stage": stage, "dir": sdir, "phase": phase, "role": role_for(stage),
            "tier": tier_of(stage), "human": STAGE_TYPE.get(stage) == "human",
            "runner": STAGE_RUNNER_OF.get(stage, "ec2"), "attempts": [],
            "gate": GATE_FOR_STAGE.get(stage), "approval": None,
            "future": False, "passed_without_execution": False, "current": False,
            "tokens": 0, "cost": 0.0, "seconds": 0.0, "unmetered": 0, "models": [],
            "status": None, "kind": "", "attempt_count": 0, "pipe_index": pipe_index(stage),
            "run_id": run_id}


def build_lanes(run, execs, approvals, now: datetime, traces: set[str] | None = None) -> dict:
    """The lane model for one run.

    run: the runs row; execs: every stage_executions row of the run; approvals: every
    approvals row of the run (all statuses); traces: execution keys with a trace file.
    Returns {"lanes": [...], "columns": n, "executions": n, "retries": n,
             "seconds": total, "cost": total, "tokens": total}.
    """
    run_id = run["id"]
    rows = sorted(execs, key=lambda e: (e["started_at"], _g(e, "attempt", 0), e["id"]))
    max_s = max([seconds_of(e, now) or 0.0 for e in rows] + [1.0])
    lanes: dict[str, dict] = {}
    for slot, e in enumerate(rows, 1):
        key = e["stage"]
        lane = lanes.get(key)
        if lane is None:
            lane = lanes[key] = _new_lane(key, run_id)
        s = seconds_of(e, now)
        exec_key = _g(e, "idempotency_key") or f"{run_id}:{key}:{_g(e, 'attempt', 1)}"
        err = (_g(e, "error", "") or "").splitlines()
        lane["attempts"].append({
            "exec_id": e["id"], "attempt": _g(e, "attempt", 1), "status": e["status"],
            "kind": STATUS_KIND.get(e["status"], ""), "slot": slot,
            "width_pct": max(MIN_WIDTH_PCT, round(100 * (s or 0.0) / max_s)),
            "seconds": s, "started_at": e["started_at"], "finished_at": _g(e, "finished_at"),
            "runner": _g(e, "runner", "ec2"), "model": _g(e, "model"),
            "tokens": _g(e, "total_tokens"), "metered": _g(e, "total_tokens") is not None,
            "cost": exec_cost(e), "error": err[0][:160] if err else "",
            "execution_key": exec_key, "has_trace": bool(traces and exec_key in traces),
        })
    for lane in lanes.values():
        atts = lane["attempts"]
        lane["tokens"] = sum(a["tokens"] or 0 for a in atts)
        lane["cost"] = sum(a["cost"] for a in atts)
        lane["seconds"] = sum(a["seconds"] or 0.0 for a in atts)
        lane["unmetered"] = sum(1 for a in atts if not a["metered"])
        lane["status"], lane["kind"] = atts[-1]["status"], atts[-1]["kind"]
        lane["models"] = sorted({a["model"] for a in atts if a["model"]})
        lane["attempt_count"] = len(atts)
        lane["first_slot"] = atts[0]["slot"]
        lane["last_slot"] = atts[-1]["slot"]

    # Stages the run passed without an execution here (human coding, imports) and
    # stages still ahead: ghost lanes so the whole road is visible.
    #
    # ONLY for a run on the feature pipeline. A bug run walks the debug lifecycle
    # (workflow/DEBUG-LIFECYCLE.md: triage → repro → root-cause → fix → regression →
    # postmortem), so painting the eight feature stages as its road ahead would claim
    # it is going to run a ui-ux stage it will never reach. Its lanes are what it
    # actually executed, and render_lanes says which lifecycle it is on.
    cur = run["current_stage"]
    feature_run = not is_bug_run(run_id) and cur.split(".", 1)[0] in {s[1] for s in FEATURE_STAGES}
    cur_i = pipe_index(cur)
    if feature_run:
        for stage, _sdir, stype, _gate, _runner in FEATURE_STAGES:
            if stage in lanes:
                continue
            lane = lanes[stage] = _new_lane(stage, run_id)
            i = STAGE_INDEX[stage]
            if i < cur_i or (i == cur_i and run["status"] in ("waiting_gate", "done")):
                lane["passed_without_execution"] = True
            elif i == cur_i:
                lane["current"] = True          # queued / executing with no row yet
            else:
                lane["future"] = True
        if cur not in lanes:
            lanes[cur] = _new_lane(cur, run_id)
    if cur in lanes and run["status"] not in ("done", "cancelled"):
        lanes[cur]["current"] = True

    # Gate diamonds: the latest approval row per gate name.
    latest: dict[str, dict] = {}
    for a in sorted(approvals, key=lambda a: (a["requested_at"], a["id"])):
        latest[a["gate"]] = a
    for lane in lanes.values():
        g = lane["gate"]
        if not g:
            continue
        a = latest.get(g)
        if a is not None:
            lane["approval"] = {
                "id": a["id"], "status": a["status"], "kind": GATE_KIND.get(a["status"], ""),
                "requested_at": a["requested_at"], "decided_at": _g(a, "decided_at"),
                "decided_by": _g(a, "decided_by"), "note": _g(a, "decision_note", "") or "",
            }

    # Order: executed lanes by first attempt; lanes without executions sit right after
    # the last executed lane that precedes them in the pipeline (or first).
    def sort_key(lane: dict) -> tuple:
        if lane["attempts"]:
            return (float(lane["first_slot"]), lane["pipe_index"])
        before = [ln["last_slot"] for ln in lanes.values()
                  if ln["attempts"] and ln["pipe_index"] < lane["pipe_index"]]
        return (float(max(before)) + 0.5 if before else 0.0, lane["pipe_index"])

    ordered = sorted(lanes.values(), key=sort_key)
    return {
        "lanes": ordered, "feature_run": feature_run,
        "columns": max(len(rows), 1), "executions": len(rows),
        "retries": sum(max(0, ln["attempt_count"] - 1) for ln in ordered),
        "seconds": sum(ln["seconds"] for ln in ordered),
        "cost": sum(ln["cost"] for ln in ordered),
        "tokens": sum(ln["tokens"] for ln in ordered),
        "unmetered": sum(ln["unmetered"] for ln in ordered),
    }


# ── rendering ────────────────────────────────────────────────────────────────

def _fmt_when(ts) -> str:
    return f"{ts:%b %d %H:%M}" if ts else "—"


def gate_row(lane: dict, gate_short: dict, gate_meta: dict) -> str:
    g = lane["gate"]
    a = lane["approval"]
    label = gate_short.get(g, g)
    title = gate_meta.get(g, (g, ""))[0]
    if a is None:
        kind = "future"
        text = ("not reached yet" if lane["future"] or lane["current"] else
                "no approval row — the stage passed without a gate decision")
        who = ""
        link = ""
    else:
        kind = a["kind"]
        text = {"pending": "waiting on a human", "approved": "approved",
                "rejected": "rejected — stopped for rework",
                "expired": "expired"}.get(a["status"], a["status"])
        who = (f"{a['decided_by']} · {_fmt_when(a['decided_at'])}" if a["decided_by"]
               else f"opened {_fmt_when(a['requested_at'])}")
        link = ("<a href='/gates'>decide ↗</a>" if a["status"] == "pending" else "")
        if a["note"]:
            who += f" · “{H(a['note'][:90])}”"
    return (f"<div class='gaterow {kind}'><span class='dia'>◆</span>"
            f"<span class='gn'>{H(label)}</span><span title='{H(title)}'>{H(text)}</span>"
            f"<span class='who'>{who}</span>{link}</div>")


def render_lanes(model: dict, run_id: str, gate_short: dict, gate_meta: dict,
                 stage_meta: dict) -> str:
    n = model["columns"]
    head = (f"<div class='lhead'><span>Execution · role · tier</span>"
            f"<span>Attempts in time order → ({model['executions']} execution"
            f"{'s' if model['executions'] != 1 else ''})</span>"
            f"<span class='r'>Tokens · est. $ · status</span></div>")
    rows = [head]
    for lane in model["lanes"]:
        cls = "lane" + (" future" if lane["future"] else "") + (" cur" if lane["current"] else "")
        name = stage_meta.get(lane["dir"], (lane["dir"],))[0]
        left = (f"<div class='lname'><div class='k' title='{H(name)}'>{H(lane['stage'])}"
                f"{' <small>human</small>' if lane['human'] else ''}</div>"
                f"<div class='r'>{chip(lane['tier'], 'tier')}<span>{H(lane['role'])}"
                f" · {H(lane['runner'])}</span></div></div>")
        if lane["attempts"]:
            pills = []
            for a in lane["attempts"]:
                label = f"#{a['attempt']} · {dur(a['seconds'])}"
                tip = (f"attempt {a['attempt']} · {a['status']} · {a['runner']} · "
                       f"{_fmt_when(a['started_at'])} → {_fmt_when(a['finished_at'])}"
                       + (f" · {a['error']}" if a["error"] else "")
                       + (" · trace" if a["has_trace"] else " · no trace"))
                pills.append(
                    f"<a class='pill {a['kind']}' style='--slot:{a['slot']};--w:{a['width_pct']}%' "
                    f"href='/run/{H(run_id)}/exec/{a['exec_id']}' data-drawer data-k "
                    f"title='{H(tip)}'><i></i><span>{H(label)}"
                    f"{' ✕' if a['kind'] == 'bad' else ''}</span></a>")
            mid = f"<div class='slots' style='--n:{n}'>{''.join(pills)}</div>"
            st = STATUS_LABEL.get(lane["status"], (lane["status"], ""))
            tok = (fmt_k(lane["tokens"]) + " tok") if lane["tokens"] else "unmetered"
            if lane["unmetered"] and lane["tokens"]:
                tok += f" · {lane['unmetered']} unmetered"
            right = (f"<div class='lright'><span>{H(tok)}</span>"
                     f"<span class='money'>{H(fmt_money(lane['cost']) if lane['tokens'] else '—')}</span>"
                     f"{chip(*st)}</div>")
        else:
            ghost = ("human stage — no execution row; the gate is the stage" if lane["human"]
                     else "passed without an execution here (imported or manual)"
                     if lane["passed_without_execution"]
                     else "queued — waiting for a runner slot" if lane["current"]
                     else "not started")
            mid = f"<div class='slots' style='--n:{n}'><span class='ghost'>{H(ghost)}</span></div>"
            right = "<div class='lright'><span></span><span></span>" + (
                chip("current", "gate") if lane["current"] else "") + "</div>"
        rows.append(f"<div class='{cls}' data-stage='{H(lane['stage'])}'>{left}{mid}{right}</div>")
        if lane["gate"]:
            rows.append(gate_row(lane, gate_short, gate_meta))
    lifecycle = ""
    if not model.get("feature_run", True):
        lifecycle = ("<span>this run is on the <b>debug lifecycle</b> "
                     "(workflow/DEBUG-LIFECYCLE.md), not the feature pipeline — the lanes "
                     "are what it has executed, with no stages ahead assumed</span>")
    legend = ("<div class='lanefoot'>"
              "<span class='sw'><i style='background:var(--success)'></i>succeeded</span>"
              "<span class='sw'><i style='background:var(--danger)'></i>failed</span>"
              "<span class='sw'><i style='background:var(--dawn-3)'></i>running</span>"
              "<span class='sw'><i style='background:var(--accent)'></i>◆ gate</span>"
              "<span>bar fill = duration vs the longest execution · click a bar for the "
              f"compiled prompt, tool calls, report and envelope</span>{lifecycle}</div>")
    return f"<section class='lanes'>{''.join(rows)}</section>{legend}"
