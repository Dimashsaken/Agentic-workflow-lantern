"""Cost (Mission Control v3, D22): per run, per day, per model, and the tripwires.

Same ledger as `pipeline.py usage` / `usage-check` (P0.4): stage_executions token
columns are exact, dollars are estimates from est_cost_usd(); NULL tokens are
"unmetered" and never $0.00. The tripwire block reuses the two ceilings of
cmd_usage_check — today's spend against LANTERN_DAILY_SPEND_ALARM_USD and the
cumulative draw against 25/50/75 % of LANTERN_CREDIT_POOL_USD (+ the pre-ledger offset)
— and shows whether each alarm has already fired (events actor='usage-check').

Aggregation here is pure over the grouped rows the routes fetch; tested by
test_cost.py without a database.
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from pipeline import est_cost_usd
from ui import H, chip, fmt_int, fmt_money

POOL_THRESHOLDS = (25, 50, 75)


def _f(v, default=0):
    return default if v is None else v


def aggregate(rows, key: str) -> list[dict]:
    """Group per-model aggregate rows (fields: key, model, inp, cached, outp, n, unmetered)
    by `key`, summing tokens and cost. Rows with no model and no tokens are the
    unmetered pile; they count executions, never dollars. Sorted by cost, descending."""
    out: dict = {}
    for r in rows:
        k = r[key]
        g = out.setdefault(k, {key: k, "cost": 0.0, "inp": 0, "cached": 0, "outp": 0,
                               "n": 0, "unmetered": 0, "models": set(), "metered_n": 0})
        g["n"] += int(_f(r["n"]))
        g["unmetered"] += int(_f(r["unmetered"]))
        if r["model"] is None and not _f(r["inp"]):
            continue
        g["cost"] += est_cost_usd(r["inp"], r["cached"], r["outp"], r["model"])
        g["inp"] += int(_f(r["inp"]))
        g["cached"] += int(_f(r["cached"]))
        g["outp"] += int(_f(r["outp"]))
        g["metered_n"] += int(_f(r["n"])) - int(_f(r["unmetered"]))
        if r["model"]:
            g["models"].add(r["model"])
    result = list(out.values())
    for g in result:
        g["models"] = sorted(g["models"])
        g["cached_pct"] = round(g["cached"] / g["inp"] * 100) if g["inp"] else None
    result.sort(key=lambda g: (-g["cost"], str(g[key])))
    return result


def tripwire(today_cost: float, alltime_cost: float, env: Mapping[str, str],
             alarm_events=()) -> dict:
    """The two ceilings of pipeline.cmd_usage_check, with what has already fired.
    alarm_events: events rows (type, data, at) written by actor 'usage-check'."""
    daily_limit = float(env.get("LANTERN_DAILY_SPEND_ALARM_USD") or "50")
    pool = float(env.get("LANTERN_CREDIT_POOL_USD") or "25000")
    offset = float(env.get("LANTERN_POOL_SPENT_OFFSET_USD") or "0")
    drawn = alltime_cost + offset
    fired_daily = None
    fired_pool: dict[int, datetime] = {}
    for e in alarm_events or ():
        data = e["data"] if isinstance(e["data"], dict) else {}
        if e["type"] == "spend_alarm":
            if fired_daily is None or e["at"] > fired_daily:
                fired_daily = e["at"]
        elif e["type"] == "pool_alarm":
            try:
                pct = int(data.get("threshold"))
            except (TypeError, ValueError):
                continue
            if pct not in fired_pool or e["at"] > fired_pool[pct]:
                fired_pool[pct] = e["at"]
    thresholds = [{"pct": p, "usd": pool * p / 100, "crossed": drawn >= pool * p / 100,
                   "fired_at": fired_pool.get(p)} for p in POOL_THRESHOLDS]
    next_t = next((t for t in thresholds if not t["crossed"]), None)
    return {
        "daily_limit": daily_limit, "today": today_cost,
        "today_pct": (today_cost / daily_limit * 100) if daily_limit else 0.0,
        "over_daily": today_cost > daily_limit, "daily_fired_at": fired_daily,
        "pool": pool, "offset": offset, "drawn": drawn,
        "pool_pct": (drawn / pool * 100) if pool else 0.0,
        "thresholds": thresholds, "next_threshold": next_t,
        "highest_crossed": max((t["pct"] for t in thresholds if t["crossed"]), default=None),
    }


# ── rendering ────────────────────────────────────────────────────────────────

def _when(ts) -> str:
    return f"{ts:%b %d %H:%M}" if ts else ""


def render_tripwires(t: dict) -> str:
    d_state = ("over" if t["over_daily"] else "warn" if t["today_pct"] >= 80 else "")
    d_chip = (chip("alarm fired " + _when(t["daily_fired_at"]), "blocked") if t["daily_fired_at"]
              and t["over_daily"] else chip("over — alarm pending", "blocked") if t["over_daily"]
              else chip("under", "ok"))
    daily = (f"<div class='tripc'><div class='tn'>Daily tripwire{d_chip}</div>"
             f"<div class='tv'>{H(fmt_money(t['today']))}<small> of ${t['daily_limit']:,.0f}</small></div>"
             f"<div class='tbar'><i class='{d_state}' style='width:{min(t['today_pct'], 100):.0f}%'></i></div>"
             f"<div class='td'>{t['today_pct']:.0f}% of LANTERN_DAILY_SPEND_ALARM_USD · the hourly "
             "usage-check posts once per day when crossed · an alarm, not a block</div></div>")
    hi = t["highest_crossed"]
    p_chip = (chip(f"{hi}% crossed", "warn" if hi < 75 else "blocked") if hi else chip("under 25%", "ok"))
    marks = "".join(
        f"<span class='chip {'blocked' if x['crossed'] and x['pct'] >= 75 else 'warn' if x['crossed'] else ''}'>"
        f"{x['pct']}% · ${x['usd']:,.0f}"
        + (f" · fired {_when(x['fired_at'])}" if x["fired_at"] else " · fired? no" if x["crossed"] else "")
        + "</span>" for x in t["thresholds"])
    p_state = "over" if hi and hi >= 75 else "warn" if hi else ""
    pool = (f"<div class='tripc'><div class='tn'>Credit pool{p_chip}</div>"
            f"<div class='tv'>{H(fmt_money(t['drawn']))}<small> of ${t['pool']:,.0f}</small></div>"
            f"<div class='tbar'><i class='{p_state}' style='width:{min(t['pool_pct'], 100):.1f}%'></i></div>"
            f"<div class='td'>{t['pool_pct']:.2f}% drawn — every metered execution and consult"
            + (f", plus ${t['offset']:,.0f} pre-ledger offset" if t["offset"] else "")
            + f"<div class='marks'>{marks}</div></div></div>")
    return f"<div class='trip'>{daily}{pool}</div>"


def _tok_cells(g: dict) -> str:
    if not g["inp"] and not g["outp"]:
        return "<td class='r'>—</td><td class='r'>—</td><td class='r'>—</td><td class='r'>—</td>"
    cached = f"{fmt_int(g['cached'])} · {g['cached_pct']}%" if g["cached_pct"] is not None else fmt_int(g["cached"])
    return (f"<td class='r'>{fmt_int(g['inp'])}</td><td class='r'>{H(cached)}</td>"
            f"<td class='r'>{fmt_int(g['outp'])}</td><td class='r'>{H(fmt_money(g['cost']))}</td>")


def render_by_run(groups: list[dict], limit: int = 40) -> str:
    if not groups:
        return "<p class='empty' style='margin-top:12px'><b>No executions in the ledger yet.</b></p>"
    rows = "".join(
        f"<tr><td class='d'><a href='/run/{H(g['run_id'])}'>{H(g['run_id'])}</a></td>"
        f"<td>{H(', '.join(g['models']) or '— unmetered')}</td><td class='r'>{g['n']}"
        + (f" <span style='color:var(--warning)'>({g['unmetered']} unmetered)</span>" if g["unmetered"] else "")
        + f"</td>{_tok_cells(g)}</tr>" for g in groups[:limit])
    return ("<div class='stripwrap'><table class='spendtbl'><tr><th>Run</th><th>Model</th>"
            "<th class='r'>Executions</th><th class='r'>Input</th><th class='r'>Cached</th>"
            f"<th class='r'>Output</th><th class='r'>Est. $</th></tr>{rows}</table></div>")


def render_by_day(groups: list[dict], daily_limit: float) -> str:
    if not groups:
        return "<p class='empty' style='margin-top:12px'><b>No metered executions in the window.</b></p>"
    rows = []
    for g in sorted(groups, key=lambda g: g["day"], reverse=True):
        w = min(g["cost"] / daily_limit * 100, 100) if daily_limit else 0
        over = " class='over'" if g["cost"] > daily_limit else ""
        rows.append(f"<tr><td class='d'>{g['day']:%b %d}</td><td>{H(', '.join(g['models']) or '— unmetered')}</td>"
                    f"<td class='r'>{g['n']}</td>{_tok_cells(g)}"
                    f"<td><span class='bar'><i{over} style='width:{w:.0f}%'></i></span></td></tr>")
    return ("<div class='stripwrap'><table class='spendtbl'><tr><th>Day</th><th>Model</th>"
            "<th class='r'>Executions</th><th class='r'>Input</th><th class='r'>Cached</th>"
            f"<th class='r'>Output</th><th class='r'>Est. $</th><th></th></tr>{''.join(rows)}</table></div>")


def render_by_model(groups: list[dict]) -> str:
    if not groups:
        return "<p class='empty' style='margin-top:12px'><b>Nothing metered yet.</b></p>"
    rows = "".join(
        f"<tr><td class='d'>{H(g['model'] or '— unmetered')}</td><td class='r'>{g['n']}</td>"
        f"{_tok_cells(g)}</tr>" for g in groups)
    return ("<div class='stripwrap'><table class='spendtbl'><tr><th>Model</th><th class='r'>Executions</th>"
            "<th class='r'>Input</th><th class='r'>Cached</th><th class='r'>Output</th>"
            f"<th class='r'>Est. $</th></tr>{rows}</table></div>")
