"""Lantern Mission Control v3 — the factory's face (docs/MISSION-CONTROL.md, D22).

    uvicorn app:app --host 0.0.0.0 --port 8080     (or: python app.py)

Work, reviews, and chat are the primary navigation. Home is a compact searchable
queue; review evidence opens on demand. Run pages show recent actual activity,
with the full execution lanes and technical artifacts in disclosure sections.
See docs/MISSION-CONTROL.md for routes and interaction details.

Two hard rules carried over unchanged from v1:
  * Gate integrity: approvals are written server-side via
    POST /gate/{approval_id}/{decision}, fail-closed, against LANTERN_WEB_USERS.
    Nothing client-side can approve anything; the keyboard map only submits forms.
  * Honesty: pages render what the database and the run folder actually say —
    including when they disagree. A stage execution can be 'succeeded' while its own
    report's Status: line says BLOCKED; that disagreement is first-class.

Auth: HMAC cookie sessions behind a login page — no data is served
unauthenticated. Users from LANTERN_WEB_USERS ("name:pw,name:pw"); signing key
from LANTERN_WEB_SECRET (falls back to a hash of LANTERN_WEB_USERS).
"""

import asyncio
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
from urllib.parse import quote

import asyncpg
import markdown as md
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

AZURE_RUNNER = Path(__file__).resolve().parents[1] / "azure-runner"
sys.path.insert(0, str(AZURE_RUNNER))
load_dotenv(AZURE_RUNNER / ".env")

from pipeline import (  # noqa: E402
    FEATURE_STAGES, REWORK_TARGETS, STAGE_DIR, STAGE_INDEX, STAGE_RUNNER, ProductTargetError,
    advance, cmd_rework, db_urls, est_cost_usd, log_event, render_runboard,
    verify_product_target, work_branch,
)
from orchestrator import CODING_BRANCH_PREFIXES, ROLE_FOR_STAGE  # noqa: E402
import factory  # noqa: E402
import catalog  # noqa: E402
import chat  # noqa: E402
import cost as costmod  # noqa: E402
import drawer  # noqa: E402
import lanes  # noqa: E402
import traceability  # noqa: E402
import ui  # noqa: E402
import workspace  # noqa: E402
import worklist  # noqa: E402
import lifecycle  # noqa: E402
from ui import H, ago, chip, fmt_int, fmt_k, fmt_money  # noqa: E402

# Board columns = run-folder dirs; split stage-1 executions share one column.
BOARD_DIRS = list(dict.fromkeys(d for _, d, *_ in FEATURE_STAGES))
STAGE_SEQ = [s for s, *_ in FEATURE_STAGES]           # full stage names, in order
DIR_RUNNER = {}                                       # dir -> runner of its first stage
for _s, _d, *_rest in FEATURE_STAGES:
    DIR_RUNNER.setdefault(_d, STAGE_RUNNER.get(_s, "ec2"))

REPO = Path(__file__).resolve().parents[2]
app = FastAPI(title="Lantern Mission Control")
pool: asyncpg.Pool | None = None

# Which consultable role owns each stage dir (run-page "consult about this run" links).
DIR_ROLE = {d: ROLE_FOR_STAGE.get(d, "coding" if d == "03-coding" else None)
            for d in dict.fromkeys(s[1] for s in FEATURE_STAGES)}

SESSION_COOKIE = "lantern_session"
SESSION_TTL = 7 * 24 * 3600
EC2_SLOTS = 2            # daemon concurrency cap (docs/ORCHESTRATION.md, D10)

STAGE_META = {
    "00-story":       ("0 · Research & story",     "agent",  "A read-only researcher maps the codebase, then the story writer turns the brief into numbered acceptance criteria you approve."),
    "01-ui-ux":       ("1 · UI/UX design",         "agent",  "Explores 2–3 flow options, builds a prototype, records a walkthrough video."),
    "02-pre-coding":  ("2 · Planning",              "agent",  "Blast-radius analysis, schema plan, ordered task plan."),
    "03-coding":      ("3 · Coding",                "human",  "The plan is implemented — by the assigned developer in their own session, or in auto mode by the coding agent, which ends in a pull request."),
    "04-qa-dev":      ("4 · QA in dev",             "agent",  "Executes a test charter against the dev build — every session on video."),
    "05-post-coding": ("5 · Review & validation",   "agent",  "Cleanliness, hidden tech debt, backward compatibility — then the validator gives every acceptance criterion a verdict with evidence."),
    "06-security":    ("6 · Security & deploy risk","agent",  "Vulnerabilities, dependency audit, go/no-go for staging."),
    "07-qa-staging":  ("7 · QA in staging",         "agent",  "Re-runs the charter on staging, verifies analytics events, videos for sign-off."),
}
GATE_META = {
    "story_signoff":  ("Approve the story",      "Numbered acceptance criteria and edge cases — everything downstream is planned, built, tested and validated against these."),
    "ux_signoff":     ("Pick the UX option",     "Watch the walkthrough, then approve the recommended flow (or reject with a note)."),
    "plan_signoff":   ("Approve plan & schema",  "Schema changes always need a human yes before any code is written."),
    "code_complete":  ("Code-complete?",         "Every planned task is done and tests are green — the developer confirms it, or in auto mode you review the coding agent's pull request and approve here."),
    "staging_deploy": ("Deploy to staging",      "Security said GO — a human performs the staging deploy, then approves here."),
    "prod_signoff":   ("Ship to production",     "The final human decision. Review the staging QA videos first."),
}
GATE_SHORT = {
    "story_signoff": "story sign-off",
    "ux_signoff": "UX sign-off", "plan_signoff": "plan sign-off",
    "code_complete": "code-complete", "staging_deploy": "staging deploy",
    "prod_signoff": "prod sign-off",
}
KIND_ICON = {"qa_video": "🎬 ", "design_png": "🖼 ", "paper_file": "🎨 ",
             "flow_spec": "🗺 ", "design_handoff": "📦 ", "report": "📄 "}
VALIDATION_CHIP = {"covered": "ok", "missing": "blocked", "skipped": "warn",
                   "off-spec": "blocked", "insecure": "blocked"}


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


# ── chat surface (docs/CHAT.md): routes live in chat.py, model work in
# tools/azure-runner/chat_service.py. setup() hands chat our pool/auth/shell so
# the login rules stay defined exactly once, here.

def page_for_chat(title, body, user, active, clock, auto_reload=True):
    return ui.page(title, body, user, active, clock, auto_reload=auto_reload, kind="chat")


app.include_router(chat.setup(get_pool=get_pool, current_user=current_user,
                              page=page_for_chat, render_markdown=lambda t: render_markdown(t)))


@app.on_event("startup")
async def _chat_startup() -> None:
    try:
        await chat.on_startup()     # idempotent schema upgrade + reap orphaned turns
    except Exception as e:          # noqa: BLE001 — the board must come up even if
        print(f"chat startup skipped: {e}", file=sys.stderr)  # Postgres is briefly away


@app.on_event("shutdown")
async def _chat_shutdown() -> None:
    await chat.on_shutdown()        # close SSE streams so restarts don't hang on them


# ── report honesty: what does the stage's own report say? ────────────────────

VERDICT_RE = re.compile(r"\*\*Status:\*\*\s*([A-Z][A-Z-]*)")
OPENQ_RE = re.compile(r"##\s*Open questions?[^\n]*\n+\s*-?\s*(.+)")


def run_root(run_id: str) -> Path:
    return REPO / "workflow" / "runs" / run_id


def report_path(run_id: str, dir_: str) -> Path:
    return run_root(run_id) / dir_ / "report.md"


def report_text(run_id: str, dir_: str) -> str | None:
    try:
        return report_path(run_id, dir_).read_text(encoding="utf-8")
    except OSError:
        return None


def run_file(run_id: str, rel: str) -> str | None:
    try:
        return (run_root(run_id) / rel).read_text(encoding="utf-8")
    except OSError:
        return None


def run_json(run_id: str, rel: str):
    try:
        return json.loads((run_root(run_id) / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def report_verdict(text: str | None) -> str | None:
    if not text:
        return None
    # The LAST status line counts (D17: second executions append their section).
    ms = VERDICT_RE.findall(text)
    return ms[-1] if ms else None


def report_open_question(text: str | None) -> str | None:
    if not text:
        return None
    ms = OPENQ_RE.findall(text)
    return ms[-1].strip()[:240] if ms else None


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


def gate_latency_metrics(rows: list[dict]) -> list[dict]:
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


def png_exists(rel) -> bool:
    """Is this repo-relative artifact actually on disk? Same confinement as /file/."""
    try:
        p = (REPO / str(rel)).resolve()
        return p.is_relative_to((REPO / "workflow" / "runs").resolve()) and p.is_file()
    except (OSError, ValueError):
        return False


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
    except asyncpg.PostgresError as e:  # the ledger degrades; the board must not
        print(f"gate latency query failed: {e}", file=sys.stderr)   # post-coding F1
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
    return {"runs": runs, "latest_executions": latest, "latest_by_dir": latest_by_dir, "ledger": ledger,
            "pend": pend, "gate_latency": gate_latency, "runners": runners,
            "online": online, "today": today, "feed": feed}


def run_short(run_id: str) -> str:
    return re.sub(r"^(feat|bug)-\d{8}-", "", run_id)


def workstation_blocked(run, online: dict) -> bool:
    return (run["status"] in ("running", "executing")
            and STAGE_RUNNER.get(run["current_stage"]) == "workstation"
            and not online.get("workstation"))


def page(title, body, user, active, now, kind: str = "", auto_reload: bool = True) -> HTMLResponse:
    return HTMLResponse(ui.page(title, body, user, active, f"{now:%H:%M}",
                                auto_reload=auto_reload, kind=kind))


# ── gate cards: the artifact being decided comes first ───────────────────────

def artbox(title: str, inner: str, sub: str = "", open_: bool = True) -> str:
    """A bounded, scrollable box for the artifact under decision, headed by its path."""
    head = f"<div class='abh'><b>{H(title)}</b>" + (f"<span>{H(sub)}</span>" if sub else "") + "</div>"
    return f"<div class='artbox'>{head}{inner}</div>"


def validation_table(data: dict) -> str:
    rows = []
    for c in data.get("criteria", []) or []:
        if not isinstance(c, dict):
            continue
        st = str(c.get("status", "?"))
        rows.append(f"<tr><td class='id'>{H(str(c.get('id', '?')))}</td>"
                    f"<td>{chip(st, VALIDATION_CHIP.get(st, ''))}</td>"
                    f"<td>{H('; '.join(traceability.evidence_details(c.get('evidence'))))}</td></tr>")
    verdict = str(data.get("verdict", "?"))
    fix = data.get("fix_now") or []
    head = (f"<div class='abh'><b>05-post-coding/validation.json</b>"
            f"{chip('verdict ' + verdict, 'ok' if verdict == 'pass' else 'blocked')}"
            + (f"<span>{len(fix)} fix-now item(s)</span>" if fix else "") + "</div>")
    table = ("<table class='vtbl'><tr><th>AC</th><th>Verdict</th><th>Evidence</th></tr>"
             f"{''.join(rows)}</table>")
    fixrows = "".join(f"<li><b>{H(str(f.get('criterion', '')))}</b> {H(str(f.get('title', '')))}</li>"
                      for f in fix if isinstance(f, dict))
    fixhtml = f"<ul class='commits'>{fixrows}</ul>" if fixrows else ""
    return f"<div class='artbox'>{head}{table}{fixhtml}</div>"


def plan_summary(plan: dict) -> str:
    rows = []
    for t in plan.get("tasks", []) or []:
        if not isinstance(t, dict):
            continue
        rows.append(f"<tr><td class='id'>{H(str(t.get('id', '?')))}</td><td>{H(str(t.get('title', '')))}</td>"
                    f"<td class='id'>{H(str(t.get('size') or '—'))}</td>"
                    f"<td class='id'>{H(', '.join(map(str, t.get('criteria') or [])) or '—')}</td>"
                    f"<td>{'yes' if t.get('hitl') else ''}</td></tr>")
    deferred = "".join(f"<li><b>{H(str(d.get('id')))}</b> deferred — {H(str(d.get('reason', '')))}</li>"
                       for d in (plan.get("deferred_criteria") or []) if isinstance(d, dict))
    scope = ", ".join(map(str, plan.get("write_scope") or [])) or "—"
    builders = plan.get("builders") or []
    chips = (chip("schema changes" if plan.get("schema_changes") else "no schema change",
                  "warn" if plan.get("schema_changes") else "ok")
             + chip("HITL required" if plan.get("hitl_required") else "no HITL flagged",
                    "gate" if plan.get("hitl_required") else ""))
    if builders:
        chips += chip(f"{len(builders)} builders", "tier")
    head = f"<div class='abh'><b>02-pre-coding/plan.json</b>{chips}<span>write scope: {H(scope)}</span></div>"
    table = ("<table class='vtbl'><tr><th>Task</th><th>Title</th><th>Size</th><th>Criteria</th><th>HITL</th></tr>"
             f"{''.join(rows)}</table>")
    return f"<div class='artbox'>{head}{table}" + (f"<ul class='commits'>{deferred}</ul>" if deferred else "") + "</div>"


def review_rounds(run_id: str, payload: dict) -> str:
    """Review-bot rounds (D19): from the run folder first, the gate payload second."""
    rounds: list[dict] = []
    rdir = run_root(run_id) / "03-coding" / "review"
    for p in sorted(rdir.glob("round-*.md")) if rdir.is_dir() else []:
        n = re.sub(r"\D", "", p.stem) or "?"
        rounds.append({"round": n, "file": f"03-coding/review/{p.name}", "text": run_file(run_id, f"03-coding/review/{p.name}")})
    rj = run_json(run_id, "03-coding/review/review.json") or run_json(run_id, "03-coding/review.json")
    for key in ("review_rounds", "reviews", "review"):
        v = payload.get(key)
        if isinstance(v, list):
            for r in v:
                if isinstance(r, dict):
                    rounds.append({"round": str(r.get("round", "?")), "verdict": r.get("verdict"),
                                   "findings": r.get("findings") if isinstance(r.get("findings"), list) else None,
                                   "must_fix": r.get("must_fix"), "text": None})
            break
        if isinstance(v, dict):
            rounds.append({"round": str(v.get("round", "?")), "verdict": v.get("verdict"),
                           "findings": v.get("findings") if isinstance(v.get("findings"), list) else None,
                           "must_fix": v.get("must_fix"), "text": None})
            break
    if rj and not any(r.get("verdict") for r in rounds):
        rounds.append({"round": str(rj.get("round", "?")), "verdict": rj.get("verdict"),
                       "findings": rj.get("findings") if isinstance(rj.get("findings"), list) else None,
                       "must_fix": rj.get("must_fix"), "text": None, "file": "03-coding/review.json"})
    if not rounds:
        return ""
    items = []
    for r in rounds:
        v = r.get("verdict")
        vchip = chip(v, "ok" if v == "approve" else "blocked") if v else ""
        n_f = len(r["findings"]) if isinstance(r.get("findings"), list) else None
        bits = [f"<span class='rn'>round {H(str(r['round']))}</span>", vchip]
        if n_f is not None:
            mf = r.get("must_fix") or []
            bits.append(f"<span>{n_f} finding(s)" + (f" · {len(mf)} must-fix" if mf else "") + "</span>")
        if r.get("file"):
            bits.append(f"<span class='caps'>{H(r['file'])}</span>")
        body = "".join(bits)
        if r.get("text"):
            body += (f"<details class='report' style='flex-basis:100%'><summary>read the round</summary>"
                     f"<div class='prose'>{render_markdown(r['text'])}</div></details>")
        items.append(f"<div class='round'>{body}</div>")
    return (f"<div class='artbox' style='max-height:none'><div class='abh'><b>Review rounds</b>"
            f"<span>{len(rounds)} round(s) before a human was pinged</span></div>"
            f"<div class='rounds' style='padding:10px 14px'>{''.join(items)}</div></div>")


def builders_block(run_id: str, payload: dict) -> str:
    """Parallel builders (D18): the payload's list, or per-builder handoffs on disk."""
    blds = payload.get("builders") if isinstance(payload.get("builders"), list) else []
    if not blds:
        bdir = run_root(run_id) / "03-coding" / "builders"
        for p in sorted(bdir.glob("*/handoff.json")) if bdir.is_dir() else []:
            h = run_json(run_id, f"03-coding/builders/{p.parent.name}/handoff.json") or {}
            blds.append({"name": p.parent.name, "branch": h.get("branch"),
                         "commits": h.get("commit_count", len(h.get("commits") or [])),
                         "files_changed": h.get("files_changed")})
    if not blds:
        return ""
    rows = []
    for b in blds:
        if not isinstance(b, dict):
            continue
        commits = b.get("commits")
        n = len(commits) if isinstance(commits, list) else commits
        files = b.get("files_changed")
        nf = len(files) if isinstance(files, list) else files
        rows.append(f"<tr><td class='id'>{H(str(b.get('name', '?')))}</td>"
                    f"<td class='id'>{H(str(b.get('branch') or '—'))}</td>"
                    f"<td class='id'>{H(str(n if n is not None else '—'))}</td>"
                    f"<td class='id'>{H(str(nf if nf is not None else '—'))}</td></tr>")
    return (f"<div class='artbox' style='max-height:none'><div class='abh'><b>Builders</b>"
            f"<span>{len(rows)} scoped builders merged by the host</span></div>"
            "<table class='vtbl'><tr><th>Builder</th><th>Branch</th><th>Commits</th><th>Files</th></tr>"
            f"{''.join(rows)}</table></div>")


def media_links(run_id: str, dir_: str) -> str:
    data = run_json(run_id, f"{dir_}/media-manifest.json") or {}
    ups = data.get("uploaded") if isinstance(data, dict) else None
    if not ups:
        return ""
    links = "".join(
        f"<a href='{H(art_href(str(u.get('uri', ''))))}' target='_blank'>🎬 session {H(str(u.get('session', '?')))}"
        f" · attempt {H(str(u.get('attempt', '?')))}</a>"
        for u in ups if isinstance(u, dict))
    return f"<div class='arts'>{links}</div>"


def gate_artifacts(a, run, payload: dict, dir_: str, text: str | None, inline: bool) -> list[str]:
    """The artifact each gate is deciding, first — then the supporting report."""
    run_id = a["run_id"]
    bits: list[str] = []
    gate = a["gate"]
    shown_report = False
    if gate == "story_signoff":             # D17: the story IS the payload
        story = run_file(run_id, "00-story/story.md")
        if story:
            bits.append(artbox("The story being approved — 00-story/story.md",
                               f"<div class='prose'>{render_markdown(story)}</div>"))
            sj = run_json(run_id, "00-story/story.json")
            if isinstance(sj, dict):
                n = len(sj.get("acceptance_criteria") or [])
                q = sj.get("open_questions") or []
                bits.append(f"<div class='gmeta'><b>{n}</b> acceptance criteria · "
                            f"<b>{len(sj.get('non_goals') or [])}</b> non-goals · "
                            + (f"<span style='color:var(--warning)'>{len(q)} open question(s)</span>" if q else "no open questions")
                            + "</div>")
    h = payload.get("handoff") or {}
    if h:                                        # ux_signoff: the rich handoff
        cards = []
        for o in h.get("options", []):
            rec = o.get("name") == h.get("recommended")
            # Presence AND validity, applied to the artifact under decision: a PNG the
            # handoff names but the run folder no longer holds is said out loud, not
            # served as a broken image the approver has to interpret.
            imgs = "".join(
                (f"<a href='/file/{H(png)}' target='_blank'><img src='/file/{H(png)}' "
                 f"alt='{H(o.get('name', '?'))}' loading='lazy'></a>")
                if png_exists(png) else
                (f"<div class='missingpng'>{H(Path(str(png)).name)} — named by the handoff, "
                 f"not in the run folder</div>")
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
    if gate == "plan_signoff":
        plan = run_json(run_id, "02-pre-coding/plan.json")
        task_plan = run_file(run_id, "02-pre-coding/task-plan.md")
        if isinstance(plan, dict):
            bits.append(plan_summary(plan))
        if task_plan:
            bits.append(artbox("The task plan being approved — 02-pre-coding/task-plan.md",
                               f"<div class='prose'>{render_markdown(task_plan)}</div>"))
        schema = run_file(run_id, "02-pre-coding/schema-plan.md")
        if schema:
            bits.append(f"<details class='report'><summary>schema-plan.md</summary>"
                        f"<div class='prose'>{render_markdown(schema)}</div></details>")
    if payload.get("branch") and payload.get("commits") is not None:
        # code_complete after an AUTO coding stage (D14): the pull request is the
        # payload — link it, list the commits, and keep the coding report inline
        # so the reviewer sees the deviations and the confidence map next to it.
        commits = payload.get("commits") or []
        n = payload.get("commit_count", len(commits))
        rows = "".join(
            f"<li><code>{H(str(c.get('sha', ''))[:8])}</code> {H(c.get('subject', ''))}</li>"
            for c in commits[:12])
        more = f"<li>… {n - 12} more</li>" if n > 12 else ""
        pr = payload.get("pr_url")
        if pr:
            link = (f"<a href='{H(pr)}' target='_blank' style='color:var(--dawn-3)'>"
                    f"open pull request #{H(str(payload.get('pr_number', '')))} ↗</a>")
        elif payload.get("compare_url"):
            link = (f"<a href='{H(payload['compare_url'])}' target='_blank' "
                    f"style='color:var(--dawn-3)'>compare the pushed branch ↗</a>")
        else:
            link = "<span style='color:var(--text-dim)'>no pull request (non-GitHub remote) — review the branch</span>"
        if payload.get("pr_error"):
            bits.append(f"<div class='blockwarn'><b>The branch is pushed but the pull request "
                        f"was not opened.</b> {H(payload['pr_error'])} — fix the cause "
                        f"(usually the bot token's pull-request permission), then run "
                        f"<code>pipeline.py publish {H(run_id)}</code>.</div>")
        bits.append(
            f"<div class='gmeta'>{link} · branch <code>{H(payload['branch'])}</code> → "
            f"<code>{H(payload.get('base', ''))}</code> · <b>{n}</b> commit{'s' if n != 1 else ''}"
            f"{' · <b>auto-committed leftovers</b>' if payload.get('auto_committed') else ''}</div>"
            f"<ul class='commits'>{rows}{more}</ul>")
    if gate == "code_complete":
        gate_json = run_json(run_id, "03-coding/gate.json")
        gate_md = run_file(run_id, "03-coding/gate.md")
        if isinstance(gate_json, dict):
            ok = bool(gate_json.get("passed"))
            failed = [r.get("name") for r in gate_json.get("results", []) if isinstance(r, dict) and not r.get("passed")]
            head = (f"<div class='abh'><b>03-coding/gate.md</b>{chip('GREEN' if ok else 'RED', 'ok' if ok else 'blocked')}"
                    f"<span>quality gate as code · round {H(str(gate_json.get('round', 0)))}"
                    + (f" · failed: {H(', '.join(map(str, failed)))}" if failed else "")
                    + f" · {H(', '.join(map(str, gate_json.get('configured') or [])) or 'no commands configured')}</span></div>")
            body = f"<div class='prose'>{render_markdown(gate_md)}</div>" if gate_md else ""
            bits.append(f"<div class='artbox'>{head}{body}</div>")
        rr = review_rounds(run_id, payload)
        if rr:
            bits.append(rr)
        bb = builders_block(run_id, payload)
        if bb:
            bits.append(bb)
        if text:
            bits.append(f"<details class='report' open><summary>The coding report — "
                        f"{H(dir_)}/report.md</summary>"
                        f"<div class='prose'>{render_markdown(text)}</div></details>")
            shown_report = True
    if gate == "staging_deploy":
        val = run_json(run_id, "05-post-coding/validation.json")
        if isinstance(val, dict):
            bits.append(validation_table(val))
        else:
            bits.append("<p class='gdesc'>No 05-post-coding/validation.json — the validator's "
                        "verdict per criterion is missing for this run (runs imported after "
                        "stage 5, or pre-D17).</p>")
        if text:
            bits.append(artbox("The security report — 06-security/report.md",
                               f"<div class='prose'>{render_markdown(text)}</div>"))
            shown_report = True
    if gate == "prod_signoff":
        media = media_links(run_id, "07-qa-staging")
        bugs = run_file(run_id, "07-qa-staging/bugs.md")
        if media:
            bits.append(f"<div class='gmeta'><b>staging videos</b></div>{media}")
        if text:
            bits.append(artbox("The staging QA report — 07-qa-staging/report.md",
                               f"<div class='prose'>{render_markdown(text)}</div>"))
            shown_report = True
        if bugs:
            bits.append(f"<details class='report'><summary>bugs.md</summary>"
                        f"<div class='prose'>{render_markdown(bugs)}</div></details>")
    if not shown_report and text and inline:
        opened = " open" if gate not in ("story_signoff", "plan_signoff", "ux_signoff") else ""
        bits.append(f"<details class='report'{opened}><summary>The stage report — "
                    f"{H(dir_)}/report.md</summary>"
                    f"<div class='prose'>{render_markdown(text)}</div></details>")
    elif not bits and inline:
        bits.append("<p class='gdesc'>No report found for this stage — the run "
                    "folder has nothing to show. Decide from the run page evidence.</p>")
    return bits


def gate_card(a, run, now, inline: bool = True) -> str:
    """One pending approval, its artifact first, its decision form last. Same
    component on /, /gates and /run/{id}. The decision itself stays a server-side
    POST; the keyboard map (a / r) only submits this form."""
    payload = _payload(a)
    gate_title, gate_desc = GATE_META.get(a["gate"], (a["gate"], ""))
    stage = payload.get("stage") or (run["current_stage"] if run else "")
    dir_ = STAGE_DIR.get(stage, stage)
    text = report_text(a["run_id"], dir_) if dir_ else None
    verdict = report_verdict(text)
    openq = report_open_question(text)
    waited = (now - a["requested_at"]).total_seconds()
    age = ago(waited)
    stale = is_stale(waited)

    bits = [f"""<div class='ghead'><div>
        <div class='gid'><a href='/run/{H(a["run_id"])}' data-open>{H(a["run_id"])}</a>
          <span>· after {H(dir_ or "?")}</span>{chip("STALE", "warn") if stale else ""}
          {chip("report: blocked", "blocked") if verdict == "BLOCKED" else ""}</div>
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

    bits.extend(gate_artifacts(a, run, payload, dir_, text, inline))

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
    blocked = "1" if verdict == "BLOCKED" else "0"
    confirm = ("return (event.submitter&&event.submitter.hasAttribute('formaction'))"
               "?confirm('Reject and stop this run for rework?')"
               + (":confirm('The report says BLOCKED — approve anyway?')" if verdict == "BLOCKED" else ":true"))
    bits.append(f"""<div class='gact'>
      <form method='post' action='/gate/{a["id"]}/approve' data-decide data-gate='{H(a["gate"])}'
            data-run='{H(a["run_id"])}' data-blocked='{blocked}' data-approve='/gate/{a["id"]}/approve'
            data-reject='/gate/{a["id"]}/reject' onsubmit="{confirm}">
        <input type='text' name='note' placeholder='decision note — recorded in the audit log'>
        <button class='btn primary'>Approve{H(nxt)}</button>
        <button class='btn danger' formaction='/gate/{a["id"]}/reject'>Reject — stop for rework</button>
        <span class='nxt'>keyboard: <kbd>a</kbd> approve · <kbd>r</kbd> reject with a note · <kbd>Enter</kbd> open the run</span>
      </form>
    </div>""")
    return (f"<div class='gcard{' stale' if stale else ''}' data-k tabindex='0' "
            f"id='gate-{a['id']}'>{''.join(bits)}</div>")


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
      <p>The control room for the software factory. Sign in to see runs and decide gates.</p>
      {warn}{err}
      <form method='post' action='/login'>
        <input name='username' type='text' placeholder='username' autocomplete='username' autofocus>
        <input name='password' type='password' placeholder='password' autocomplete='current-password'>
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


def work_rows(snap, now):
    return worklist.items(snap, now, stage_dir=STAGE_DIR, stage_meta=STAGE_META,
                          gate_meta=GATE_META, short_name=run_short,
                          blocked=workstation_blocked,
                          report_verdict=lambda rid, stage: report_verdict(report_text(rid, stage)))


@app.get("/", response_class=HTMLResponse)
async def board(request: Request, filter: str = "active", q: str = ""):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    snap = await snapshot(await get_pool())
    now = datetime.now(timezone.utc)
    return page("Work — Lantern", worklist.render(work_rows(snap, now), now,
                selected=filter, query=q), user, "/", now, kind="home")


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

    body = ["<header class='work-heading'><div><span class='eyebrow'>Your decisions</span>"
            "<h1>Reviews</h1><p>Open a review to see the evidence and decide.</p></div></header>"]
    if pend:
        for a in pend:
            run = runs.get(a["run_id"])
            label = GATE_META.get(a["gate"], (a["gate"],))[0]
            age = ago((now - a["requested_at"]).total_seconds())
            body.append(f"<details class='review-item'><summary data-k>"
                        f"<span><strong>{H(run_short(a['run_id']).replace('-', ' ').capitalize())}</strong>"
                        f"<span>{H(label)}</span></span><span class='review-age'>waiting {H(age)}</span>"
                        f"</summary>{gate_card(a, run, now)}</details>")
    else:
        body.append("<div class='work-empty'><h2>You're all caught up</h2>"
                    "<p>Nothing is waiting on your review.</p><a class='btn' href='/'>Back to work</a></div>")

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
        body.append(f"<details class='disclosure'><summary>Recent decisions</summary><section class='feed decided'><div class='th'>"
                    f"<span class='caps'>Decided · most recent</span>"
                    f"<span class='caps'>{len(history)} shown</span></div>{''.join(rows)}</section></details>")

    try:
        latency = gate_latency_metrics(gate_latency_rows(await p.fetch(LATENCY_SQL)))
    except asyncpg.PostgresError:
        latency = None
    body.append("<details class='disclosure'><summary>Review timing</summary>"
                + ui.gate_ledger(latency) + "</details>")

    return page("Gates — Lantern Mission Control",
                f"<main class='page'>{''.join(body)}</main>", user, "/gates", now, kind="gates")


@app.get("/runs", response_class=HTMLResponse)
async def runs_index(request: Request, filter: str = "all", q: str = ""):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    snap = await snapshot(await get_pool())
    now = datetime.now(timezone.utc)
    return page("All work — Lantern", worklist.render(work_rows(snap, now), now,
                selected=filter, query=q, path="/runs"), user, "/", now, kind="runs")


# ── cost ─────────────────────────────────────────────────────────────────────

COST_COLS = """model, coalesce(sum(input_tokens),0)::bigint AS inp,
              coalesce(sum(cached_input_tokens),0)::bigint AS cached,
              coalesce(sum(output_tokens),0)::bigint AS outp, count(*)::int AS n,
              count(*) FILTER (WHERE total_tokens IS NULL)::int AS unmetered"""


@app.get("/spend")
async def spend_redirect():
    return RedirectResponse("/cost", status_code=303)


@app.get("/cost", response_class=HTMLResponse)
async def cost_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    p = await get_pool()
    now = datetime.now(timezone.utc)
    daily = await p.fetch(
        f"""SELECT date_trunc('day', started_at)::date AS day, {COST_COLS}
            FROM stage_executions
            WHERE started_at >= now() - interval '14 days'
            GROUP BY 1, model ORDER BY 1 DESC""")
    per_run = await p.fetch(
        f"""SELECT run_id, {COST_COLS} FROM stage_executions
            GROUP BY run_id, model ORDER BY coalesce(sum(total_tokens),0) DESC""")
    alltime = await p.fetch(f"SELECT {COST_COLS} FROM stage_executions GROUP BY model")
    # Consults burn credits too (D11/D13) — chat_turns sits in the same ledger.
    chat_cols = COST_COLS.replace("total_tokens IS NULL",
                                  "total_tokens IS NULL AND status <> 'running'")
    try:
        chat_daily = await p.fetch(
            f"""SELECT date_trunc('day', t.started_at)::date AS day, s.agent, {chat_cols}
                FROM chat_turns t JOIN chat_sessions s ON s.id = t.session_id
                WHERE t.started_at >= now() - interval '14 days'
                GROUP BY 1, s.agent, model ORDER BY 1 DESC, s.agent""")
        chat_alltime = await p.fetch(f"SELECT {chat_cols} FROM chat_turns GROUP BY model")
    except asyncpg.PostgresError:          # database predates the chat tables
        chat_daily, chat_alltime = [], []
    try:
        alarms = await p.fetch(
            "SELECT type, data, at FROM events WHERE actor = 'usage-check' ORDER BY at DESC LIMIT 20")
    except asyncpg.PostgresError:
        alarms = []

    by_day = costmod.aggregate(daily, "day")
    by_run = costmod.aggregate(per_run, "run_id")
    by_model = costmod.aggregate(alltime, "model")
    stage_total = sum(g["cost"] for g in by_model)
    chat_total = sum(est_cost_usd(r["inp"], r["cached"], r["outp"], r["model"]) for r in chat_alltime)
    total_cost = stage_total + chat_total
    total_unmetered = sum(r["unmetered"] for r in [*alltime, *chat_alltime])
    n_exec = sum(r["n"] for r in alltime)
    today_cost = sum(g["cost"] for g in by_day if g["day"] == now.date()) + sum(
        est_cost_usd(r["inp"], r["cached"], r["outp"], r["model"])
        for r in chat_daily if r["day"] == now.date())
    alarm_rows = [{"type": r["type"], "at": r["at"],
                   "data": (json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]) or {}}
                  for r in alarms]
    trip = costmod.tripwire(today_cost, total_cost, os.environ, alarm_rows)

    body = [f"""<section class='readout' style='grid-template-columns:repeat(4,1fr) auto'>
      <div><div class='caps'>Spent today</div>
        <div class='v{' bad' if trip['over_daily'] else ''}'>{H(fmt_money(today_cost))}<small> / {trip['daily_limit']:.0f}</small></div>
        <div class='d'>{min(trip['today_pct'], 999):.0f}% of the daily tripwire · stages and consults</div></div>
      <div><div class='caps'>Ledger total</div><div class='v'>{H(fmt_money(total_cost))}</div>
        <div class='d'>{H(fmt_money(stage_total))} stages · {H(fmt_money(chat_total))} consults · est.</div></div>
      <div><div class='caps'>Executions</div><div class='v'>{n_exec}</div>
        <div class='d'>metered stage executions, all time</div></div>
      <div><div class='caps'>Unmetered</div>
        <div class='v{' bad' if total_unmetered else ''}'>{total_unmetered}</div>
        <div class='d'>executions with no token counts — real spend is higher</div></div>
      <div class='cta'></div></section>"""]
    body.append("<h2 class='sect'>Tripwires</h2><p class='sub'>The two ceilings "
                "<code>pipeline.py usage-check</code> watches hourly: today's rate, and the draw "
                "on the credit pool. Alarms post once; they never block a run.</p>"
                + costmod.render_tripwires(trip))
    body.append("<h2 class='sect'>By run</h2><p class='sub'>Every run's stage executions, all "
                "time, costliest first. Open a run for the per-execution breakdown in its lanes.</p>"
                + costmod.render_by_run(by_run))
    body.append(f"<h2 class='sect'>By day, last 14</h2><p class='sub'>The bar is the day against "
                f"the ${trip['daily_limit']:.0f} tripwire.</p>" + costmod.render_by_day(by_day, trip["daily_limit"]))
    body.append("<h2 class='sect'>By model, all time</h2><p class='sub'>The fleet routes across "
                "price classes (D16); per-deployment rates come from LANTERN_PRICE_JSON when set.</p>"
                + costmod.render_by_model(by_model))
    if chat_daily:
        rows = "".join(
            f"<tr><td class='d'>{r['day']:%b %d}</td>"
            f"<td><a href='/chat?agent={H(r['agent'])}'>{H(r['agent'])}</a></td>"
            f"<td>{H(r['model'] or '— unmetered')}</td><td class='r'>{r['n']}</td>"
            + (f"<td class='r'>{fmt_int(r['inp'])}</td><td class='r'>{fmt_int(r['outp'])}</td>"
               f"<td class='r'>{H(fmt_money(est_cost_usd(r['inp'], r['cached'], r['outp'], r['model'])))}</td>"
               if r["model"] or r["inp"] else
               "<td class='r'>—</td><td class='r'>—</td><td class='r'>—</td>")
            + "</tr>"
            for r in chat_daily)
        body.append(f"""<h2 class='sect'>Chat &amp; consults, last 14 days</h2>
          <p class='sub'>Every web consult turn, by agent — same ledger, same rates
          (docs/CHAT.md). CLI consults land in the events log, not here.</p>
          <div class='stripwrap'><table class='spendtbl'>
          <tr><th>Day</th><th>Agent</th><th>Model</th><th class='r'>Turns</th>
          <th class='r'>Input</th><th class='r'>Output</th><th class='r'>Est. $</th></tr>
          {rows}</table></div>""")

    p_in = os.environ.get("LANTERN_PRICE_IN_PER_M", "4")
    p_c = os.environ.get("LANTERN_PRICE_CACHED_IN_PER_M", "1")
    p_out = os.environ.get("LANTERN_PRICE_OUT_PER_M", "20")
    body.append(f"<p class='footnote'>Token counts are exact; dollars are estimates at "
                f"${H(p_in)} / ${H(p_c)} cached / ${H(p_out)} per 1M tokens until Azure "
                f"invoice lines confirm the rates (pipeline.py, P0.4). Executions that "
                f"crashed before reporting usage have no token counts and are flagged "
                f"unmetered — real spend is higher than shown.</p>")

    return page("Cost — Lantern Mission Control",
                f"<main class='page'>{''.join(body)}</main>", user, "/cost", now, kind="cost")


# ── the run page: swim lanes ─────────────────────────────────────────────────

def run_header(run, run_id: str, now: datetime, totals: dict, active: str) -> str:
    status_chip = {"running": ("Queued", ""), "executing": ("Running", "ok"),
                   "waiting_gate": ("Waiting on a human", "gate"),
                   "failed": ("Failed", "blocked"), "done": ("Completed", "ok"),
                   "cancelled": ("Cancelled", "")}.get(run["status"], (run["status"], ""))
    curdir = lifecycle.directory(run["current_stage"])
    verdict = report_verdict(report_text(run_id, curdir)) \
        if run["status"] not in ("done", "cancelled") else None
    v_chip = chip("report: blocked", "blocked") if verdict == "BLOCKED" else ""
    mode = chip("auto coding", "tier") if (dict(run).get("coding_mode") == "auto") else ""
    # D15: the target is editable from here. When it is unset the warn chip IS the
    # link — that turns "stage 2+ blocks" from a dead end into the fix for it.
    if dict(run).get("product_repo"):
        landed = work_branch(run_id, dict(run).get("product_working_branch") or "")
        derived = not (dict(run).get("product_working_branch") or "")
        repo_bit = (
            f"<code>{H(run['product_repo'])}</code> · base "
            f"<code>{H(run['product_branch'] or 'default')}</code> · branch "
            f"<code>{H(landed)}</code>{' (derived)' if derived else ''} "
            f"<a href='/run/{H(run_id)}/repo' class='lnk'>change</a>")
    else:
        repo_bit = (f"<a href='/run/{H(run_id)}/repo'>"
                    + chip("no product repo set — stage 2+ blocks · connect one", "warn")
                    + "</a>")
    tot, inp, cached = totals.get("tot", 0), totals.get("inp", 0), totals.get("cached", 0)
    tok_line = (f"{fmt_int(tot)} tok · {round(cached / inp * 100) if inp else 0}% cached"
                if tot else "no ledger")
    unm = totals.get("unmetered", 0)
    unm_line = f"<br>{unm} unmetered execution{'s' if unm != 1 else ''}" if unm else ""
    secs = totals.get("seconds")
    sec_line = f"<br>{ui.dur(secs)} of agent time" if secs else ""
    tabs = [("Overview", f"/run/{run_id}", ""), ("Traceability", f"/run/{run_id}/trace", " data-key-t"),
            ("Codebase", f"/run/{run_id}/repo", ""),
            ("Ask Lantern", f"/chat?agent=lantern&run={run_id}", "")]
    nav = "".join(f"<a href='{H(href)}'{extra}{' class=on' if href == active else ''}>{H(n)}</a>"
                  for n, href, extra in tabs)
    return f"""<div class='runhead'><div>
        <a class='back-link' href='/'>← All work</a>
        <h1>{H(run_short(run_id).replace('-', ' ').capitalize())}</h1>
        <div class='run-status'>{chip(*status_chip)}{v_chip}<span>{H(STAGE_META.get(curdir, (curdir,))[0])}</span></div>
        <div class='run-codebase'>{repo_bit}</div>
        <details class='run-meta'><summary>Run details</summary><div class='meta'>
          <code>{H(run_id)}</code> · pipeline v{H(str(run['pipeline_version']))} {mode}<br>
          brief <code>{H(run['brief'])}</code><br>
          Started by <b>{H(run['created_by'])}</b> · {run['created_at']:%b %d %H:%M} UTC<br>
          Est. spend {H(fmt_money(totals.get('cost', 0.0)) if tot else '—')} · {H(tok_line)}{unm_line}{sec_line}
        </div></details>
        <nav class='runnav' aria-label='Run views'>{nav}</nav></div></div>"""



def _trace_keys(run_id: str, execs) -> set[str]:
    """Execution keys that have a trace file on disk (a stat per execution)."""
    out = set()
    for e in execs:
        key = e["idempotency_key"] if "idempotency_key" in dict(e) and e["idempotency_key"] else None
        if not key:
            continue
        sdir = STAGE_DIR.get(e["stage"], e["stage"].split(".", 1)[0])
        if drawer.load_trace(run_root(run_id) / sdir, key) is not None:
            out.add(key)
    return out


@app.get("/run/{run_id}", response_class=HTMLResponse)
async def run_page(run_id: str, request: Request, stage: str = ""):
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
    approvals = await p.fetch(
        "SELECT * FROM approvals WHERE run_id = $1 ORDER BY requested_at", run_id)
    if not approvals and pend:
        approvals = pend

    model = lanes.build_lanes(run, execs, approvals, now, traces=_trace_keys(run_id, execs))
    tot = sum(e["total_tokens"] or 0 for e in execs)
    inp = sum(e["input_tokens"] or 0 for e in execs)
    cached = sum(e["cached_input_tokens"] or 0 for e in execs)
    totals = {"cost": model["cost"], "tot": tot, "inp": inp, "cached": cached,
              "unmetered": model["unmetered"], "seconds": model["seconds"]}
    body = [run_header(run, run_id, now, totals, f"/run/{run_id}")]

    cycle = lifecycle.build(run, execs, approvals, events)
    body.append(lifecycle.render(cycle, now, selected=stage))

    for a in pend:
        body.append(gate_card(a, run, now))

    if not pend:
        status = run["status"]
        latest = execs[-1] if execs else None
        if status == "failed":
            message = H((latest["error"] if latest else None) or "This run stopped. Open its latest execution to investigate.")
            body.append(f"<div class='notice'><b>This run needs attention.</b> {message}</div>")
        elif status == "waiting_gate":
            body.append("<div class='notice'><b>Review unavailable.</b> This run is waiting for a decision, but its approval record is missing.</div>")
        elif status in ("done", "cancelled"):
            body.append(f"<p class='sub'>This run is {H(status)}. Its evidence and history are below.</p>")

    body.append(f"<details class='disclosure' id='execution-history'><summary>Execution details <span>{model['executions']} executions</span></summary>"
                + lanes.render_lanes(model, run_id, GATE_SHORT, GATE_META, STAGE_META) + "</details>")

    # Traceability, one line: the counts and a link to the matrix.
    m = traceability.build_matrix(run_id, run_root(run_id))
    if m["present"]["story"]:
        c = m["counts"]
        body.append(f"<h2 class='sect'>Traceability</h2><p class='sub'>{len(m['rows'])} acceptance "
                    f"criteria — <b>{c['complete']}</b> complete · <b>{c['gap']}</b> gaps · "
                    f"<b>{c['deferred']}</b> deferred · <b>{c['pending']}</b> pending. "
                    f"<a href='/run/{H(run_id)}/trace' data-key-t style='color:var(--dawn-3);text-decoration:underline'>"
                    f"open the matrix →</a></p>")

    # Stage folders: the run-folder view (reports, artifacts, consults) per stage dir.
    by_dir: dict[str, list] = {}
    for e in execs:
        by_dir.setdefault(lifecycle.directory(e["stage"]), []).append(e)
    curdir = lifecycle.directory(run["current_stage"])
    body.append("<details class='disclosure'><summary>Reports &amp; files</summary>")
    for d in dict.fromkeys([*BOARD_DIRS, *by_dir, curdir]):
        if d not in by_dir and d != curdir:
            continue
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
            secs = sum(((t["finished_at"] or now) - t["started_at"]).total_seconds() for t in tries)
            right = f"{ui.dur(secs)} · {len(tries)} execution{'s' if len(tries) != 1 else ''}"
            right += (f"<br>{fmt_int(d_tot)} tok · {H(fmt_money(d_cost))}" if d_tot
                      else "<br>unmetered")
        head = (f"<div class='shead'><span class='nm'>{H(name)}</span>"
                f"<span class='actor'>{'🤖 agent' if actor == 'agent' else '👤 human'}"
                f" · {H(DIR_RUNNER.get(d, 'ec2'))}</span>"
                f"{chip(*st)}{chip('current', 'gate') if cur else ''}"
                f"<span class='right'>{right}</span></div>")
        bits = [head, f"<div class='sdesc'>{H(desc)}</div>"]
        if latest and latest["error"]:
            bits.append(f"<div class='err'>{H(latest['error'][:600])}</div>")
        text = report_text(run_id, d)
        if text:
            v = report_verdict(text)
            v_note = f" — report status: {v}" if v else ""
            bits.append(f"<details class='report'><summary>report.md{H(v_note)}</summary>"
                        f"<div class='prose'>{render_markdown(text)}</div></details>")
        stage_arts = [a for a in arts if a["stage"] == d]
        links = "".join(
            f"<a href='{H(art_href(a['uri']))}' target='_blank'>"
            f"{KIND_ICON.get(a['kind'], '')}{H(a['kind'])}</a>"
            for a in stage_arts)
        if links:
            bits.append(f"<div class='arts'>{links}</div>")
        bits.append(media_links(run_id, d))
        role = DIR_ROLE.get(d)
        if role and tries:      # a stage that ran can be asked about (consult mode, D11)
            bits.append(f"<div class='arts'><a href='/chat?agent={H(role)}&amp;run={H(run_id)}'>"
                        f"💬 consult {H(role)} about this run</a></div>")
        body.append(f"<div class='{cls}' id='files-{H(d)}'>{''.join(bits)}</div>")

    body.append("</details>")

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
        body.append(f"<details class='disclosure'><summary>Audit log <span>{len(events)} events</span></summary>"
                    f"<div>{''.join(rows)}</div></details>")

    return page(f"{run_id} — Lantern Mission Control",
                f"<main class='page'>{''.join(body)}</main>", user, "/runs", now, kind="run")


@app.get("/run/{run_id}/exec/{exec_id}", response_class=HTMLResponse)
async def exec_drawer(run_id: str, exec_id: int, request: Request, fragment: str = ""):
    """The execution drawer — a fragment for the run page's aside, or a full page."""
    user = current_user(request)
    if not user:
        if fragment:
            raise HTTPException(401, "sign in required")
        return RedirectResponse("/login", status_code=303)
    p = await get_pool()
    now = datetime.now(timezone.utc)
    run = await p.fetchrow("SELECT * FROM runs WHERE id = $1", run_id)
    if not run:
        raise HTTPException(404, "run not found")
    e = await p.fetchrow(
        "SELECT * FROM stage_executions WHERE id = $1 AND run_id = $2", exec_id, run_id)
    if not e:
        raise HTTPException(404, "execution not found")
    key = e["idempotency_key"] or f"{run_id}:{e['stage']}:{e['attempt']}"
    try:
        memory = await p.fetch(
            "SELECT entry, created_at FROM role_memory WHERE execution_key = $1 ORDER BY id", key)
    except asyncpg.PostgresError:
        memory = []
    m = drawer.load_execution(run, e, run_root(run_id), memory, now)
    html_frag = drawer.render_drawer(m, render_markdown, STAGE_META, fragment=bool(fragment))
    if fragment:
        return HTMLResponse(html_frag)
    return page(f"{run_id} · {e['stage']} #{e['attempt']} — Lantern Mission Control",
                f"<main class='page'><div style='max-width:900px'>{html_frag}</div></main>",
                user, "/runs", now, kind="exec", auto_reload=False)


@app.get("/run/{run_id}/trace", response_class=HTMLResponse)
async def trace_matrix(run_id: str, request: Request):
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
    tot = sum(e["total_tokens"] or 0 for e in execs)
    totals = {"cost": sum(lanes.exec_cost(e) for e in execs), "tot": tot,
              "inp": sum(e["input_tokens"] or 0 for e in execs),
              "cached": sum(e["cached_input_tokens"] or 0 for e in execs),
              "unmetered": sum(1 for e in execs if e["total_tokens"] is None)}
    m = traceability.build_matrix(run_id, run_root(run_id))
    body = [run_header(run, run_id, now, totals, f"/run/{run_id}/trace"),
            f"<h2 class='sect'>Traceability{(' — ' + H(m['story_title'])) if m['story_title'] else ''}</h2>"
            "<p class='sub'>The contract at a glance: every acceptance criterion across the plan's "
            "tasks, the coding commits, the QA charter and the validator's verdict. Rows are the "
            "story; columns are what each stage did with it.</p>",
            traceability.render_matrix(m)]
    return page(f"{run_id} · traceability — Lantern Mission Control",
                f"<main class='page'>{''.join(body)}</main>", user, "/runs", now, kind="trace")


# ── the factory catalog ──────────────────────────────────────────────────────

@app.get("/factory", response_class=HTMLResponse)
async def factory_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    p = await get_pool()
    now = datetime.now(timezone.utc)
    try:
        repos = [r["product_repo"] for r in await p.fetch(
            "SELECT DISTINCT product_repo FROM runs WHERE product_repo IS NOT NULL ORDER BY 1")]
    except asyncpg.PostgresError:
        repos = []
    runs_dir = REPO / "workflow" / "runs"
    plans = [(d.name, d / "02-pre-coding" / "plan.json")
             for d in (sorted(runs_dir.iterdir()) if runs_dir.is_dir() else [])
             if (d / "02-pre-coding" / "plan.json").is_file()]
    c = await asyncio.to_thread(catalog.build_catalog, REPO, dict(os.environ), repos,
                                STAGE_META, GATE_META, plans)
    body = ("<div class='runhead' style='padding-bottom:12px'><div><div class='caps'>Factory</div>"
            "<h1 style='font-family:var(--font-ui);font-weight:600'>What this factory is made of</h1>"
            "<div class='meta'>Read-only, from files and the environment of the host serving this "
            "page: roles, the fixed pipeline and its gates, the model stack, every product's "
            "quality gate, the evals, and the builders a plan declares.</div></div></div>"
            + catalog.render_catalog(c, render_markdown))
    return page("Factory — Lantern Mission Control", f"<main class='page'>{body}</main>",
                user, "/factory", now, kind="factory")


# ── the loop primitives (D17), server-side ───────────────────────────────────
# Retry re-queues a FAILED run at its current stage; rework sends a failed or waiting
# run back to an earlier stage through pipeline.cmd_rework. Both record the web
# user as the actor. Approvals are never touched here — that is the gate route.

@app.post("/run/{run_id}/retry")
async def retry_run(run_id: str, request: Request):
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "sign in required")     # fail closed, like gates
    p = await get_pool()
    async with p.acquire() as conn:
        run = await conn.fetchrow("SELECT status, current_stage FROM runs WHERE id = $1", run_id)
        if not run:
            raise HTTPException(404, "run not found")
        if run["status"] != "failed":
            raise HTTPException(409, f"run is {run['status']} — retry applies to failed runs")
        await conn.execute(
            "UPDATE runs SET status = 'running', updated_at = now() WHERE id = $1", run_id)
        await log_event(conn, run_id, f"human:{user}", "run_retried",
                        {"stage": run["current_stage"], "channel": "web"})
        await render_runboard(conn)
    return RedirectResponse(f"/run/{run_id}", status_code=303)


@app.post("/run/{run_id}/rework")
async def rework_run(run_id: str, request: Request, to_stage: str = Form(""), note: str = Form("")):
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "sign in required")
    if to_stage not in REWORK_TARGETS:
        raise HTTPException(400, f"rework target must be one of {', '.join(REWORK_TARGETS)}")
    try:
        await cmd_rework(run_id, to_stage, user, note.strip())
    except SystemExit as e:                  # cmd_rework refuses with sys.exit(<reason>)
        raise HTTPException(409, str(e) or "rework refused") from None
    return RedirectResponse(f"/run/{run_id}", status_code=303)


# ── the codebase connection (D15) ────────────────────────────────────────────
# The only place besides the gate route that writes. Repo selection is confined to
# workspace.contains(): whatever path is admitted here gets cloned by this host,
# mounted into sandboxes, read by agents and pasted into system prompts, so an
# unconfined picker would be a filesystem-read primitive behind a login form.

def _repo_picker_body(run, run_id: str, repos: list[dict], sel: str,
                      heads: list[str] | None, error: str) -> str:
    cur_repo = run.get("product_repo") or ""
    cur_base = run.get("product_branch") or ""
    cur_work = run.get("product_working_branch") or ""
    landed = work_branch(run_id, cur_work)
    roots = workspace.roots_label()

    out = [f"<div class='caps'>Codebase</div><h2 class='sect'>Connect "
           f"<code>{H(run_id)}</code> to a repository</h2>",
           "<p class='sub'>Pick the repo and the base branch this run works against, and "
           "optionally an existing branch to continue on. Every stage after this reads "
           "that code and orients on that branch.</p>"]

    if cur_repo:
        out.append(
            f"<div class='pick'><h3>Currently connected</h3>"
            f"<p class='hint'><code>{H(cur_repo)}</code><br>base <code>{H(cur_base)}</code>"
            f" · work lands on <code>{H(landed)}</code>"
            f"{' (derived from the run id)' if not cur_work else ''}</p></div>")
    if error:
        out.append(f"<div class='pick'><div class='errbox'>{H(error)}</div></div>")

    # ── on this host ──
    rows = []
    for r in repos:
        checked = " checked" if r["path"] == sel else ""
        rows.append(
            f"<label><input type='radio' name='local_path' value='{H(r['path'])}'{checked}>"
            f"<span class='nm'>{H(r['name'])}</span>"
            f"<span class='br'>{H(r['head_branch'] or '—')}</span>"
            f"<span class='pt'>{H(r['path'])}</span></label>")
    host_block = [f"<div class='pick'><h3>On this host</h3>"]
    if repos:
        host_block.append(
            f"<p class='hint'>Scanned <code>{H(roots)}</code> — these are real "
            f"directories on the machine serving this page. A local repo is read from "
            f"disk with no network and no token; the pipeline sees its "
            f"<b>committed</b> state only, so uncommitted work in your checkout is "
            f"invisible to agents.</p>"
            f"<div class='repolist'>{''.join(rows)}</div>")
    else:
        host_block.append(
            "<div class='warnbox'>No repositories offered. The picker only looks inside "
            f"<code>LANTERN_WORKSPACE_ROOTS</code> — currently <code>{H(roots)}</code>. "
            "That is a security boundary, not a convenience: unset means nothing is "
            "offered rather than everything. Set it (os.pathsep-separated) on the host "
            "running Mission Control, or use a remote URL below.</div>")
    host_block.append("</div>")
    out.append("".join(host_block))

    out.append(
        f"<div class='pick'><h3>Or a remote repository</h3>"
        f"<p class='hint'>An https clone URL. The host fetches it with its own token "
        f"into a bare mirror; the token never enters a sandbox.</p>"
        f"<div class='row'><div class='fld' style='flex:1;min-width:320px'>"
        f"<span class='lb'>Clone URL</span>"
        f"<input type='text' name='remote_url' style='width:100%' "
        f"placeholder='https://github.com/org/repo' "
        f"value='{H(sel if sel and not any(r['path'] == sel for r in repos) else '')}'>"
        f"</div></div></div>")

    # ── branches (only once a repo has been inspected) ──
    if heads is not None:
        sel_base = (cur_base if cur_base in heads else
                    ("main" if "main" in heads else
                     ("master" if "master" in heads else (heads[0] if heads else ""))))
        base_opts = "".join(
            f"<option value='{H(b)}'{' selected' if b == sel_base else ''}>{H(b)}</option>"
            for b in heads)
        ns = [b for b in heads if b.startswith(CODING_BRANCH_PREFIXES)]
        derived = work_branch(run_id, "")
        work_opts = [f"<option value=''>— new branch for this run ({H(derived)}) —</option>"]
        work_opts += [
            f"<option value='{H(b)}'{' selected' if b == cur_work else ''}>{H(b)}</option>"
            for b in ns]
        note = ""
        if not ns:
            note = ("<p class='hint'>No existing branch is inside the namespace agents "
                    f"may push to ({H(', '.join(p + '*' for p in CODING_BRANCH_PREFIXES))}) "
                    "— D6. This run will get a fresh one.</p>")
        out.append(
            f"<div class='pick'><h3>Branches</h3>"
            f"<p class='hint'>The <b>base</b> is what the work branches from and what the "
            f"pull request targets. The <b>working branch</b> is where commits land — "
            f"leave it derived unless you are continuing work that already exists.</p>"
            f"{note}"
            f"<div class='row'>"
            f"<div class='fld'><span class='lb'>Base branch</span>"
            f"<select name='base_branch'>{base_opts}</select></div>"
            f"<div class='fld'><span class='lb'>Working branch</span>"
            f"<select name='working_branch'>{''.join(work_opts)}</select></div>"
            f"<button class='btn primary' name='action' value='save'>Connect this run</button>"
            f"</div></div>")
    else:
        out.append("<div class='pick'><div class='row'>"
                   "<button class='btn primary' name='action' value='inspect'>"
                   "Load branches</button>"
                   "<span class='hint' style='margin:0'>Pick a repo first — its branches "
                   "are read from the host mirror, which is synced now.</span>"
                   "</div></div>")

    return (f"<form method='post' action='/run/{H(run_id)}/repo'>{''.join(out)}"
            f"<p class='sub'><a href='/run/{H(run_id)}'>← back to the run</a></p></form>")


@app.get("/run/{run_id}/repo", response_class=HTMLResponse)
async def repo_picker(run_id: str, request: Request, repo: str = "", error: str = ""):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    p = await get_pool()
    now = datetime.now(timezone.utc)
    run = await p.fetchrow("SELECT * FROM runs WHERE id = $1", run_id)
    if not run:
        raise HTTPException(404, "run not found")
    repos = await asyncio.to_thread(workspace.discover_repos)
    sel = repo or (run.get("product_repo") or "")
    heads = None
    if sel:
        # Rendering only needs the branch list — verification belongs to the POST,
        # where a refusal has somewhere to go. Going through verify_product_target
        # here would sync the mirror twice and refuse outright for a repo whose
        # recorded base branch has since been renamed away.
        try:
            heads = await asyncio.to_thread(_branch_names, sel)
        except (RuntimeError, OSError) as e:
            error = error or f"could not read {sel}: {str(e)[:300]}"
    body = _repo_picker_body(dict(run), run_id, repos, sel, heads, error)
    return page(f"Codebase — {run_id}", f"<main class='page'>{body}</main>",
                user, "/runs", now, kind="repo")


def _branch_names(repo: str) -> list[str]:
    """The repo's branch heads, via the host mirror pipeline.py already maintains."""
    from pipeline import _branch_heads, sync_product_mirror
    return _branch_heads(sync_product_mirror(repo))


@app.post("/run/{run_id}/repo")
async def set_repo(run_id: str, request: Request, action: str = Form("inspect"),
                   local_path: str = Form(""), remote_url: str = Form(""),
                   base_branch: str = Form(""), working_branch: str = Form("")):
    user = current_user(request)
    if user is None:
        raise HTTPException(401, "sign in required")    # fail closed, like gates
    p = await get_pool()
    run = await p.fetchrow("SELECT * FROM runs WHERE id = $1", run_id)
    if not run:
        raise HTTPException(404, "run not found")
    if run["status"] in ("done", "cancelled"):
        raise HTTPException(409, f"run is {run['status']} — its codebase is history now")

    local_path, remote_url = local_path.strip(), remote_url.strip()
    if local_path and remote_url:
        raise HTTPException(400, "choose a repo on this host OR a remote URL, not both")
    if local_path:
        admitted = workspace.contains(local_path)
        if admitted is None:
            # Name the boundary: a 404-style silence would leave the user guessing
            # whether the path is wrong or the picker is broken.
            raise HTTPException(400, (
                f"'{local_path}' is not an available repository. The picker only admits "
                f"git repos inside LANTERN_WORKSPACE_ROOTS ({workspace.roots_label()})."))
        repo = str(admitted)
    elif remote_url:
        if not remote_url.startswith(("https://", "http://", "git@", "ssh://")):
            raise HTTPException(400, "a remote target must be a clone URL")
        repo = remote_url
    else:
        raise HTTPException(400, "pick a repository first")

    # Repointing a run at a DIFFERENT repo mid-flight invalidates every upstream
    # report — the blast radius, the task plan and the QA charter all name paths in
    # the old tree. Refuse loudly rather than corrupt the run's history.
    stage_i = STAGE_SEQ.index(run["current_stage"]) if run["current_stage"] in STAGE_SEQ else 0
    if (run["product_repo"] and run["product_repo"] != repo
            and stage_i > STAGE_SEQ.index("03-coding")):
        raise HTTPException(409, (
            "this run is past coding — pointing it at a different repository would "
            "invalidate every report already written against the old one. Start a new "
            "run instead."))

    def _back(err: str = "") -> RedirectResponse:
        q = f"?repo={quote(repo)}" + (f"&error={quote(err)}" if err else "")
        return RedirectResponse(f"/run/{run_id}/repo{q}", status_code=303)

    try:
        info = await asyncio.to_thread(
            verify_product_target, repo, base_branch or run["product_branch"] or "main",
            working_branch)
    except ProductTargetError as e:
        return _back(f"{e} (branches: {', '.join(e.branches) or 'none'})")
    except (RuntimeError, OSError) as e:
        return _back(str(e)[:400])

    if action != "save":
        return _back()

    async with p.acquire() as conn:
        await conn.execute(
            """UPDATE runs SET product_repo = $1, product_branch = $2,
                               product_working_branch = $3, updated_at = now()
               WHERE id = $4""",
            repo, base_branch or run["product_branch"] or "main",
            info["working"] or None, run_id)
        await log_event(conn, run_id, f"human:{user}", "product_target_set",
                        {"repo": repo, "branch": base_branch,
                         "working": info["working"], "head": info["base_sha"][:12],
                         "channel": "web"})
    return RedirectResponse(f"/run/{run_id}", status_code=303)


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
    status = "approved" if decision == "approve" else "rejected"
    p = await get_pool()
    async with p.acquire() as conn:
        a = await conn.fetchrow(
            """UPDATE approvals SET status=$1, decided_at=now(), decided_by=$2, decision_note=$3
               WHERE id = $4 AND status = 'pending' RETURNING run_id, gate""",
            status, user, note, approval_id)
        if not a:
            raise HTTPException(409, "approval no longer pending")
        # The event type matches the CLI's exactly (pipeline.record_gate_decision writes
        # `gate_{status}`): one audit stream, whichever surface decided. Until v3 this
        # route wrote `gate_rejectd` — a typo that split rejections into two names.
        await log_event(conn, a["run_id"], f"human:{user}", f"gate_{status}",
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
