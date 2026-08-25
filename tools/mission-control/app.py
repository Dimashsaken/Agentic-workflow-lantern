"""Lantern Mission Control — verification-first web UI over the pipeline DB.

    uvicorn app:app --host 0.0.0.0 --port 8080     (or: python app.py)

Design: docs/MISSION-CONTROL.md. Auth: cookie session behind a login page — no data
is served unauthenticated. Users from LANTERN_WEB_USERS ("name:pw,name:pw"); cookie
signing key from LANTERN_WEB_SECRET (falls back to a hash of LANTERN_WEB_USERS).
"""

import hashlib
import hmac
import html
import json
import os
import secrets
import sys
import time
from pathlib import Path

import asyncpg
import markdown as md
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

AZURE_RUNNER = Path(__file__).resolve().parents[1] / "azure-runner"
sys.path.insert(0, str(AZURE_RUNNER))
load_dotenv(AZURE_RUNNER / ".env")

from pipeline import FEATURE_STAGES, STAGE_DIR, STAGE_RUNNER, advance, db_urls, log_event  # noqa: E402

# Board columns = run-folder dirs; split stage-1 executions share one column.
BOARD_DIRS = list(dict.fromkeys(d for _, d, *_ in FEATURE_STAGES))

REPO = Path(__file__).resolve().parents[2]
app = FastAPI(title="Lantern Mission Control")
pool: asyncpg.Pool | None = None

SESSION_COOKIE = "lantern_session"
SESSION_TTL = 7 * 24 * 3600

# Human-readable pipeline vocabulary — the UI must explain itself (docs/MISSION-CONTROL.md)
STAGE_META = {
    "01-ui-ux":       ("1 · UI/UX design",        "🤖 AI agent", "Explores 2–3 flow options, builds a prototype, records a walkthrough video."),
    "02-pre-coding":  ("2 · Planning",             "🤖 AI agent", "Blast-radius analysis, schema plan, ordered task plan."),
    "03-coding":      ("3 · Coding",               "👤 Human",    "The assigned developer implements the plan (Codex CLI on their laptop)."),
    "04-qa-dev":      ("4 · QA in dev",            "🤖 AI agent", "Executes a test charter against the dev build — every session on video."),
    "05-post-coding": ("5 · Code review",          "🤖 AI agent", "Cleanliness, hidden tech debt, backward compatibility."),
    "06-security":    ("6 · Security & deploy risk","🤖 AI agent", "Vulnerabilities, dependency audit, go/no-go for staging."),
    "07-qa-staging":  ("7 · QA in staging",        "🤖 AI agent", "Re-runs the charter on staging, verifies analytics events, videos for sign-off."),
}
GATE_META = {
    "ux_signoff":     ("Pick the UX option",       "Watch the walkthrough video, then approve the recommended flow (or reject with a note)."),
    "plan_signoff":   ("Approve plan & schema",    "Schema changes always need a human yes before any code is written."),
    "code_complete":  ("Code-complete?",           "The developer confirms every planned task is done and tests are green."),
    "staging_deploy": ("Deploy to staging",        "Security said GO — a human performs the staging deploy, then approves here."),
    "prod_signoff":   ("Ship to production",       "The final human decision. Review the staging QA videos first."),
}
STATUS_META = {
    "running":      ("#3fb950", "an agent is working on it"),
    "waiting_gate": ("#d29922", "paused — needs a human decision"),
    "failed":       ("#f85149", "stopped — needs rework, then Retry"),
    "done":         ("#8b949e", "shipped"),
    "cancelled":    ("#8b949e", "cancelled"),
}

CSS = """
body{font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;margin:0}
main{padding:1.25rem;max-width:1400px;margin:0 auto}
a{color:#58a6ff;text-decoration:none}
nav{display:flex;align-items:center;gap:1rem;background:#161b22;border-bottom:1px solid #30363d;padding:.7rem 1.25rem}
nav .spacer{flex:1} nav .who{color:#8b949e;font-size:.85rem}
h1{font-size:1.15rem;margin:0} h2{font-weight:600;font-size:1rem;margin:1.4rem 0 .4rem}
.sub{color:#8b949e;font-size:.85rem;margin:.1rem 0 .6rem}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:.8rem;margin:.5rem 0}
.badge{display:inline-block;padding:.1rem .55rem;border-radius:999px;font-size:.75rem;color:#0d1117;font-weight:700}
.chip{display:inline-block;padding:.05rem .5rem;border:1px solid #30363d;border-radius:999px;font-size:.75rem;color:#8b949e}
.board{display:flex;gap:.75rem;overflow-x:auto;padding-bottom:.5rem}
.col{min-width:185px;flex:1}
.col h3{font-size:.78rem;color:#8b949e;margin:.4rem 0} .col .desc{font-size:.7rem;color:#6e7681}
button{background:#238636;color:#fff;border:0;border-radius:6px;padding:.42rem .9rem;cursor:pointer;font-weight:600}
button.reject{background:#da3633}
input{background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:.4rem}
.report{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:1rem;margin:.5rem 0;overflow-x:auto}
.evt{font-size:.8rem;color:#8b949e;font-family:monospace}
.legend{display:flex;gap:1.1rem;flex-wrap:wrap;font-size:.78rem;color:#8b949e;margin:.4rem 0}
.legend span b{color:#e6edf3}
.login{max-width:340px;margin:14vh auto;text-align:center}
.login input{width:100%;margin:.35rem 0;box-sizing:border-box}
.err{color:#f85149;font-size:.85rem}
.options{display:flex;gap:.6rem;overflow-x:auto;margin:.5rem 0}
.option{min-width:200px;max-width:280px}
.option img{width:100%;border:1px solid #30363d;border-radius:6px;background:#fff}
.optname{font-size:.8rem;margin:.2rem 0}
.warn{color:#d29922;border-color:#d29922}
"""


# ── auth: signed cookie sessions ─────────────────────────────────────────────

def _users() -> dict[str, str]:
    raw = os.environ.get("LANTERN_WEB_USERS", "")
    return {u.strip(): pw for u, pw in
            (p.split(":", 1) for p in raw.split(",") if ":" in p)}


def _secret() -> bytes:
    explicit = os.environ.get("LANTERN_WEB_SECRET")
    seed = explicit or ("derived:" + os.environ.get("LANTERN_WEB_USERS", ""))
    return hashlib.sha256(seed.encode()).digest()


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def make_session(user: str) -> str:
    exp = str(int(time.time()) + SESSION_TTL)
    payload = f"{user}|{exp}"
    return f"{payload}|{_sign(payload)}"


def current_user(request: Request) -> str | None:
    tok = request.cookies.get(SESSION_COOKIE, "")
    parts = tok.split("|")
    if len(parts) != 3:
        return None
    payload = f"{parts[0]}|{parts[1]}"
    if not hmac.compare_digest(_sign(payload), parts[2]):
        return None
    if int(parts[1]) < time.time() or parts[0] not in _users():
        return None
    return parts[0]


async def get_pool() -> asyncpg.Pool:
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(db_urls()[1], min_size=1, max_size=5)
    return pool


# ── rendering helpers ────────────────────────────────────────────────────────

def page(title: str, body: str, user: str | None = None, refresh: bool = True) -> HTMLResponse:
    nav = ""
    if user:
        nav = (f"<nav><h1><a href='/'>🏮 Lantern Mission Control</a></h1>"
               f"<a href='/#inbox'>Inbox</a><a href='/#board'>Board</a><span class='spacer'></span>"
               f"<span class='who'>signed in as <b>{html.escape(user)}</b></span>"
               f"<a href='/logout'>log out</a></nav>")
    meta = "<meta http-equiv='refresh' content='20'>" if refresh else ""
    return HTMLResponse(
        f"<!doctype html><html><head><meta charset='utf-8'>{meta}"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
        f"<body>{nav}<main>{body}</main></body></html>")


def badge(status_: str) -> str:
    color, _ = STATUS_META.get(status_, ("#8b949e", ""))
    return f"<span class='badge' style='background:{color}'>{html.escape(status_.replace('_', ' '))}</span>"


def legend() -> str:
    items = "".join(
        f"<span><span class='badge' style='background:{c}'>&nbsp;</span> <b>{html.escape(s.replace('_',' '))}</b> — {html.escape(d)}</span>"
        for s, (c, d) in STATUS_META.items() if s != "cancelled")
    return f"<div class='legend'>{items}</div>"


def _payload(a) -> dict:
    p = a["payload"] if "payload" in dict(a) else None
    if isinstance(p, str):
        try:
            return json.loads(p)
        except ValueError:
            return {}
    return p or {}


def handoff_html(payload: dict) -> str:
    """Render a ui-ux handoff.json gate payload: Paper link + option PNGs side by side."""
    h = payload.get("handoff") or {}
    if not h:
        return ""
    bits = []
    if h.get("paper_url"):
        bits.append(f"<p><a href='{html.escape(h['paper_url'])}' target='_blank'>🎨 open the Paper canvas</a></p>")
    cards = []
    for o in h.get("options", []):
        name = o.get("name", "?")
        star = " ★ recommended" if name == h.get("recommended") else ""
        imgs = "".join(
            f"<a href='/file/{html.escape(png)}'><img src='/file/{html.escape(png)}' alt='{html.escape(name)}'></a>"
            for png in o.get("pngs", []))
        cards.append(f"<div class='option'><div class='optname'><b>{html.escape(name)}</b>{star}</div>{imgs}</div>")
    if cards:
        bits.append(f"<div class='options'>{''.join(cards)}</div>")
    if h.get("video"):
        bits.append(f"<p><a href='{html.escape(str(h['video']))}'>🎬 walkthrough video</a></p>")
    return "".join(bits)


def gate_form(a) -> str:
    title, desc = GATE_META.get(a["gate"], (a["gate"], ""))
    return (f"<b>{html.escape(title)}</b><div class='sub'>{html.escape(desc)}</div>"
            f"{handoff_html(_payload(a))}"
            f"<form method='post' action='/gate/{a['id']}/approve' style='display:inline'>"
            f"<input name='note' placeholder='optional note'> <button>Approve</button></form> "
            f"<form method='post' action='/gate/{a['id']}/reject' style='display:inline'>"
            f"<button class='reject'>Reject</button></form>")


KIND_ICON = {"qa_video": "🎬 ", "design_png": "🖼 ", "paper_file": "🎨 ", "flow_spec": "🗺 ", "design_handoff": "📦 "}


def art_href(uri: str) -> str:
    return uri if uri.startswith(("http://", "https://", "s3://")) else f"/file/{uri}"


async def runners_online(p) -> dict[str, bool]:
    try:
        rows = await p.fetch("SELECT name, now() - last_seen < interval '90 seconds' AS online FROM runners")
    except asyncpg.PostgresError:   # table not created yet (pre-v2 database)
        return {}
    return {r["name"]: r["online"] for r in rows}


def needs_workstation_note(run_status: str, current_stage: str, online: dict[str, bool]) -> str:
    if (run_status == "running" and STAGE_RUNNER.get(current_stage) == "workstation"
            and not online.get("workstation")):
        return ("<div class='chip warn'>⏸ needs the design workstation — open Paper Desktop on the "
                "Lantern file and start <code>pipeline.py daemon --runner workstation</code></div>")
    return ""


# ── routes ───────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    if current_user(request):
        return RedirectResponse("/", status_code=303)
    warn = "" if _users() else "<p class='err'>No users configured — set LANTERN_WEB_USERS on the server.</p>"
    err = f"<p class='err'>{html.escape(error)}</p>" if error else ""
    return page("Sign in — Lantern", f"""
      <div class='login card'><h1>🏮 Lantern Mission Control</h1>
      <p class='sub'>The control room for the agent fleet. Sign in to see runs and decide gates.</p>
      {warn}{err}
      <form method='post' action='/login'>
        <input name='username' placeholder='username' autofocus>
        <input name='password' type='password' placeholder='password'>
        <button style='width:100%;margin-top:.4rem'>Sign in</button>
      </form></div>""", refresh=False)


@app.post("/login")
async def do_login(username: str = Form(""), password: str = Form("")):
    users = _users()
    if username in users and secrets.compare_digest(password, users[username]):
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(SESSION_COOKIE, make_session(username), max_age=SESSION_TTL,
                        httponly=True, samesite="lax")
        return resp
    return RedirectResponse("/login?error=Wrong+username+or+password", status_code=303)


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    p = await get_pool()
    pend = await p.fetch(
        "SELECT id, run_id, gate, payload, requested_at FROM approvals WHERE status='pending' ORDER BY requested_at")
    runs = await p.fetch(
        "SELECT id, status, current_stage, created_by, updated_at FROM runs WHERE status != 'done' ORDER BY updated_at DESC")
    done = await p.fetch(
        "SELECT id, completed_at FROM runs WHERE status='done' ORDER BY completed_at DESC LIMIT 5")
    online = await runners_online(p)

    inbox = "".join(
        f"<div class='card'><a href='/run/{html.escape(a['run_id'])}'>{html.escape(a['run_id'])}</a>"
        f" <span class='chip'>waiting since {a['requested_at']:%b %d %H:%M}</span><br>{gate_form(a)}</div>"
        for a in pend) or "<div class='card'>Nothing is waiting on a human right now 🎉</div>"

    cols = []
    for dir_ in BOARD_DIRS:
        name, actor, _ = STAGE_META[dir_]
        cards = "".join(
            f"<div class='card'><a href='/run/{html.escape(r['id'])}'>{html.escape(r['id'])}</a><br>"
            f"{badge(r['status'])}<div class='sub'>by {html.escape(r['created_by'])} · {r['updated_at']:%b %d}</div>"
            f"{needs_workstation_note(r['status'], r['current_stage'], online)}</div>"
            for r in runs if STAGE_DIR.get(r["current_stage"], r["current_stage"]) == dir_)
        cols.append(f"<div class='col'><h3>{html.escape(name)}</h3>"
                    f"<div class='desc'>{html.escape(actor)}</div>{cards}</div>")

    recent = "".join(f"<li><a href='/run/{html.escape(r['id'])}'>{html.escape(r['id'])}</a> "
                     f"shipped {r['completed_at']:%b %d}</li>" for r in done) or "<li>none yet</li>"

    return page("Mission Control", f"""
      <h2 id='inbox'>📥 Inbox — decisions waiting on a human</h2>
      <p class='sub'>The pipeline pauses here until someone approves. Approving moves the run to its next stage; rejecting stops it for rework.</p>
      {inbox}
      <h2 id='board'>🗺 Board — every active run, left to right through the pipeline</h2>
      {legend()}
      <div class='board'>{''.join(cols)}</div>
      <h2>✅ Recently shipped</h2><ul>{recent}</ul>""", user=user)


@app.get("/run/{run_id}", response_class=HTMLResponse)
async def run_page(run_id: str, request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    p = await get_pool()
    run = await p.fetchrow("SELECT * FROM runs WHERE id = $1", run_id)
    if not run:
        raise HTTPException(404, "run not found")
    execs = await p.fetch(
        """SELECT DISTINCT ON (stage) stage, status, attempt, error, started_at, finished_at
           FROM stage_executions WHERE run_id = $1 ORDER BY stage, attempt DESC""", run_id)
    by_dir: dict[str, asyncpg.Record] = {}   # latest execution per run-folder dir
    for e in execs:
        d = STAGE_DIR.get(e["stage"], e["stage"])
        if d not in by_dir or e["started_at"] > by_dir[d]["started_at"]:
            by_dir[d] = e
    arts = await p.fetch("SELECT stage, kind, uri FROM artifacts WHERE run_id = $1", run_id)
    events = await p.fetch(
        "SELECT actor, type, at FROM events WHERE run_id = $1 ORDER BY at DESC LIMIT 30", run_id)
    pend = await p.fetch(
        "SELECT id, gate, payload, requested_at FROM approvals WHERE run_id = $1 AND status='pending'", run_id)
    online = await runners_online(p)

    _, sdesc = STATUS_META.get(run["status"], ("", ""))
    parts = [f"<h2>{html.escape(run_id)} {badge(run['status'])}</h2>"
             f"<p class='sub'>{html.escape(sdesc)} · started by {html.escape(run['created_by'])} · "
             f"brief: <code>{html.escape(run['brief'])}</code></p>"]
    ws_note = needs_workstation_note(run["status"], run["current_stage"], online)
    if ws_note:
        parts.append(f"<div class='card'>{ws_note}</div>")
    for a in pend:
        parts.append(f"<div class='card'>⏳ {gate_form(a)}</div>")

    cur_dir = STAGE_DIR.get(run["current_stage"], run["current_stage"])
    for dir_ in BOARD_DIRS:
        name, actor, desc = STAGE_META[dir_]
        e = by_dir.get(dir_)
        cur = " ← current" if dir_ == cur_dir and run["status"] != "done" else ""
        state = badge(e["status"]) if e else "<span class='chip'>not started</span>"
        phase = (f" <span class='chip'>phase: {html.escape(e['stage'].split('.', 1)[1])}</span>"
                 if e and "." in e["stage"] else "")
        parts.append(f"<div class='card'><b>{html.escape(name)}</b> <span class='chip'>{html.escape(actor)}</span> "
                     f"{state}{phase}<b>{cur}</b><div class='sub'>{html.escape(desc)}</div>")
        if e and e["error"]:
            parts.append(f"<p class='evt'>error: {html.escape(e['error'][:500])}</p>")
        report = REPO / "workflow" / "runs" / run_id / dir_ / "report.md"
        if report.exists():
            parts.append(f"<details><summary>📄 stage report</summary><div class='report'>"
                         f"{md.markdown(report.read_text(encoding='utf-8'))}</div></details>")
        stage_arts = [a for a in arts if a["stage"] == dir_]
        if stage_arts:
            links = " · ".join(
                f"<a href='{html.escape(art_href(a['uri']))}'>{KIND_ICON.get(a['kind'], '')}{html.escape(a['kind'])}</a>"
                for a in stage_arts)
            parts.append(f"<p>artifacts: {links}</p>")
        parts.append("</div>")

    evt = "".join(f"<div class='evt'>{e['at']:%b %d %H:%M} · {html.escape(e['actor'])} · "
                  f"{html.escape(e['type'].replace('_', ' '))}</div>" for e in events)
    parts.append(f"<h2>📜 Audit log</h2><p class='sub'>Every action on this run, newest first.</p>{evt}")
    return page(run_id, "".join(parts), user=user)


@app.get("/file/{rel:path}")
async def serve_file(rel: str, request: Request):
    """Serve run-folder artifacts (option PNGs, reports) to signed-in users only."""
    if not current_user(request):
        raise HTTPException(401, "sign in required")     # fail closed, like gates
    p = (REPO / rel).resolve()
    runs_root = (REPO / "workflow" / "runs").resolve()
    if not p.is_relative_to(runs_root) or not p.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(p)


@app.post("/gate/{approval_id}/{decision}")
async def decide(approval_id: int, decision: str, request: Request, note: str = Form("")):
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "sign in required")    # fail closed
    if decision not in ("approve", "reject"):
        raise HTTPException(400, "bad decision")
    p = await get_pool()
    async with p.acquire() as conn:
        a = await conn.fetchrow(
            """UPDATE approvals SET status=$1, decided_at=now(), decided_by=$2, decision_note=$3
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
                "UPDATE runs SET status='failed', updated_at=now() WHERE id = $1", a["run_id"])
    return RedirectResponse(f"/run/{a['run_id']}", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8080)
