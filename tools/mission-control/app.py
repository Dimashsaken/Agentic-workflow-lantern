"""Lantern Mission Control — verification-first web UI over the pipeline DB.

    uvicorn app:app --host 0.0.0.0 --port 8080     (or: python app.py)

Design: docs/MISSION-CONTROL.md. Reads the same Postgres the orchestrator writes;
approvals are fail-closed (no LANTERN_WEB_USERS configured -> read-only).
"""

import html
import os
import secrets
import sys
from pathlib import Path

import asyncpg
import markdown as md
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

AZURE_RUNNER = Path(__file__).resolve().parents[1] / "azure-runner"
sys.path.insert(0, str(AZURE_RUNNER))
load_dotenv(AZURE_RUNNER / ".env")

from pipeline import FEATURE_STAGES, advance, db_urls, log_event  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
app = FastAPI(title="Lantern Mission Control")
basic = HTTPBasic(auto_error=False)
pool: asyncpg.Pool | None = None

STATUS_COLOR = {"running": "#3fb950", "waiting_gate": "#d29922", "failed": "#f85149",
                "done": "#8b949e", "cancelled": "#8b949e"}

CSS = """
body{font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:1.5rem}
a{color:#58a6ff;text-decoration:none} h1,h2{font-weight:600} h1{font-size:1.3rem}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:.8rem;margin:.5rem 0}
.badge{display:inline-block;padding:.1rem .5rem;border-radius:999px;font-size:.75rem;color:#0d1117;font-weight:700}
.board{display:flex;gap:.75rem;overflow-x:auto;padding-bottom:.5rem}
.col{min-width:180px;flex:1}.col h3{font-size:.8rem;color:#8b949e;text-transform:uppercase}
button{background:#238636;color:#fff;border:0;border-radius:6px;padding:.4rem .9rem;cursor:pointer}
button.reject{background:#da3633}
input[type=text]{background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:.35rem}
.report{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:1rem;margin:.5rem 0;overflow-x:auto}
.evt{font-size:.8rem;color:#8b949e;font-family:monospace}
table{border-collapse:collapse}td,th{padding:.25rem .6rem;text-align:left}
"""


def _users() -> dict[str, str]:
    raw = os.environ.get("LANTERN_WEB_USERS", "")
    pairs = [p.split(":", 1) for p in raw.split(",") if ":" in p]
    return {u.strip(): pw for u, pw in pairs}


def current_user(creds: HTTPBasicCredentials | None = Depends(basic)) -> str | None:
    users = _users()
    if creds and creds.username in users and secrets.compare_digest(
            creds.password, users[creds.username]):
        return creds.username
    return None


async def get_pool() -> asyncpg.Pool:
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(db_urls()[1], min_size=1, max_size=5)
    return pool


def page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta http-equiv='refresh' content='15'><title>{html.escape(title)}</title>"
        f"<style>{CSS}</style></head><body>"
        f"<h1><a href='/'>🏮 Lantern Mission Control</a></h1>{body}</body></html>")


def badge(status_: str) -> str:
    return (f"<span class='badge' style='background:{STATUS_COLOR.get(status_, '#8b949e')}'>"
            f"{html.escape(status_)}</span>")


def gate_form(a, user: str | None) -> str:
    if not user:
        return "<em>sign in with an approver account to decide</em>"
    return (f"<form method='post' action='/gate/{a['id']}/approve' style='display:inline'>"
            f"<input type='text' name='note' placeholder='note'> <button>Approve</button></form> "
            f"<form method='post' action='/gate/{a['id']}/reject' style='display:inline'>"
            f"<button class='reject'>Reject</button></form>")


@app.get("/", response_class=HTMLResponse)
async def dashboard(user: str | None = Depends(current_user)):
    p = await get_pool()
    pend = await p.fetch(
        """SELECT a.id, a.run_id, a.gate, a.requested_at FROM approvals a
           WHERE a.status = 'pending' ORDER BY a.requested_at""")
    runs = await p.fetch(
        "SELECT id, status, current_stage, updated_at FROM runs WHERE status != 'done' ORDER BY updated_at DESC")
    done = await p.fetch(
        "SELECT id, completed_at FROM runs WHERE status = 'done' ORDER BY completed_at DESC LIMIT 5")

    inbox = "".join(
        f"<div class='card'>⏳ <a href='/run/{html.escape(a['run_id'])}'>{html.escape(a['run_id'])}</a>"
        f" needs <b>{html.escape(a['gate'])}</b> (since {a['requested_at']:%m-%d %H:%M}) "
        f"{gate_form(a, user)}</div>"
        for a in pend) or "<div class='card'>nothing waiting on a human 🎉</div>"

    cols = []
    for stage, _, _ in FEATURE_STAGES:
        cards = "".join(
            f"<div class='card'><a href='/run/{html.escape(r['id'])}'>{html.escape(r['id'])}</a><br>"
            f"{badge(r['status'])}</div>"
            for r in runs if r["current_stage"] == stage)
        cols.append(f"<div class='col'><h3>{html.escape(stage)}</h3>{cards}</div>")
    board = f"<div class='board'>{''.join(cols)}</div>"

    recent = "".join(f"<li><a href='/run/{html.escape(r['id'])}'>{html.escape(r['id'])}</a> "
                     f"done {r['completed_at']:%Y-%m-%d}</li>" for r in done)
    who = f"signed in as <b>{html.escape(user)}</b>" if user else "read-only (no approver login)"
    return page("Mission Control",
                f"<p class='evt'>{who}</p><h2>Inbox — needs a human</h2>{inbox}"
                f"<h2>Board</h2>{board}<h2>Recently shipped</h2><ul>{recent}</ul>")


@app.get("/run/{run_id}", response_class=HTMLResponse)
async def run_page(run_id: str, user: str | None = Depends(current_user)):
    p = await get_pool()
    run = await p.fetchrow("SELECT * FROM runs WHERE id = $1", run_id)
    if not run:
        raise HTTPException(404, "run not found")
    execs = await p.fetch(
        """SELECT DISTINCT ON (stage) stage, status, attempt, error, finished_at
           FROM stage_executions WHERE run_id = $1 ORDER BY stage, attempt DESC""", run_id)
    by_stage = {e["stage"]: e for e in execs}
    arts = await p.fetch("SELECT stage, kind, uri FROM artifacts WHERE run_id = $1", run_id)
    events = await p.fetch(
        "SELECT actor, type, at FROM events WHERE run_id = $1 ORDER BY at DESC LIMIT 30", run_id)
    pend = await p.fetch(
        "SELECT id, gate, requested_at FROM approvals WHERE run_id = $1 AND status = 'pending'", run_id)

    parts = [f"<h2>{html.escape(run_id)} {badge(run['status'])} "
             f"<span class='evt'>at {html.escape(run['current_stage'])}</span></h2>"]
    for a in pend:
        parts.append(f"<div class='card'>⏳ gate <b>{html.escape(a['gate'])}</b> {gate_form(a, user)}</div>")

    for stage, stype, gate in FEATURE_STAGES:
        e = by_stage.get(stage)
        state = badge(e["status"]) if e else "<span class='evt'>pending</span>"
        parts.append(f"<div class='card'><b>{html.escape(stage)}</b> ({stype}) {state}")
        if e and e["error"]:
            parts.append(f"<p class='evt'>error: {html.escape(e['error'][:500])}</p>")
        report = REPO / "workflow" / "runs" / run_id / stage / "report.md"
        if report.exists():
            parts.append(f"<details><summary>report</summary><div class='report'>"
                         f"{md.markdown(report.read_text(encoding='utf-8'))}</div></details>")
        stage_arts = [a for a in arts if a["stage"] == stage]
        if stage_arts:
            links = " · ".join(
                f"<a href='{html.escape(a['uri'])}'>{html.escape(a['kind'])}</a>" for a in stage_arts)
            parts.append(f"<p>artifacts: {links}</p>")
        parts.append("</div>")

    evt = "".join(f"<div class='evt'>{e['at']:%m-%d %H:%M} {html.escape(e['actor'])} "
                  f"{html.escape(e['type'])}</div>" for e in events)
    parts.append(f"<h2>Events</h2>{evt}")
    return page(run_id, "".join(parts))


@app.post("/gate/{approval_id}/{decision}")
async def decide(approval_id: int, decision: str, note: str = Form(""),
                 user: str | None = Depends(current_user)):
    if user is None:
        raise HTTPException(401, "approver login required")   # fail closed
    if decision not in ("approve", "reject"):
        raise HTTPException(400, "bad decision")
    p = await get_pool()
    async with p.acquire() as conn:
        a = await conn.fetchrow(
            """UPDATE approvals SET status = $1, decided_at = now(), decided_by = $2, decision_note = $3
               WHERE id = $4 AND status = 'pending' RETURNING run_id, gate""",
            "approved" if decision == "approve" else "rejected", user, note, approval_id)
        if not a:
            raise HTTPException(409, "approval no longer pending")
        await log_event(conn, a["run_id"], f"human:{user}", f"gate_{decision}d",
                        {"gate": a["gate"], "note": note, "channel": "web"})
        if decision == "approve":
            stage = await conn.fetchval("SELECT current_stage FROM runs WHERE id = $1", a["run_id"])
            await advance(conn, a["run_id"], stage)
        else:
            await conn.execute(
                "UPDATE runs SET status = 'failed', updated_at = now() WHERE id = $1", a["run_id"])
    return RedirectResponse(f"/run/{a['run_id']}", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
