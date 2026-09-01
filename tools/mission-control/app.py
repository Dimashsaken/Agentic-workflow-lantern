"""Lantern Mission Control v2 — the board is the control plane.

    uvicorn app:app --host 0.0.0.0 --port 8080     (or: python app.py)

The board is a ticket board in the Fredrin sense — five workflow columns
(Queued · Running · Blocked · Review · Done) and every run is a card moving
through them, with the 7-stage pipeline compressed into a rail on the card.
Review cards carry Approve/Reject directly; /runs keeps the dense strip list.

Two hard rules carried over unchanged from v1:
  * Gate integrity: approvals are written server-side via
    POST /gate/{approval_id}/{decision}, fail-closed, against LANTERN_WEB_USERS.
    Nothing client-side can approve anything.
  * Honesty: the board renders what the database and the stage reports actually
    say — including when they disagree. A stage execution can be 'succeeded'
    while its own report's Status: line says BLOCKED (the vacuous-gate failure,
    fixed for new runs in 5f3f653); that disagreement is a first-class column.

Auth: HMAC cookie sessions behind a login page — no data is served
unauthenticated. Users from LANTERN_WEB_USERS ("name:pw,name:pw"); signing key
from LANTERN_WEB_SECRET (falls back to a hash of LANTERN_WEB_USERS).
"""

import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import markdown as md
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

AZURE_RUNNER = Path(__file__).resolve().parents[1] / "azure-runner"
sys.path.insert(0, str(AZURE_RUNNER))
load_dotenv(AZURE_RUNNER / ".env")

from pipeline import (  # noqa: E402
    FEATURE_STAGES, STAGE_DIR, STAGE_RUNNER, advance, db_urls, est_cost_usd,
    log_event,
)
import ui  # noqa: E402
from ui import H, ago, chip, fmt_int, fmt_money, group_head, srail, strip, strip_header  # noqa: E402

# Board columns = run-folder dirs; split stage-1 executions share one column.
BOARD_DIRS = list(dict.fromkeys(d for _, d, *_ in FEATURE_STAGES))
STAGE_SEQ = [s for s, *_ in FEATURE_STAGES]           # full stage names, in order
DIR_RUNNER = {}                                       # dir -> runner of its first stage
for _s, _d, *_rest in FEATURE_STAGES:
    DIR_RUNNER.setdefault(_d, STAGE_RUNNER.get(_s, "ec2"))

REPO = Path(__file__).resolve().parents[2]
app = FastAPI(title="Lantern Mission Control")
pool: asyncpg.Pool | None = None

SESSION_COOKIE = "lantern_session"
SESSION_TTL = 7 * 24 * 3600
EC2_SLOTS = 2            # daemon concurrency cap (docs/ORCHESTRATION.md, D10)

STAGE_META = {
    "01-ui-ux":       ("1 · UI/UX design",         "agent",  "Explores 2–3 flow options, builds a prototype, records a walkthrough video."),
    "02-pre-coding":  ("2 · Planning",              "agent",  "Blast-radius analysis, schema plan, ordered task plan."),
    "03-coding":      ("3 · Coding",                "human",  "The assigned developer implements the plan (Codex CLI on their laptop)."),
    "04-qa-dev":      ("4 · QA in dev",             "agent",  "Executes a test charter against the dev build — every session on video."),
    "05-post-coding": ("5 · Code review",           "agent",  "Cleanliness, hidden tech debt, backward compatibility."),
    "06-security":    ("6 · Security & deploy risk","agent",  "Vulnerabilities, dependency audit, go/no-go for staging."),
    "07-qa-staging":  ("7 · QA in staging",         "agent",  "Re-runs the charter on staging, verifies analytics events, videos for sign-off."),
}
GATE_META = {
    "ux_signoff":     ("Pick the UX option",     "Watch the walkthrough, then approve the recommended flow (or reject with a note)."),
    "plan_signoff":   ("Approve plan & schema",  "Schema changes always need a human yes before any code is written."),
    "code_complete":  ("Code-complete?",         "The developer confirms every planned task is done and tests are green."),
    "staging_deploy": ("Deploy to staging",      "Security said GO — a human performs the staging deploy, then approves here."),
    "prod_signoff":   ("Ship to production",     "The final human decision. Review the staging QA videos first."),
}
GATE_SHORT = {
    "ux_signoff": "UX sign-off", "plan_signoff": "plan sign-off",
    "code_complete": "code-complete", "staging_deploy": "staging deploy",
    "prod_signoff": "prod sign-off",
}
KIND_ICON = {"qa_video": "🎬 ", "design_png": "🖼 ", "paper_file": "🎨 ",
             "flow_spec": "🗺 ", "design_handoff": "📦 ", "report": "📄 "}


# ── auth: signed cookie sessions (unchanged from v1) ─────────────────────────

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


# ── report honesty: what does the stage's own report say? ────────────────────

VERDICT_RE = re.compile(r"\*\*Status:\*\*\s*([A-Z][A-Z-]*)")
OPENQ_RE = re.compile(r"##\s*Open questions?[^\n]*\n+\s*-?\s*(.+)")


def report_path(run_id: str, dir_: str) -> Path:
    return REPO / "workflow" / "runs" / run_id / dir_ / "report.md"


def report_text(run_id: str, dir_: str) -> str | None:
    try:
        return report_path(run_id, dir_).read_text(encoding="utf-8")
    except OSError:
        return None


def report_verdict(text: str | None) -> str | None:
    if not text:
        return None
    m = VERDICT_RE.search(text[:4000])
    return m.group(1) if m else None


def report_open_question(text: str | None) -> str | None:
    if not text:
        return None
    m = OPENQ_RE.search(text)
    return m.group(1).strip()[:240] if m else None


def render_markdown(text: str) -> str:
    return md.markdown(text, extensions=["tables", "fenced_code"])


# ── data assembly ────────────────────────────────────────────────────────────

# Gate latency (feat-20260831-gate-latency): one grouped read over decided
# approvals. The 30-day window is on decided_at — a decision made yesterday on
# a gate opened months ago still counts. percentile_cont interpolates the
# median for even-sized cohorts.
LATENCY_SQL = """SELECT gate, count(*)::int AS n,
       percentile_cont(0.5) WITHIN GROUP
         (ORDER BY EXTRACT(EPOCH FROM decided_at - requested_at)) AS med
FROM approvals
WHERE status IN ('approved','rejected') AND decided_at IS NOT NULL
  AND decided_at >= now() - interval '30 days'
GROUP BY gate"""

STALE_SECONDS = 24 * 3600      # the plan's staffing threshold — a code edit, not config


def is_stale(elapsed_seconds: float) -> bool:
    return elapsed_seconds > STALE_SECONDS


def gate_latency_rows(rows) -> list[dict]:
    """Normalize latency query rows: every known gate in GATE_META order
    (zero-sample gates included), then unknown historical gates rather than
    dropping them."""
    by_gate = {r["gate"]: r for r in rows}
    out = []
    for g in GATE_META:
        r = by_gate.get(g)
        out.append({"gate": g,
                    "med": float(r["med"]) if r and r["med"] is not None else None,
                    "n": int(r["n"]) if r else 0})
    for r in rows:
        if r["gate"] not in GATE_META:
            out.append({"gate": r["gate"],
                        "med": float(r["med"]) if r["med"] is not None else None,
                        "n": int(r["n"])})
    return out


def ledger_metrics(rows: list[dict]) -> list[dict]:
    """Display form of normalized latency rows: value/kind/sub per gate.
    Zero-sample cohorts show '—', never '0h'; medians over the 24h staffing
    threshold get the warning kind."""
    out = []
    for r in rows:
        label = GATE_SHORT.get(r["gate"], r["gate"])
        if not r["n"] or r["med"] is None:
            out.append({"value": "—", "kind": "dim",
                        "sub": f"{label} · no decisions · n=0"})
        else:
            out.append({"value": ago(r["med"]),
                        "kind": "warn" if r["med"] > STALE_SECONDS else "",
                        "sub": f"{label} · n={r['n']}"})
    return out

def _payload(a) -> dict:
    p = a["payload"] if "payload" in dict(a) else None
    if isinstance(p, str):
        try:
            return json.loads(p)
        except ValueError:
            return {}
    return p or {}


def art_href(uri: str) -> str:
    return uri if uri.startswith(("http://", "https://", "s3://")) else f"/file/{uri}"


async def snapshot(p) -> dict:
    """Everything the board and runs pages need, in one batch of queries."""
    runs = await p.fetch("SELECT * FROM runs ORDER BY updated_at DESC")
    latest = await p.fetch(
        """SELECT DISTINCT ON (run_id, stage) *
           FROM stage_executions ORDER BY run_id, stage, attempt DESC, started_at DESC""")
    agg = await p.fetch(
        """SELECT run_id, model, sum(input_tokens)::bigint AS inp,
                  sum(cached_input_tokens)::bigint AS cached,
                  sum(output_tokens)::bigint AS outp, sum(total_tokens)::bigint AS tot,
                  sum(requests)::bigint AS reqs, max(attempt) AS max_att,
                  count(*) FILTER (WHERE total_tokens IS NULL)::int AS unmetered
           FROM stage_executions GROUP BY run_id, model""")
    pend = await p.fetch(
        "SELECT * FROM approvals WHERE status='pending' ORDER BY requested_at")
    try:
        gate_latency = gate_latency_rows(await p.fetch(LATENCY_SQL))
    except asyncpg.PostgresError:       # the ledger degrades; the board must not
        gate_latency = None
    try:
        runner_rows = await p.fetch(
            "SELECT name, last_seen, EXTRACT(EPOCH FROM now()-last_seen) AS age FROM runners")
    except asyncpg.PostgresError:           # pre-v2 database without the table
        runner_rows = []
    today = await p.fetch(
        """SELECT model, sum(input_tokens)::bigint AS inp,
                  sum(cached_input_tokens)::bigint AS cached,
                  sum(output_tokens)::bigint AS outp, count(*)::int AS n
           FROM stage_executions WHERE started_at >= date_trunc('day', now())
           GROUP BY model""")
    feed = await p.fetch(
        """SELECT run_id, stage, attempt, status, error, started_at
           FROM stage_executions
           WHERE started_at >= now() - interval '48 hours'
             AND (status = 'failed' OR attempt > 1)
           ORDER BY started_at DESC LIMIT 14""")
    latest_by_dir: dict[tuple[str, str], asyncpg.Record] = {}
    for e in latest:
        k = (e["run_id"], STAGE_DIR.get(e["stage"], e["stage"]))
        cur = latest_by_dir.get(k)
        if cur is None or e["started_at"] > cur["started_at"]:
            latest_by_dir[k] = e
    ledger: dict[str, dict] = {}
    for r in agg:
        led = ledger.setdefault(r["run_id"], {
            "cost": 0.0, "tot": 0, "inp": 0, "cached": 0, "reqs": 0,
            "models": set(), "max_att": 1, "unmetered": 0})
        led["cost"] += est_cost_usd(r["inp"], r["cached"], r["outp"], r["model"])
        led["tot"] += r["tot"] or 0
        led["inp"] += r["inp"] or 0
        led["cached"] += r["cached"] or 0
        led["reqs"] += r["reqs"] or 0
        led["max_att"] = max(led["max_att"], r["max_att"] or 1)
        led["unmetered"] += r["unmetered"] or 0
        if r["model"]:
            led["models"].add(r["model"])
    runners = {r["name"]: r for r in runner_rows}
    online = {n: (r["age"] is not None and r["age"] < 90) for n, r in runners.items()}
    return {"runs": runs, "latest_by_dir": latest_by_dir, "ledger": ledger,
            "pend": pend, "gate_latency": gate_latency, "runners": runners,
            "online": online, "today": today, "feed": feed}


def rail_segs(run, latest_by_dir) -> tuple[list[str], str, int]:
    curdir = STAGE_DIR.get(run["current_stage"], run["current_stage"])
    curidx = BOARD_DIRS.index(curdir) if curdir in BOARD_DIRS else 0
    segs = []
    for i, d in enumerate(BOARD_DIRS):
        e = latest_by_dir.get((run["id"], d))
        if d == curdir:
            segs.append("done" if run["status"] == "done" else
                        "fail" if run["status"] in ("failed", "cancelled") else "now")
        elif i < curidx or (e and e["status"] == "succeeded"):
            segs.append("done")
        elif e and e["status"] == "failed":
            segs.append("fail")
        else:
            segs.append("")
    return segs, curdir, curidx


def run_short(run_id: str) -> str:
    return re.sub(r"^(feat|bug)-\d{8}-", "", run_id)


def workstation_blocked(run, online: dict) -> bool:
    return (run["status"] in ("running", "executing")
            and STAGE_RUNNER.get(run["current_stage"]) == "workstation"
            and not online.get("workstation"))


def build_strip(run, snap: dict, now: datetime) -> tuple[str, dict]:
    """Classify one run into its board group and render its strip dict."""
    lat = snap["latest_by_dir"]
    led = snap["ledger"].get(run["id"], {})
    pend_by_run = {a["run_id"]: a for a in snap["pend"]}
    segs, curdir, curidx = rail_segs(run, lat)
    meta = STAGE_META.get(curdir, (curdir, "agent", ""))
    e = lat.get((run["id"], curdir))
    phase = run["current_stage"].split(".", 1)[1] if "." in run["current_stage"] else ""
    stage_label = f"{curidx + 1} of {len(BOARD_DIRS)} · {curdir.split('-', 1)[1]}" + \
                  (f" {phase}" if phase else "")
    a = pend_by_run.get(run["id"])
    verdict = None
    if run["status"] not in ("done", "cancelled"):
        verdict = report_verdict(report_text(run["id"], curdir))

    if a is not None:
        group = "needs_you"
        gate = GATE_SHORT.get(a["gate"], a["gate"])
        d_chip = ("Blocked", "blocked") if verdict == "BLOCKED" else ("Waiting", "gate")
        wait_main, why = ("You", f" — {gate}"), (
            "report status: BLOCKED — read it before approving"
            if verdict == "BLOCKED" else GATE_META.get(a["gate"], ("", ""))[1][:70])
        elapsed, cold = ago((now - a["requested_at"]).total_seconds()), False
        dot_kind = "gate"
    elif run["status"] == "failed":
        group, d_chip, dot_kind = "stuck", ("Failed", "blocked"), "fail"
        err = (e["error"] or "").splitlines()[0][:70] if e and e["error"] else "see run page"
        wait_main, why = ("Nobody", " — failed, needs rework"), err
        elapsed, cold = ago((now - run["updated_at"]).total_seconds()), False
    elif workstation_blocked(run, snap["online"]):
        group, d_chip, dot_kind = "stuck", ("No runner", "warn"), "fail"
        wait_main = ("Design workstation", " — offline")
        why = "start pipeline.py daemon --runner workstation"
        elapsed, cold = ago((now - run["updated_at"]).total_seconds()), False
    elif run["status"] in ("running", "executing"):
        group, dot_kind = "working", "live"
        runner = STAGE_RUNNER.get(run["current_stage"], "ec2")
        if run["status"] == "executing":
            d_chip = ("Running", "ok")
            hb = e["heartbeat_at"] if e and e["heartbeat_at"] else None
            why = f"runner {runner}" + (f" · heartbeat {ago((now - hb).total_seconds())} ago" if hb else "")
        else:
            d_chip = ("Queued", "")
            why = f"waiting for a {runner} daemon slot"
        wait_main = ("Agent", f" — {meta[0].split('·', 1)[1].strip()}")
        started = e["started_at"] if e and e["status"] in ("running",) else run["updated_at"]
        elapsed, cold = ago((now - started).total_seconds()), False
    elif run["status"] in ("done", "cancelled"):
        group, dot_kind = "closed", "idle"
        d_chip = ("Shipped", "ok") if run["status"] == "done" else \
                 (f"{led.get('max_att', 1)} attempts", "warn") if led.get("max_att", 1) > 1 \
                 else ("Cancelled", "")
        when = (run["completed_at"] or run["updated_at"])
        wait_main = ("Nobody", f" — closed {when:%b %d}")
        why = f"{run['status']} at stage {curidx + 1} · {curdir}"
        elapsed, cold = f"{when:%b %d}", True
    else:                                    # waiting_gate but no approval row
        group, d_chip, dot_kind = "stuck", ("No gate", "warn"), "fail"
        wait_main = ("Nobody", " — gate open but no approval row")
        why = "inconsistent state — check pipeline.py"
        elapsed, cold = ago((now - run["updated_at"]).total_seconds()), False

    models = led.get("models", set())
    tot, inp, cached = led.get("tot", 0), led.get("inp", 0), led.get("cached", 0)
    if tot:
        tok_l1 = fmt_int(tot)
        tok_l2 = f"{round(cached / inp * 100)}% cached" if inp else ""
        model_l1 = next(iter(models)) if len(models) == 1 else ("mixed" if models else "—")
        model_l2 = f"{fmt_int(led.get('reqs'))} requests" if led.get("reqs") else ""
        money = fmt_money(led.get("cost"))
    else:
        tok_l1, tok_l2 = "—", "no ledger"
        model_l1, model_l2 = "—", "unmetered"
        money = "—"
    return group, {
        "href": f"/run/{run['id']}", "dot": dot_kind, "id": run["id"],
        "sub": f"{run['created_by']} · opened {run['created_at']:%b %d}",
        "stage_label": stage_label, "segs": segs, "chip": d_chip,
        "wait_main": wait_main, "wait_why": why, "elapsed": elapsed,
        "elapsed_cold": cold, "model_l1": model_l1, "model_l2": model_l2,
        "tok_l1": tok_l1, "tok_l2": tok_l2, "money": money,
    }


# ── shared page fragments ────────────────────────────────────────────────────

def page(title, body, user, active, now) -> HTMLResponse:
    return HTMLResponse(ui.page(title, body, user, active, f"{now:%H:%M}"))


def runner_sentence(snap) -> tuple[str, str]:
    """(count 'n / m', description) for the runners readout cell."""
    expected = sorted(set(STAGE_RUNNER.values()))
    on = sum(1 for n in expected if snap["online"].get(n))
    bits = []
    for n in expected:
        r = snap["runners"].get(n)
        if r is None:
            bits.append(f"{n} never seen")
        elif snap["online"].get(n):
            bits.append(f"{n} live {ago(r['age'])} ago")
        else:
            bits.append(f"{n} last seen {ago(r['age'])} ago")
    return f"{on}<small> / {len(expected)}</small>", " · ".join(bits)


def today_spend(snap) -> tuple[float, int, str]:
    cost = sum(est_cost_usd(r["inp"], r["cached"], r["outp"], r["model"])
               for r in snap["today"])
    n = sum(r["n"] for r in snap["today"])
    models = sorted({r["model"] for r in snap["today"] if r["model"]})
    return cost, n, ", ".join(models) if models else "—"


def gate_card(a, run, now, inline: bool = True) -> str:
    """One pending approval, payload rendered inline. Same component on /gates
    and /run/{id}. The decision itself stays a server-side POST."""
    payload = _payload(a)
    gate_title, gate_desc = GATE_META.get(a["gate"], (a["gate"], ""))
    stage = payload.get("stage") or (run["current_stage"] if run else "")
    dir_ = STAGE_DIR.get(stage, stage)
    text = report_text(a["run_id"], dir_) if dir_ else None
    verdict = report_verdict(text)
    openq = report_open_question(text)
    age = ago((now - a["requested_at"]).total_seconds())

    bits = [f"""<div class='ghead'><div>
        <div class='gid'><a href='/run/{H(a["run_id"])}'>{H(a["run_id"])}</a>
          · after {H(dir_ or "?")}</div>
        <h2>{H(gate_title)}</h2></div>
        <div class='gage'>waiting {H(age)}<br>
          <span style='color:var(--text-dim)'>opened {a["requested_at"]:%b %d %H:%M} UTC</span></div>
      </div><p class='gdesc'>{H(gate_desc)}</p>"""]

    if verdict == "BLOCKED":
        q = f"<span class='q'>“{H(openq)}”</span>" if openq else ""
        bits.append(
            f"<div class='blockwarn'><b>This stage's own report says BLOCKED.</b> "
            f"The database marked the execution succeeded, but the report's verdict "
            f"did not — approving here approves a stage that says it isn't done. "
            f"Its open question:{q}</div>")

    h = payload.get("handoff") or {}
    if h:                                        # ux_signoff: the rich handoff
        cards = []
        for o in h.get("options", []):
            rec = o.get("name") == h.get("recommended")
            imgs = "".join(
                f"<a href='/file/{H(png)}' target='_blank'><img src='/file/{H(png)}' "
                f"alt='{H(o.get('name', '?'))}' loading='lazy'></a>"
                for png in o.get("pngs", []))
            star = "<span class='chip gate'>Recommended</span>" if rec else ""
            cards.append(
                f"<div class='gopt{' rec' if rec else ''}'>"
                f"<div class='on'><b>{H(o.get('name', '?'))}</b>{star}</div>"
                f"<div class='axis'>{H(o.get('axis', ''))}</div>{imgs}</div>")
        bits.append(f"<div class='gopts'>{''.join(cards)}</div>")
        meta_bits = []
        if h.get("paper_url"):
            meta_bits.append(f"<a href='{H(h['paper_url'])}' target='_blank' "
                             f"style='color:var(--dawn-3)'>open the Paper canvas ↗</a>")
        m = h.get("metrics") or {}
        if m.get("divergence_generated"):
            meta_bits.append(f"<b>{m.get('divergence_kept', '?')}</b> of "
                             f"<b>{m['divergence_generated']}</b> divergence options kept")
        if m.get("png_scale"):
            meta_bits.append(f"png {H(str(m['png_scale']))}")
        meta_bits.append(
            f"video: <b>{H(str(h['video']))}</b>" if h.get("video")
            else "no walkthrough video recorded")
        bits.append(f"<div class='gmeta'>{' · '.join(meta_bits)}</div>")
    elif text and inline:                        # plan_signoff etc: the report IS the payload
        bits.append(f"<details class='report' open><summary>The report being approved — "
                    f"{H(dir_)}/report.md</summary>"
                    f"<div class='prose'>{render_markdown(text)}</div></details>")
    elif inline:
        bits.append("<p class='gdesc'>No report found for this stage — the run "
                    "folder has nothing to show. Decide from the run page evidence.</p>")

    nxt = ""
    if run:
        try:
            i = STAGE_SEQ.index(run["current_stage"])
            if i + 1 < len(STAGE_SEQ):
                nd = STAGE_DIR.get(STAGE_SEQ[i + 1], STAGE_SEQ[i + 1])
                nxt = f" — starts {STAGE_META.get(nd, (nd,))[0]}"
            else:
                nxt = " — the run is complete"
        except ValueError:
            pass
    confirm = (" onsubmit=\"return confirm('The report says BLOCKED — approve anyway?')\""
               if verdict == "BLOCKED" else "")
    bits.append(f"""<div class='gact'>
      <form method='post' action='/gate/{a["id"]}/approve' style='display:flex;gap:10px;flex:1;min-width:300px'{confirm}>
        <input type='text' name='note' placeholder='decision note — recorded in the audit log'>
        <button class='btn primary'>Approve{H(nxt)}</button></form>
      <form method='post' action='/gate/{a["id"]}/reject'>
        <button class='btn danger'>Reject — stop for rework</button></form>
    </div>""")
    return f"<div class='gcard'>{''.join(bits)}</div>"


# ── routes ───────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    if current_user(request):
        return RedirectResponse("/", status_code=303)
    warn = "" if _users() else \
        "<p class='err'>No users configured — set LANTERN_WEB_USERS on the server.</p>"
    err = f"<p class='err'>{H(error)}</p>" if error else ""
    return HTMLResponse(ui.page("Sign in — Lantern", f"""
      <div class='login'><div class='logo'></div>
      <h1>Mission Control</h1>
      <p>The control room for the agent fleet. Sign in to see runs and decide gates.</p>
      {warn}{err}
      <form method='post' action='/login'>
        <input name='username' type='text' placeholder='username' autofocus>
        <input name='password' type='password' placeholder='password'>
        <button class='btn primary'>Sign in</button>
      </form></div>"""))


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


def fmt_k(n) -> str:
    return f"{n / 1000:,.0f}k" if n and n >= 1000 else (str(n) if n else "0")


def led_model(led: dict) -> str:
    models = led.get("models") or set()
    return next(iter(models)) if len(models) == 1 else ("mixed" if models else "—")


def build_card(run, snap: dict, now: datetime) -> tuple[str, str]:
    """One run, one ticket. Returns (column, card html).

    The board is Fredrin's concept, not a pipeline diagram: five workflow
    columns — Queued · Running · Blocked · Review · Done — and the ticket
    moves through them. Where the run is inside the 7-stage pipeline is the
    rail ON the card, not the geometry of the board. Review cards carry the
    actual controls; the decision is still the same server-side POST.
    """
    lat = snap["latest_by_dir"]
    led = snap["ledger"].get(run["id"], {})
    pend_by_run = {x["run_id"]: x for x in snap["pend"]}
    a = pend_by_run.get(run["id"])
    segs, curdir, curidx = rail_segs(run, lat)
    e = lat.get((run["id"], curdir))
    verdict = None
    if run["status"] not in ("done", "cancelled"):
        verdict = report_verdict(report_text(run["id"], curdir))

    title = run_short(run["id"])
    prefix = run["id"][: len(run["id"]) - len(title)].rstrip("-") \
        if run["id"].endswith(title) and title != run["id"] else ""
    stage_name = curdir.split("-", 1)[1]
    stage_lab = f"stage {curidx + 1}/{len(BOARD_DIRS)} · {stage_name}"
    chips: list[tuple[str, str]] = []
    wl = err = acts = ""
    age, cold, hot, dim = "", False, False, False

    if a is not None:
        col, hot = "review", True
        age = ago((now - a["requested_at"]).total_seconds())
        if verdict == "BLOCKED":
            chips.append(("report: blocked", "blocked"))
        chips.append((GATE_SHORT.get(a["gate"], a["gate"]), "gate"))
        wl = ("Waiting on <b>you</b> — the report says BLOCKED, read it first."
              if verdict == "BLOCKED" else
              "Waiting on <b>you</b> — review the evidence, then decide.")
        confirm = (" onsubmit=\"return confirm('The report says BLOCKED — approve anyway?')\""
                   if verdict == "BLOCKED" else "")
        acts = (f"<div class='acts'>"
                f"<form method='post' action='/gate/{a['id']}/approve'{confirm}>"
                f"<button class='btn primary sm'>Approve</button></form>"
                f"<form method='post' action='/gate/{a['id']}/reject' "
                f"onsubmit=\"return confirm('Reject and stop this run for rework?')\">"
                f"<button class='btn danger sm'>Reject</button></form>"
                f"<a class='ev' href='/gates'>evidence →</a></div>")
    elif run["status"] == "executing":
        col = "running"
        age = ago((now - (e["started_at"] if e else run["updated_at"])).total_seconds())
        hb = e["heartbeat_at"] if e and e["heartbeat_at"] else None
        runner = STAGE_RUNNER.get(run["current_stage"], "ec2")
        wl = (f"<b>{H(led_model(led))}</b> working on {H(runner)}"
              + (f" · heartbeat {ago((now - hb).total_seconds())} ago" if hb else ""))
    elif workstation_blocked(run, snap["online"]):
        col = "blocked"
        chips.append(("no runner", "warn"))
        age = ago((now - run["updated_at"]).total_seconds())
        wl = "Needs the <b>design workstation</b>, which is offline."
    elif run["status"] == "running":
        col = "queued"
        runner = STAGE_RUNNER.get(run["current_stage"], "ec2")
        age = ago((now - run["updated_at"]).total_seconds())
        wl = f"Waiting for a free <b>{H(runner)}</b> slot."
    elif run["status"] == "failed":
        col = "blocked"
        chips.append(("failed", "blocked"))
        age = ago((now - run["updated_at"]).total_seconds())
        if e and e["error"]:
            err = e["error"].splitlines()[0][:160]
        wl = "Needs rework — fix, then retry from the run page."
    elif run["status"] in ("done", "cancelled"):
        col, dim, cold = "done", True, True
        when = run["completed_at"] or run["updated_at"]
        age = f"{when:%b %d}"
        if run["status"] == "done":
            chips.append(("shipped", "ok"))
        elif led.get("max_att", 1) > 1:
            chips.append((f"{led['max_att']} attempts", "warn"))
        else:
            chips.append(("cancelled", ""))
        wl = f"{run['status'].capitalize()} at stage {curidx + 1} · {H(stage_name)}"
    else:                                    # waiting_gate but no approval row
        col = "blocked"
        chips.append(("no gate", "warn"))
        age = ago((now - run["updated_at"]).total_seconds())
        wl = "Gate open but no approval row — check pipeline.py."

    chips_html = "".join(chip(t, k) for t, k in chips)
    foot = ""
    if led.get("tot"):
        cpct = f" · {round(led['cached'] / led['inp'] * 100)}% cached" if led.get("inp") else ""
        foot = (f"<div class='foot'><span class='m'>{H(fmt_money(led['cost']))}</span>"
                f"<span>{H(led_model(led))} · {fmt_k(led['tot'])} tok{cpct}</span></div>")
    card = (f"<div class='kcard{' hot' if hot else ''}{' dim' if dim else ''}'>"
            f"<a class='title' href='/run/{H(run['id'])}'>{H(title)}</a>"
            f"<div class='meta'>{H(prefix)}{' · ' if prefix else ''}{H(run['created_by'])}</div>"
            + (f"<div class='chips'>{chips_html}</div>" if chips_html else "")
            + f"<div class='stg'><span class='lab'>{H(stage_lab)}</span>"
              f"<span class='age{' cold' if cold else ''}'>{H(age)}</span></div>"
            + srail(segs)
            + (f"<div class='wl'>{wl}</div>" if wl else "")
            + (f"<div class='kerr'>{H(err)}</div>" if err else "")
            + foot + acts + "</div>")
    return col, card


@app.get("/", response_class=HTMLResponse)
async def board(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    p = await get_pool()
    snap = await snapshot(p)
    now = datetime.now(timezone.utc)

    cols: dict[str, list[str]] = {k: [] for k in
                                  ("queued", "running", "blocked", "review", "done")}
    for run in snap["runs"]:
        col, card = build_card(run, snap, now)
        if col == "done" and (now - run["updated_at"]).total_seconds() > 48 * 3600:
            continue
        cols[col].append(card)

    cost_today, _n_today, _models = today_spend(snap)
    tripwire = float(os.environ.get("LANTERN_DAILY_SPEND_ALARM_USD", "50"))
    sep = "<span class='sep'>·</span>"
    ec2 = snap["runners"].get("ec2")
    ec2_bit = (f"ec2 <b>live</b>" if ec2 and snap["online"].get("ec2")
               else f"ec2 last seen {ago(ec2['age'])} ago" if ec2
               else "<span class='bad'>ec2 never seen</span>")
    ws_bit = ("workstation <b>live</b>" if snap["online"].get("workstation")
              else "<span class='warn'>workstation offline — stage 1 can't start</span>")
    n_rev, n_run = len(cols["review"]), len(cols["running"])
    statusline = (
        f"<div class='statusline'>"
        f"<span><span class='num'>{n_rev}</span> waiting on you</span>{sep}"
        f"<span><span class='num'>{n_run}</span> running</span>{sep}"
        f"<span>spent today <span class='num'>{H(fmt_money(cost_today))}</span>"
        f" of ${tripwire:.0f}</span>{sep}"
        f"<span>{ec2_bit}</span>{sep}<span>{ws_bit}</span></div>")

    lat = snap["gate_latency"]
    lat_html = ui.gate_ledger(ledger_metrics(lat) if lat is not None else None)

    COLS = [
        ("queued",  "Queued",  "Empty. Runs wait here for a runner slot before an agent picks them up."),
        ("running", "Running", "No agent is working right now. A ticket moves here when a daemon claims it."),
        ("blocked", "Blocked", "Nothing has failed."),
        ("review",  "Review",  "Nothing needs you. When a stage finishes behind a gate, its ticket lands here."),
        ("done",    "Done",    "Nothing closed in the last 48 hours."),
    ]
    kb = []
    for key, name, empty in COLS:
        hot = key == "review" and bool(cols[key])
        head = (f"<div class='kbhead{' hot' if hot else ''}'>"
                f"<span class='n'>{H(name)}</span><span class='c'>{len(cols[key])}</span></div>")
        content = "".join(cols[key]) if cols[key] else f"<p class='kbempty'>{H(empty)}</p>"
        kb.append(f"<div class='kbcol'>{head}{content}</div>")

    return page("Board — Lantern Mission Control",
                statusline + lat_html + f"<section class='kb'>{''.join(kb)}</section>",
                user, "/", now)


@app.get("/gates", response_class=HTMLResponse)
async def gates(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    p = await get_pool()
    now = datetime.now(timezone.utc)
    pend = await p.fetch(
        "SELECT * FROM approvals WHERE status='pending' ORDER BY requested_at")
    runs = {r["id"]: r for r in await p.fetch(
        "SELECT * FROM runs WHERE id = ANY($1)",
        list({a["run_id"] for a in pend}))}
    history = await p.fetch(
        """SELECT * FROM approvals WHERE status != 'pending'
           ORDER BY decided_at DESC NULLS LAST LIMIT 12""")

    body = [f"<h2 class='sect'>{len(pend)} gate{'s' if len(pend) != 1 else ''} waiting, oldest first</h2>",
            "<p class='sub'>Approving advances the run; rejecting stops it for rework. "
            "Every decision lands in the audit log with your name on it.</p>"]
    if pend:
        for a in pend:
            body.append(gate_card(a, runs.get(a["run_id"]), now))
    else:
        body.append("<p class='empty' style='margin-top:16px'><b>Nothing is waiting "
                    "on a human.</b> When a stage finishes behind a gate, it appears "
                    "here with its evidence.</p>")

    if history:
        rows = []
        for a in history:
            k = {"approved": "ok", "rejected": "blocked", "expired": ""}.get(a["status"], "")
            note = " ".join((a["decision_note"] or "").split())[:150]
            when = a["decided_at"] or a["requested_at"]
            rows.append(
                f"<div class='att'><span class='tm'>{when:%b %d %H:%M}</span>"
                f"<span class='rn'><a href='/run/{H(a['run_id'])}'>"
                f"{H(run_short(a['run_id']))}</a> · {H(GATE_SHORT.get(a['gate'], a['gate']))}</span>"
                f"<span class='er ok' style='color:var(--text-muted)'>{H(note) or '—'}</span>"
                f"<span class='at'>{chip(a['status'], k)}<br>"
                f"<span style='letter-spacing:.04em'>{H(a['decided_by'] or '')}</span></span></div>")
        body.append(f"<section class='feed decided'><div class='th'>"
                    f"<span class='caps'>Decided · most recent</span>"
                    f"<span class='caps'>{len(history)} shown</span></div>{''.join(rows)}</section>")

    return page("Gates — Lantern Mission Control",
                f"<main class='page'>{''.join(body)}</main>", user, "/gates", now)


@app.get("/runs", response_class=HTMLResponse)
async def runs_index(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    p = await get_pool()
    snap = await snapshot(p)
    now = datetime.now(timezone.utc)
    open_s, closed_s = [], []
    for run in snap["runs"]:
        group, d = build_strip(run, snap, now)
        (closed_s if group == "closed" else open_s).append(
            strip(d, hot=(group == "needs_you"), dim=(group == "closed")))
    body = [group_head("Open", len(open_s)),
            f"<div class='stripwrap'>{strip_header()}{''.join(open_s)}</div>" if open_s
            else "<p class='empty'><b>No open runs.</b> Start one with "
                 "<code>pipeline.py run</code>.</p>",
            group_head("Closed", len(closed_s), "full history"),
            f"<div class='stripwrap'>{''.join(closed_s)}</div>" if closed_s
            else "<p class='empty'><b>Nothing has closed yet.</b></p>"]
    return page("Runs — Lantern Mission Control",
                f"<main class='page'>{''.join(body)}</main>", user, "/runs", now)


@app.get("/spend", response_class=HTMLResponse)
async def spend(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    p = await get_pool()
    now = datetime.now(timezone.utc)
    cols = """model, coalesce(sum(input_tokens),0)::bigint AS inp,
              coalesce(sum(cached_input_tokens),0)::bigint AS cached,
              coalesce(sum(output_tokens),0)::bigint AS outp, count(*)::int AS n,
              count(*) FILTER (WHERE total_tokens IS NULL)::int AS unmetered"""
    daily = await p.fetch(
        f"""SELECT date_trunc('day', started_at)::date AS day, {cols}
            FROM stage_executions
            WHERE started_at >= now() - interval '14 days'
            GROUP BY 1, model ORDER BY 1 DESC""")
    top = await p.fetch(
        f"""SELECT run_id, {cols} FROM stage_executions
            WHERE started_at >= now() - interval '14 days'
            GROUP BY run_id, model
            ORDER BY coalesce(sum(total_tokens),0) DESC LIMIT 15""")
    alltime = await p.fetch(f"SELECT {cols} FROM stage_executions GROUP BY model")
    tripwire = float(os.environ.get("LANTERN_DAILY_SPEND_ALARM_USD", "50"))

    total_cost = sum(est_cost_usd(r["inp"], r["cached"], r["outp"], r["model"]) for r in alltime)
    total_unmetered = sum(r["unmetered"] for r in alltime)
    today_rows = [r for r in daily if r["day"] == now.date()]
    today_cost = sum(est_cost_usd(r["inp"], r["cached"], r["outp"], r["model"]) for r in today_rows)

    body = [f"""<section class='readout' style='grid-template-columns:repeat(3,1fr) auto'>
      <div><div class='caps'>Spent today</div>
        <div class='v'>{H(fmt_money(today_cost))}<small> / {tripwire:.0f}</small></div>
        <div class='d'>{min(today_cost / tripwire * 100, 999):.0f}% of the daily tripwire</div></div>
      <div><div class='caps'>Ledger total</div><div class='v'>{H(fmt_money(total_cost))}</div>
        <div class='d'>every metered execution, all time · est.</div></div>
      <div><div class='caps'>Unmetered</div>
        <div class='v{' bad' if total_unmetered else ''}'>{total_unmetered}</div>
        <div class='d'>executions with no token counts — real spend is higher</div></div>
      <div class='cta'></div></section>"""]

    if daily:
        rows = []
        for r in daily:
            # A model-less bucket is the unmetered pile (crashed before the usage
            # line): printing 0 tokens / $0.00 for it would be a lie.
            if r["model"] is None and not r["inp"]:
                rows.append(
                    f"<tr><td class='d'>{r['day']:%b %d}</td>"
                    f"<td>— unmetered</td><td class='r'>{r['n']}</td>"
                    f"<td class='r'>—</td><td class='r'>—</td><td class='r'>—</td>"
                    f"<td class='r'>—</td><td></td></tr>")
                continue
            cost = est_cost_usd(r["inp"], r["cached"], r["outp"], r["model"])
            w = min(cost / tripwire * 100, 100)
            over = " over" if cost > tripwire else ""
            cpct = f"{round(r['cached'] / r['inp'] * 100)}%" if r["inp"] else "—"
            rows.append(
                f"<tr><td class='d'>{r['day']:%b %d}</td><td>{H(r['model'] or '—')}</td>"
                f"<td class='r'>{r['n']}</td><td class='r'>{fmt_int(r['inp'])}</td>"
                f"<td class='r'>{fmt_int(r['cached'])} · {cpct}</td>"
                f"<td class='r'>{fmt_int(r['outp'])}</td>"
                f"<td class='r'>{H(fmt_money(cost))}</td>"
                f"<td><span class='bar'><i class='{over.strip()}' style='width:{w:.0f}%'></i></span></td></tr>")
        body.append(f"""<h2 class='sect'>By day, last 14</h2>
          <p class='sub'>The bar is the day against the ${tripwire:.0f} tripwire.</p>
          <div class='stripwrap'><table class='spendtbl'>
          <tr><th>Day</th><th>Model</th><th class='r'>Stages</th><th class='r'>Input</th>
          <th class='r'>Cached</th><th class='r'>Output</th><th class='r'>Est. $</th><th></th></tr>
          {''.join(rows)}</table></div>""")
    else:
        body.append("<p class='empty' style='margin-top:20px'><b>No metered executions "
                    "in the last 14 days.</b></p>")

    if top:
        rows = "".join(
            f"<tr><td class='d'><a href='/run/{H(r['run_id'])}'>{H(r['run_id'])}</a></td>"
            + (f"<td>— unmetered</td><td class='r'>{r['n']}</td>"
               f"<td class='r'>—</td><td class='r'>—</td><td class='r'>—</td></tr>"
               if r["model"] is None and not r["inp"] else
               f"<td>{H(r['model'] or '—')}</td><td class='r'>{r['n']}</td>"
               f"<td class='r'>{fmt_int(r['inp'])}</td><td class='r'>{fmt_int(r['outp'])}</td>"
               f"<td class='r'>{H(fmt_money(est_cost_usd(r['inp'], r['cached'], r['outp'], r['model'])))}</td></tr>")
            for r in top)
        body.append(f"""<h2 class='sect'>By run, last 14 days</h2>
          <div class='stripwrap'><table class='spendtbl'>
          <tr><th>Run</th><th>Model</th><th class='r'>Stages</th><th class='r'>Input</th>
          <th class='r'>Output</th><th class='r'>Est. $</th></tr>{rows}</table></div>""")

    p_in = os.environ.get("LANTERN_PRICE_IN_PER_M", "4")
    p_c = os.environ.get("LANTERN_PRICE_CACHED_IN_PER_M", "1")
    p_out = os.environ.get("LANTERN_PRICE_OUT_PER_M", "20")
    body.append(f"<p class='footnote'>Token counts are exact; dollars are estimates at "
                f"${H(p_in)} / ${H(p_c)} cached / ${H(p_out)} per 1M tokens until Azure "
                f"invoice lines confirm the rates (pipeline.py, P0.4). Executions that "
                f"crashed before reporting usage have no token counts and are flagged "
                f"unmetered — real spend is higher than shown.</p>")

    return page("Spend — Lantern Mission Control",
                f"<main class='page'>{''.join(body)}</main>", user, "/spend", now)


@app.get("/run/{run_id}", response_class=HTMLResponse)
async def run_page(run_id: str, request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    p = await get_pool()
    now = datetime.now(timezone.utc)
    run = await p.fetchrow("SELECT * FROM runs WHERE id = $1", run_id)
    if not run:
        raise HTTPException(404, "run not found")
    execs = await p.fetch(
        "SELECT * FROM stage_executions WHERE run_id = $1 ORDER BY started_at", run_id)
    arts = await p.fetch(
        "SELECT stage, kind, uri FROM artifacts WHERE run_id = $1 ORDER BY created_at", run_id)
    events = await p.fetch(
        "SELECT actor, type, data, at FROM events WHERE run_id = $1 ORDER BY at DESC LIMIT 100",
        run_id)
    pend = await p.fetch(
        "SELECT * FROM approvals WHERE run_id = $1 AND status='pending'", run_id)

    by_dir: dict[str, list] = {}
    for e in execs:
        by_dir.setdefault(STAGE_DIR.get(e["stage"], e["stage"]), []).append(e)
    curdir = STAGE_DIR.get(run["current_stage"], run["current_stage"])

    # totals
    cost = tot = inp = cached = 0
    unmetered = 0
    for e in execs:
        cost += est_cost_usd(e["input_tokens"], e["cached_input_tokens"],
                             e["output_tokens"], e["model"])
        tot += e["total_tokens"] or 0
        inp += e["input_tokens"] or 0
        cached += e["cached_input_tokens"] or 0
        unmetered += 1 if e["total_tokens"] is None else 0

    status_chip = {"running": ("Queued", ""), "executing": ("Running", "ok"),
                   "waiting_gate": ("Waiting on a human", "gate"),
                   "failed": ("Failed", "blocked"), "done": ("Shipped", "ok"),
                   "cancelled": ("Cancelled", "")}.get(run["status"], (run["status"], ""))
    verdict = report_verdict(report_text(run_id, curdir)) \
        if run["status"] not in ("done", "cancelled") else None
    v_chip = chip("report: blocked", "blocked") if verdict == "BLOCKED" else ""
    repo_bit = (f"<code>{H(run['product_repo'])}</code> @ {H(run['product_branch'] or 'default')}"
                if run.get("product_repo") else
                chip("no product repo set — stage 2+ blocks", "warn"))
    tok_line = (f"{fmt_int(tot)} tok · {round(cached / inp * 100) if inp else 0}% cached"
                if tot else "no ledger")
    unm_line = f"<br>{unmetered} unmetered execution{'s' if unmetered != 1 else ''}" if unmetered else ""
    body = [f"""<div class='runhead'><div>
        <div class='caps'>Run · pipeline v{H(str(run['pipeline_version']))}</div>
        <h1>{H(run_id)}</h1>
        <div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px'>
          {chip(*status_chip)}{v_chip}</div>
        <div class='meta'>brief <code>{H(run['brief'])}</code><br>
          started by <b>{H(run['created_by'])}</b> · {run['created_at']:%b %d %H:%M} UTC
          · last activity {ago((now - run['updated_at']).total_seconds())} ago<br>
          product repo: {repo_bit}</div></div>
      <div class='totals'><div class='caps'>Est. spend</div>
        <div class='v'>{H(fmt_money(cost) if tot else '—')}</div>
        <div class='d'>{H(tok_line)}{unm_line}</div></div></div>"""]

    for a in pend:
        body.append(gate_card(a, run, now))

    for i, d in enumerate(BOARD_DIRS):
        name, actor, desc = STAGE_META.get(d, (d, "agent", ""))
        tries = sorted(by_dir.get(d, []), key=lambda e: e["started_at"], reverse=True)
        latest = tries[0] if tries else None
        cur = d == curdir and run["status"] not in ("done",)
        cls = "scard cur" if cur else ("scard" if tries else "scard pend")
        st = {"succeeded": ("Succeeded", "ok"), "failed": ("Failed", "blocked"),
              "running": ("Running", "ok"), "waiting_gate": ("Waiting", "gate"),
              "skipped": ("Skipped", "")}.get(latest["status"], (latest["status"], "")) \
            if latest else ("Not started", "")
        d_cost = sum(est_cost_usd(e["input_tokens"], e["cached_input_tokens"],
                                  e["output_tokens"], e["model"]) for e in tries)
        d_tot = sum(e["total_tokens"] or 0 for e in tries)
        right = ""
        if latest:
            dur = ((latest["finished_at"] or now) - latest["started_at"]).total_seconds()
            right = f"{ago(dur)}"
            right += (f"<br>{fmt_int(d_tot)} tok · {H(fmt_money(d_cost))}" if d_tot
                      else "<br>unmetered")
        phase = (f" · {latest['stage'].split('.', 1)[1]}"
                 if latest and "." in latest["stage"] else "")
        head = (f"<div class='shead'><span class='nm'>{H(name)}</span>"
                f"<span class='actor'>{'🤖 agent' if actor == 'agent' else '👤 human'}"
                f" · {H(DIR_RUNNER.get(d, 'ec2'))}{H(phase)}</span>"
                f"{chip(*st)}{chip('current', 'gate') if cur else ''}"
                f"<span class='right'>{right}</span></div>")
        bits = [head, f"<div class='sdesc'>{H(desc)}</div>"]
        if latest and latest["error"]:
            bits.append(f"<div class='err'>{H(latest['error'][:600])}</div>")
        if len(tries) > 1 or any(t["status"] == "failed" for t in tries):
            rows = "".join(
                f"<div>attempt {t['attempt']} · "
                f"<span class='{'ok' if t['status'] == 'succeeded' else 'bad' if t['status'] == 'failed' else ''}'>"
                f"{H(t['status'])}</span> · {H(t['runner'])} · "
                f"{ago(((t['finished_at'] or now) - t['started_at']).total_seconds())}"
                + (f" · {H((t['error'] or '').splitlines()[0][:90])}" if t["error"] else "")
                + "</div>"
                for t in tries)
            bits.append(f"<div class='tries'>{rows}</div>")
        text = report_text(run_id, d)
        if text:
            v = report_verdict(text)
            v_note = f" — report status: {v}" if v else ""
            bits.append(f"<details class='report'><summary>report.md{H(v_note)}</summary>"
                        f"<div class='prose'>{render_markdown(text)}</div></details>")
        stage_arts = [a for a in arts if a["stage"] == d]
        if stage_arts:
            links = "".join(
                f"<a href='{H(art_href(a['uri']))}' target='_blank'>"
                f"{KIND_ICON.get(a['kind'], '')}{H(a['kind'])}</a>"
                for a in stage_arts)
            bits.append(f"<div class='arts'>{links}</div>")
        body.append(f"<div class='{cls}'>{''.join(bits)}</div>")

    if events:
        rows = []
        for e in events:
            data = e["data"]
            if isinstance(data, str):
                snippet = " ".join(data.split())[:120]
            else:
                snippet = json.dumps(data)[:120] if data else ""
            rows.append(f"<div class='evt'><span class='tm'>{e['at']:%b %d %H:%M:%S}</span>"
                        f"<span class='ac'>{H(e['actor'])}</span>"
                        f"<span class='ty'><b>{H(e['type'].replace('_', ' '))}</b>"
                        f"<span>{H(snippet)}</span></span></div>")
        body.append(f"<h2 class='sect'>Audit log</h2><p class='sub'>Every action on "
                    f"this run, newest first — {len(events)} shown.</p>"
                    f"<div>{''.join(rows)}</div>")

    return page(f"{run_id} — Lantern Mission Control",
                f"<main class='page'>{''.join(body)}</main>", user, "/runs", now)


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
