"""Chat service — the engine behind Mission Control's Chat tab (docs/CHAT.md, D13).

Web consult mode: the same advisory, read-only agents as `pipeline.py ask` (D11),
plus an orchestrator agent ("lantern") that reads the pipeline database and can
hand questions to specialists, plus user-created custom agents. Harness-agnostic
on purpose: FastAPI imports it today, the Slack bridge imports it now.

Since D21 the orchestrator also has HANDS: start_run, decide_gate, rework, retry,
set_product — `pipeline.py`'s own commands behind `PipelineExecutor`, never a second
implementation. Three of them act only after the human types a confirmation phrase
that THIS server read in THIS turn's human message (`confirmed()`); the model can
neither self-confirm nor reuse an older turn's confirmation. Everything is recorded
against the signed-in human, so a chat approval is auditably a person's.

What lives where:
  - conversation context (what the model re-reads) — the Agents SDK's own
    agent_sessions/agent_messages via SQLAlchemySession, keyed by the SAME id as
    our chat_sessions row, so CLI and web continue each other's threads;
  - the transcript, activity trace, and token ledger — chat_turns (ours, stable,
    rendered by the UI; the SDK's message shape is not parsed for display);
  - live streaming — an in-process TurnBus (SSE fan-out with replay). Process-
    local by design: Mission Control runs as one uvicorn process. A turn whose
    process died is marked failed («interrupted») on next contact, never left
    pretending to run.
"""

import asyncio
import contextlib
import io
import json
import os
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
from agents import (Agent, Runner, function_tool, set_default_openai_api,
                    set_default_openai_client, set_tracing_disabled)
from agents.extensions.memory import SQLAlchemySession
from sqlalchemy.ext.asyncio import create_async_engine

from orchestrator import (
    BROWSER_ROLES, REPO, azure_v1_client, build_consult_instructions,
    consult_roles, db_urls, deployment_for_tier, list_dir, make_append_memory, model_for,
    model_settings_for, read_file,
    render_role_memory, usage_dict,
)

LANTERN_AGENT = "lantern"          # the orchestrator chat — not a role folder
MAX_TURNS_CONSULT = 40             # parity with pipeline.py ask
MAX_TURNS_LANTERN = 60             # it fans out to specialists
SPECIALIST_MAX_TURNS = 24
ARG_SNIPPET = 240                  # trace truncation: args / outputs stay readable,
OUT_SNIPPET = 400                  # never dominant
INTERRUPTED = "interrupted — mission control restarted mid-turn"
# Set by the web app's shutdown hook. A process going down cancels turn tasks
# exactly like a developer's Stop does; without this flag a restart would be
# recorded as "stopped by the developer" — observed 2026-09-07 under --reload.
SHUTTING_DOWN = False


def chat_configured() -> tuple[bool, str]:
    """Can this process actually run a model turn? (Never crash the board over env.)"""
    missing = [v for v in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY",
                           "LANTERN_MODEL_REASONING")
               if not os.environ.get(v)]
    if missing:
        return False, "model backend not configured — set " + ", ".join(missing)
    return True, ""


_client_ready = False


def ensure_client() -> None:
    """One-time Azure client + Responses API setup (same choices as the orchestrator)."""
    global _client_ready
    if _client_ready:
        return
    set_default_openai_client(azure_v1_client())
    set_default_openai_api(os.environ.get("LANTERN_OPENAI_API", "responses"))
    set_tracing_disabled(True)
    _client_ready = True


async def ensure_chat_tables(conn: asyncpg.Connection) -> None:
    """Bring an existing database up to schema. schema.sql is idempotent end to end
    (CREATE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS), so executing it whole keeps
    one source of truth instead of a drifting copy of the chat DDL here."""
    await conn.execute((Path(__file__).parent / "schema.sql").read_text(encoding="utf-8"))


# ── the agent directory: fleet roles + custom agents + lantern ───────────────

def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:40] or "agent"


async def custom_agent_rows(conn, include_archived: bool = False) -> list[asyncpg.Record]:
    q = "SELECT * FROM custom_agents"
    if not include_archived:
        q += " WHERE NOT archived"
    return await conn.fetch(q + " ORDER BY created_at")


async def agent_directory(conn) -> dict[str, dict]:
    """Every talkable agent, keyed by slug. kind: orchestrator|fleet|custom."""
    out = {LANTERN_AGENT: {
        "kind": "orchestrator", "name": "Lantern", "model_pref": "reasoning",
        "desc": ("The whole pipeline in one chat — what's blocked, what shipped, what "
                 "it cost. Pulls a specialist in when a question needs one."),
    }}
    for role, desc in consult_roles().items():
        out[role] = {"kind": "fleet", "name": role, "desc": desc,
                     "model_pref": "fast" if role in {"qa-dev", "qa-staging"} else "reasoning",
                     "browser_role": role in BROWSER_ROLES}
    for r in await custom_agent_rows(conn):
        out[r["slug"]] = {"kind": "custom", "name": r["name"], "desc": r["purpose"],
                          "model_pref": r["model_pref"], "row": r}
    return out


def compose_instructions(name: str, purpose: str) -> str:
    """Default working instructions when the creator leaves the field empty
    (the Dust-Sidekick move: purpose is enough to start)."""
    return (
        f"You are {name}. {purpose.strip().rstrip('.')}.\n\n"
        "Work the way the Lantern fleet works:\n"
        "- Ground every answer in what you can actually read in this repo "
        "(read_file / list_dir) rather than in assumption; name the files you used.\n"
        "- Say plainly when you do not know or cannot verify something — an honest "
        "gap beats a confident guess.\n"
        "- Size the answer to the question: a sentence when a sentence does it.\n"
        "- When a conversation teaches you something durable about doing this job "
        "well, record it with append_memory."
    )


async def create_custom_agent(conn, name: str, purpose: str, instructions: str,
                              model_pref: str, by: str) -> str:
    slug = slugify(name)
    if slug in consult_roles() or slug == LANTERN_AGENT:
        raise ValueError(f"'{slug}' is a fleet role — pick another name")
    if model_pref not in ("reasoning", "fast"):
        model_pref = "reasoning"
    try:
        await conn.execute(
            """INSERT INTO custom_agents (slug, name, purpose, instructions, model_pref, created_by)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            slug, name.strip(), purpose.strip(), instructions.strip() or None, model_pref, by)
    except asyncpg.UniqueViolationError:
        raise ValueError(f"an agent named '{slug}' already exists")
    return slug


def agent_model(info: dict) -> str:
    if info["kind"] == "fleet":
        return model_for(info["name"])
    return deployment_for_tier("fast" if info.get("model_pref") == "fast" else "reasoning")


def agent_model_settings(info: dict):
    """Reasoning effort for a chat agent: fleet roles route by role; the orchestrator and
    custom agents carry a model_pref, which names a tier."""
    if info["kind"] == "fleet":
        return model_settings_for(info["name"], purpose="chat")
    tier = "fast" if info.get("model_pref") == "fast" else "reasoning"
    return model_settings_for(info.get("name", "custom"), purpose="chat", tier=tier)


# ── sessions ─────────────────────────────────────────────────────────────────

def chat_session_id(by: str, agent: str, name: str) -> str:
    """The shared consult key (D11): `pipeline.py ask` and the web use one format,
    so matching {user}:{agent}:{name} IS the same conversation on both surfaces."""
    return f"consult:{by}:{agent}:{name}"


async def create_session(conn, by: str, agent: str, run_id: str | None = None) -> str:
    for _ in range(3):                       # web session names are random; retry a collision
        sid = chat_session_id(by, agent, f"web-{secrets.token_hex(3)}")
        try:
            await conn.execute(
                "INSERT INTO chat_sessions (id, agent, created_by, run_id) VALUES ($1,$2,$3,$4)",
                sid, agent, by, run_id or None)
            return sid
        except asyncpg.UniqueViolationError:
            continue
    raise RuntimeError("could not allocate a session id")


async def reap_stale_turns(conn, bus: "TurnBus", session_id: str | None = None) -> int:
    """Mark 'running' turns that no live task owns as failed. Honesty over hope:
    after a process restart nothing can finish them, so they must not look alive."""
    q = "SELECT id, session_id FROM chat_turns WHERE status = 'running'"
    args: list = []
    if session_id:
        q += " AND session_id = $1"
        args.append(session_id)
    stale = [r["id"] for r in await conn.fetch(q, *args)
             if (bus.active(r["session_id"]) or {}).get("turn_id") != r["id"]]
    if stale:
        await conn.execute(
            """UPDATE chat_turns SET status='failed', error=$2, finished_at=now()
               WHERE id = ANY($1) AND status='running'""", stale, INTERRUPTED)
    return len(stale)


# ── the live bus: one active turn per session, SSE fan-out with replay ───────

class TurnBus:
    """Subscribers are PER SESSION and outlive turns: a transcript page opens one
    EventSource for its whole life, so a listener attached while the session is
    idle must still receive the next turn. The active turn only adds a replay
    buffer for listeners who arrive mid-turn. (v1 shipped subscribers inside the
    turn entry — an idle-attached page went deaf to every later turn.)"""

    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = {}
        self._turns: dict[str, dict] = {}

    def active(self, session_id: str) -> dict | None:
        return self._turns.get(session_id)

    def start(self, session_id: str, turn_id: int) -> None:
        if session_id in self._turns:
            raise RuntimeError("a turn is already running in this conversation")
        self._turns[session_id] = {"turn_id": turn_id, "task": None, "events": []}

    def attach_task(self, session_id: str, task: asyncio.Task) -> None:
        if session_id in self._turns:
            self._turns[session_id]["task"] = task

    def publish(self, session_id: str, event: dict) -> None:
        t = self._turns.get(session_id)
        if t:
            t["events"].append(event)
        for q in list(self._subs.get(session_id, ())):
            q.put_nowait(event)

    def subscribe(self, session_id: str) -> tuple[list[dict], asyncio.Queue]:
        """(replay of the active turn so far, live queue). None on the queue means
        the server is going away — end the stream, the client reconnects."""
        q: asyncio.Queue = asyncio.Queue()
        self._subs.setdefault(session_id, set()).add(q)
        t = self._turns.get(session_id)
        return (list(t["events"]) if t else []), q

    def unsubscribe(self, session_id: str, q: asyncio.Queue) -> None:
        subs = self._subs.get(session_id)
        if subs:
            subs.discard(q)
            if not subs:
                self._subs.pop(session_id, None)

    def finish(self, session_id: str) -> None:
        self._turns.pop(session_id, None)

    def stop(self, session_id: str) -> bool:
        t = self._turns.get(session_id)
        if t and t["task"] and not t["task"].done():
            t["task"].cancel()
            return True
        return False

    def close_all(self) -> None:
        """Server shutdown: release every SSE loop so a graceful restart is not
        held hostage by open event streams (observed: uvicorn --reload wedged on
        'Waiting for connections to close')."""
        for subs in list(self._subs.values()):
            for q in list(subs):
                q.put_nowait(None)


BUS = TurnBus()


# ── instruction builders ─────────────────────────────────────────────────────

def run_scope_note(run_id: str) -> str:
    return (
        f"\n\n# Run scope\nThis conversation is about run `{run_id}`. Orient there "
        f"before answering: `workflow/runs/{run_id}/` holds the brief and every "
        "stage's report; read the relevant stage dir rather than guessing what "
        "happened. Answers should cite the files they used.")


def build_lantern_instructions(by: str = "the developer", can_write: bool = False) -> str:
    """The orchestrator chat: the system contract + the pipeline database in view,
    and — since D21 — the factory's controls, behind the confirmation protocol."""
    contract = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    return (
        "# Lantern — orchestrator consult\n"
        f"You are **Lantern**, the voice of the agentic delivery pipeline, consulted "
        f"by {by}, a signed-in developer, from Mission Control. You speak first-person, "
        "concrete and calm; you admit uncertainty instead of faking data.\n\n"
        "You are the one chat that sees everything:\n"
        "- `pipeline_snapshot` — the live board: every open run, its stage, what it "
        "waits on, runner health, today's spend. Reach for it FIRST on any "
        "what's-happening question.\n"
        "- `run_detail(run_id)` — one run's stage-by-stage truth: attempts, errors, "
        "token spend, artifacts, recent events.\n"
        "- `spend_summary(days)` — the token ledger, stage work and consults alike.\n"
        "- `read_file` / `list_dir` — this repo: briefs, stage reports, charters, "
        "docs. Run folders live under `workflow/runs/<run-id>/`.\n"
        "- `ask_specialist(role, question)` — hand ONE sharp question to a fleet "
        "role (their charter/skills/memory answer it) when the developer needs "
        "depth you don't have. Quote whose answer it is when you relay it.\n\n"
        "Numbers you report come from the tools, never from memory of them.\n"
        + (WRITE_TOOL_PROTOCOL.replace("{by}", by) if can_write else
           "You are advisory and read-only in this session: no write tools are "
           "attached. When asked to start a run or decide a gate, say exactly what "
           "the human should do instead (`pipeline.py run ...`, the Gates tab, a "
           "brief in workflow/briefs/).\n")
        + "\n# The system you narrate (AGENTS.md, verbatim)\n\n" + contract)


async def build_custom_instructions(conn, row) -> str:
    """Consult-mode wrapper for a user-created agent + its learned memory.
    Memory is embedded from role_memory directly (table-only): custom agents have
    no agents/<slug>/ folder, so nothing renders memory.md for them."""
    mem = await conn.fetch(
        """SELECT entry, created_at FROM role_memory
           WHERE role = $1 AND NOT consolidated ORDER BY created_at DESC LIMIT 30""",
        row["slug"])
    body = row["instructions"] or compose_instructions(row["name"], row["purpose"])
    parts = [
        f"# Consult mode\nYou are **{row['name']}**, a custom agent of the Lantern "
        f"fleet (created by {row['created_by']}), consulted directly by a developer. "
        "Your final message IS the deliverable — answer directly and concretely, "
        "sized to the question.\n\n"
        "- You are advisory and read-only: no file-write tools. Work that changes "
        "the product or a run goes through a pipeline run — say so if asked.\n"
        "- Ground yourself with read_file/list_dir before answering anything you "
        "are not sure of (workflow/RUNBOARD.md holds the live pipeline state).\n"
        "- The developer may follow up; earlier turns of this consult persist.\n\n"
        f"# Your working instructions\n{body}",
    ]
    if mem:
        lines = "\n".join(f"- {r['created_at']:%Y-%m-%d}: {r['entry'].strip()}" for r in mem)
        parts.append(f"\n\n# Your memory (learned in past consults, newest first)\n{lines}")
    return "".join(parts)


# ── database read tools for the orchestrator agent ───────────────────────────

def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


@function_tool
async def pipeline_snapshot() -> str:
    """The live board in one call: every non-archived run (id, status, current stage,
    pending gate and its age, created_by), runner heartbeats, and today's estimated
    spend. This is the ground truth for any "what's happening / what's blocked /
    what needs a human" question — always call it rather than answering from memory.
    """
    from pipeline import est_cost_usd
    conn = await asyncpg.connect(db_urls()[1])
    try:
        runs = await conn.fetch(
            """SELECT r.id, r.status, r.current_stage, r.created_by,
                      r.updated_at, a.gate, a.requested_at
               FROM runs r LEFT JOIN approvals a
                 ON a.run_id = r.id AND a.status = 'pending'
               ORDER BY r.updated_at DESC LIMIT 40""")
        runners = await conn.fetch(
            "SELECT name, EXTRACT(EPOCH FROM now()-last_seen)::int AS age_s FROM runners")
        today = await conn.fetch(
            """SELECT model, sum(input_tokens)::bigint AS inp,
                      sum(cached_input_tokens)::bigint AS cached,
                      sum(output_tokens)::bigint AS outp
               FROM stage_executions WHERE started_at >= date_trunc('day', now())
               GROUP BY model""")
        now = datetime.now(timezone.utc)
        return _j({
            "runs": [{
                "id": r["id"], "status": r["status"], "stage": r["current_stage"],
                "by": r["created_by"],
                "pending_gate": r["gate"],
                "gate_age_h": round((now - r["requested_at"]).total_seconds() / 3600, 1)
                              if r["requested_at"] else None,
                "idle_h": round((now - r["updated_at"]).total_seconds() / 3600, 1),
            } for r in runs],
            "runners": [{"name": r["name"], "seen_s_ago": r["age_s"],
                         "online": r["age_s"] is not None and r["age_s"] < 90}
                        for r in runners],
            "today_est_usd": round(sum(
                est_cost_usd(t["inp"], t["cached"], t["outp"], t["model"]) for t in today), 2),
        })
    finally:
        await conn.close()


@function_tool
async def run_detail(run_id: str) -> str:
    """Everything the database knows about one run: stage executions (status,
    attempt, runner, error, token spend), pending approvals, artifacts, and the
    last 15 audit events. Use after pipeline_snapshot when one run needs depth.
    """
    conn = await asyncpg.connect(db_urls()[1])
    try:
        run = await conn.fetchrow("SELECT * FROM runs WHERE id = $1", run_id)
        if not run:
            return _j({"error": f"no run '{run_id}'"})
        execs = await conn.fetch(
            """SELECT stage, attempt, status, runner, error, model, total_tokens,
                      started_at, finished_at
               FROM stage_executions WHERE run_id = $1 ORDER BY started_at""", run_id)
        gates = await conn.fetch(
            "SELECT gate, status, requested_at, decided_by FROM approvals WHERE run_id = $1",
            run_id)
        arts = await conn.fetch(
            "SELECT stage, kind, uri FROM artifacts WHERE run_id = $1", run_id)
        events = await conn.fetch(
            """SELECT actor, type, at FROM events WHERE run_id = $1
               ORDER BY at DESC LIMIT 15""", run_id)
        return _j({
            "run": {k: run[k] for k in ("id", "status", "current_stage", "created_by",
                                        "product_repo", "product_branch", "created_at")},
            "stages": [dict(e) for e in execs],
            "gates": [dict(g) for g in gates],
            "artifacts": [dict(a) for a in arts],
            "recent_events": [dict(e) for e in events],
        })
    finally:
        await conn.close()


@function_tool
async def spend_summary(days: int = 7) -> str:
    """Token spend for the last N days, split into pipeline stages and chat/consult
    turns, per model, with estimated dollars (exact tokens, provisional rates) and
    the count of unmetered executions (crashed before usage was recorded — real
    spend is higher than the estimate).
    """
    from pipeline import est_cost_usd
    days = max(1, min(int(days or 7), 60))
    conn = await asyncpg.connect(db_urls()[1])
    try:
        out = {}
        for label, table in (("stages", "stage_executions"), ("chat", "chat_turns")):
            rows = await conn.fetch(
                f"""SELECT model, count(*)::int AS n,
                           sum(input_tokens)::bigint AS inp,
                           sum(cached_input_tokens)::bigint AS cached,
                           sum(output_tokens)::bigint AS outp,
                           count(*) FILTER (WHERE total_tokens IS NULL)::int AS unmetered
                    FROM {table} WHERE started_at >= now() - make_interval(days => $1)
                    GROUP BY model""", days)
            out[label] = [{
                "model": r["model"], "n": r["n"], "input_tokens": r["inp"],
                "cached_input_tokens": r["cached"], "output_tokens": r["outp"],
                "unmetered": r["unmetered"],
                "est_usd": round(est_cost_usd(r["inp"], r["cached"], r["outp"], r["model"]), 2),
            } for r in rows]
        return _j({"days": days, **out})
    finally:
        await conn.close()


# ── operating the factory from chat: the executor + the confirmation gate (D21) ──

class PipelineExecutor:
    """Runs `pipeline.py`'s own `cmd_*` coroutines and turns their CLI manners (print,
    `sys.exit("why")`) into a result dict.

    Reuse over reimplementation, deliberately: the approval row, `gate-decisions.md`,
    the runboard render, the rework rules and every event those commands write stay in
    exactly ONE place. A second copy of the gate logic living in the chat layer is how
    the two surfaces would quietly start disagreeing about what an approval is.

    Every call also logs one `pipeline_action` event whose actor is the HUMAN who asked
    (`human:{by}` — `human:slack:U123` from the bridge), never the agent, so the audit
    log answers "who did this" identically for CLI, web chat and Slack.
    """

    def __init__(self, channel: str = "web-chat"):
        self.channel = channel

    async def _log(self, run_id: str | None, by: str, action: str, data: dict) -> None:
        conn = await asyncpg.connect(db_urls()[1])
        try:
            await conn.execute(
                "INSERT INTO events (run_id, actor, type, data) VALUES ($1,$2,$3,$4)",
                run_id, f"human:{by}", "pipeline_action",
                json.dumps({"action": action, "channel": self.channel, **data}))
        finally:
            await conn.close()

    async def _call(self, coro) -> dict:
        """Capture what the command printed; a SystemExit is a refusal, not a crash."""
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                await coro
        except SystemExit as e:                 # pipeline.py's way of saying no
            out = buf.getvalue().strip()
            print(out, file=sys.stderr) if out else None
            return {"ok": False, "error": str(e) or "refused", "output": out}
        except Exception as e:                  # noqa: BLE001 — surface, never swallow
            out = buf.getvalue().strip()
            print(out, file=sys.stderr) if out else None
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "output": out}
        out = buf.getvalue().strip()
        print(out) if out else None             # the journal still sees it
        return {"ok": True, "output": out}

    async def start_run(self, brief_path: str, run_id: str | None, by: str, repo: str,
                        base_branch: str, coding_mode: str, working_branch: str = "") -> dict:
        import pipeline
        brief = Path(brief_path)
        if run_id is None:
            # Mirrors cmd_run's own default so the caller can name the run it just made;
            # passing it explicitly means the id reported IS the id created.
            run_id = f"feat-{datetime.now(timezone.utc):%Y%m%d}-{brief.stem.lstrip('_').lower()}"
        res = await self._call(pipeline.cmd_run(
            brief_path, run_id, by, False, repo, base_branch, coding_mode, working_branch))
        res["run_id"] = run_id if res["ok"] else None
        await self._log(res["run_id"], by, "start_run",
                        {"brief": brief_path, "product_repo": repo, "base_branch": base_branch,
                         "coding_mode": coding_mode, "ok": res["ok"],
                         "error": res.get("error")})
        return res

    async def decide(self, run_id: str, gate: str, by: str, note: str, approved: bool) -> dict:
        import pipeline
        res = await self._call(pipeline.cmd_decide(run_id, gate, by, note, approved))
        await self._log(run_id, by, "decide_gate",
                        {"gate": gate, "decision": "approve" if approved else "reject",
                         "note": note, "ok": res["ok"], "error": res.get("error")})
        return res

    async def rework(self, run_id: str, to_stage: str, by: str, note: str) -> dict:
        import pipeline
        res = await self._call(pipeline.cmd_rework(run_id, to_stage, by, note))
        await self._log(run_id, by, "rework",
                        {"to": to_stage, "note": note, "ok": res["ok"], "error": res.get("error")})
        return res

    async def retry(self, run_id: str, by: str) -> dict:
        import pipeline
        res = await self._call(pipeline.cmd_retry(run_id))
        await self._log(run_id, by, "retry", {"ok": res["ok"], "error": res.get("error")})
        return res

    async def set_product(self, run_id: str, by: str, repo: str, branch: str,
                          working: str = "") -> dict:
        import pipeline
        res = await self._call(pipeline.cmd_set_product(run_id, repo, branch, working))
        await self._log(run_id, by, "set_product",
                        {"repo": repo, "branch": branch, "working_branch": working,
                         "ok": res["ok"], "error": res.get("error")})
        return res


CONFIRM_WORD = "confirm"


def _norm(text: str) -> str:
    """Confirmation matching forgives case, punctuation and spacing — and nothing else.
    The WORDS have to be the human's own."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def confirmation_phrase(verb: str, subject: str) -> str:
    return f"{CONFIRM_WORD} {verb} {subject}"


def confirmed(user_text: str, phrase: str) -> bool:
    """Is this exact phrase in the human's own most recent message?

    The whole safety property of the write tools is in this one call, and in WHERE its
    argument comes from: `run_chat_turn` closes the tools over the text of the turn
    being served. The model can print the phrase, repeat it, or claim it was said — the
    server never looks at anything the model produced, and a phrase from an earlier turn
    is not the argument, so it cannot re-authorise a later action.
    """
    n = _norm(user_text)
    return bool(n) and _norm(phrase) in n


class WriteToolError(RuntimeError):
    pass


async def _run_row(run_id: str) -> dict | None:
    conn = await asyncpg.connect(db_urls()[1])
    try:
        r = await conn.fetchrow(
            """SELECT id, status, current_stage, coding_mode, product_repo, product_branch,
                      product_working_branch, created_by FROM runs WHERE id = $1""", run_id)
        return dict(r) if r else None
    finally:
        await conn.close()


async def _pending_gate(run_id: str, gate: str) -> dict | None:
    conn = await asyncpg.connect(db_urls()[1])
    try:
        r = await conn.fetchrow(
            """SELECT id, gate, requested_at, payload FROM approvals
               WHERE run_id = $1 AND gate = $2 AND status = 'pending'""", run_id, gate)
        return dict(r) if r else None
    finally:
        await conn.close()


def make_write_tools(publish, by: str, user_text: str, run_scope: str | None = None,
                     executor: PipelineExecutor | None = None) -> list:
    """The `lantern` chat agent's hands (D21).

    Three of the five act on a run's fate — starting it, sending it backwards, deciding a
    gate — and all three are two-step: the tool renders a decision card and returns
    WITHOUT acting; the developer types the confirmation phrase in their own next
    message; the server checks that message and only then calls the pipeline. The model
    is never the authority for its own action, and `by` is the signed-in web user on
    every event, so a chat approval is auditably a human's.
    """
    ex = executor or PipelineExecutor("web-chat")

    def card(verb: str, subject: str, title: str, lines: list[str],
             run_id: str | None = None, gate: str | None = None) -> str:
        phrase = confirmation_phrase(verb, subject)
        publish({"kind": "card", "verb": verb, "subject": subject, "phrase": phrase,
                 "title": title, "lines": lines, "run_id": run_id, "gate": gate})
        body = "\n".join(f"- {ln}" for ln in lines)
        return (f"NOT DONE — this needs {by}'s explicit confirmation first.\n\n"
                f"{title}\n{body}\n\n"
                f"Show this to the developer and ask them to reply with exactly:\n\n"
                f"    {phrase}\n\n"
                "Then call this tool again with the same arguments. Do not write that "
                "phrase yourself and do not claim it was said: the server reads the "
                "developer's own most recent message and refuses anything else.")

    def done(action: str, res: dict, run_id: str | None = None, gate: str | None = None) -> str:
        publish({"kind": "action", "action": action, "ok": bool(res.get("ok")),
                 "run_id": run_id, "gate": gate, "by": by,
                 "detail": (res.get("output") or res.get("error") or "")[:OUT_SNIPPET]})
        if res.get("ok"):
            return (f"DONE — {action}, recorded as {by}.\n"
                    + (res.get("output") or "").strip())
        return (f"REFUSED by the pipeline — nothing changed.\n{res.get('error', '')}\n"
                f"{(res.get('output') or '').strip()}").strip()

    @function_tool
    async def start_run(idea: str, title: str, brief_path: str, product_repo: str,
                        base_branch: str, coding_mode: str, must_haves: str) -> str:
        """Start a pipeline run — TWO STEPS, the developer confirms the second.

        Give EITHER `idea` (a rough description in the developer's words; a brief is
        composed from workflow/briefs/_TEMPLATE.md and written for them) OR `brief_path`
        (an existing brief in the repo). `title` is the SHORT name for the work — two to
        five words, what you would call it in a stand-up ("runboard stage timestamps") —
        because it becomes the run id, the brief filename and the branch name, and
        outlives the sentence it came from; leave it "" only if the idea is already that
        short. `product_repo` is the repository the run implements (URL or on-box path)
        and is required for coding mode `auto`; `base_branch` defaults to main;
        `coding_mode` is `human` (the developer codes stage 3 themselves) or `auto` (the
        coding agent implements the approved plan and the host opens the pull request).
        `must_haves` is optional — one per line, they seed the story's acceptance criteria.

        Missing required fields come back as a question, not a guess. Pass "" for
        anything you were not told.
        """
        import brief_composer
        idea, brief_path = (idea or "").strip(), (brief_path or "").strip()
        mode = (coding_mode or "").strip().lower()
        base = (base_branch or "").strip() or "main"
        repo = (product_repo or "").strip()
        if bool(idea) == bool(brief_path):
            return ("Give exactly one of `idea` (I compose the brief) or `brief_path` "
                    "(a brief that already exists in workflow/briefs/).")
        if brief_path:
            p = (REPO / brief_path).resolve()
            if not p.exists() or not p.is_file():
                return f"no brief at `{brief_path}` — list workflow/briefs/ with list_dir first."
            found = brief_composer.check_brief_file(p)
            repo = repo or found["product_repo"]
            base = found["base_branch"] if base == "main" else base
            mode = mode or found["coding_mode"]
            slug, title = p.stem, found["title"]
            rel = brief_path.replace("\\", "/")
            preview: list[str] = []
        else:
            title = " ".join((title or "").split())[:80] or " ".join(idea.split())[:80]
            composed = brief_composer.compose(
                {"title": title, "problem": idea, "must_haves": must_haves,
                 "product_repo": repo, "base_branch": base, "coding_mode": mode or "human",
                 "existing_context": "Started from the Chat tab; the researcher maps the "
                                     "codebase before the story is written."},
                by=by)
            slug = composed["slug"]
            rel = f"workflow/briefs/{slug}.md"
            preview = composed["markdown"].splitlines()[:14]
            if composed["missing"] or composed["problems"]:
                asks = {"title": "a one-line title", "problem": "the problem in the user's words",
                        "product_repo": "the product repo (URL or on-box path)",
                        "coding_mode": "the coding mode — `human` or `auto`"}
                want = [asks.get(m, m) for m in composed["missing"]] + composed["problems"]
                return ("I cannot start this run yet. Ask the developer for:\n"
                        + "\n".join(f"- {w}" for w in want)
                        + "\nThen call start_run again with everything filled in.")
        if not mode:
            return ("Ask the developer which coding mode: `human` (they implement stage 3 "
                    "in their own session) or `auto` (the coding agent implements the "
                    "approved plan and the host opens the pull request).")
        if not repo:
            return ("Ask the developer which product repository this run implements — a "
                    "GitHub URL or a path on this host. `pipeline.py repos` lists what the "
                    "host can offer; a run without one blocks at stage 2.")
        run_id = brief_composer.run_id_for(brief_composer.slugify(slug))
        if not confirmed(user_text, confirmation_phrase("start", slug)):
            lines = [f"run id: `{run_id}`", f"brief: `{rel}`", f"product repo: {repo}",
                     f"base branch: {base}", f"coding mode: {mode}"]
            if preview:
                lines.append("brief preview:\n```\n" + "\n".join(preview) + "\n```")
            if mode == "auto":
                lines.append("auto mode: the coding agent will implement the approved plan "
                             "and the host will open a pull request a human reviews.")
            return card("start", slug, f"Start run `{run_id}`", lines, run_id=run_id)
        if not brief_path:
            try:
                p = brief_composer.write_brief(slug, composed["markdown"])
            except (FileExistsError, ValueError) as e:
                return f"REFUSED — {e}"
            rel = str(p.relative_to(REPO)).replace("\\", "/")
        res = await ex.start_run(rel, run_id, by, repo, base, mode, "")
        return done(f"started run `{run_id}` from `{rel}`", res, run_id=run_id)

    @function_tool
    async def decide_gate(run_id: str, gate: str, decision: str, note: str) -> str:
        """Approve or reject a pending human gate AS THE SIGNED-IN DEVELOPER — two steps.

        `decision` is `approve` or `reject`. Rejecting marks the run failed; rework then
        retry is how it comes back. `note` is the reason, recorded in gate-decisions.md
        and the approvals row — always ask for one on a rejection.

        The first call shows the developer what they are about to decide and the phrase
        they must type. Only their own typed confirmation lets the second call through.
        Never approve a gate you were not asked to approve, and never invent the note.
        """
        run_id, gate = (run_id or "").strip(), (gate or "").strip()
        decision = (decision or "").strip().lower()
        if decision not in ("approve", "reject"):
            return "decision must be `approve` or `reject`."
        run = await _run_row(run_id)
        if not run:
            return f"no run `{run_id}` — call pipeline_snapshot to see what exists."
        pending = await _pending_gate(run_id, gate)
        if not pending:
            return (f"`{run_id}` has no pending `{gate}` gate (status {run['status']}, stage "
                    f"{run['current_stage']}). Nothing to decide.")
        subject = f"{gate} on {run_id}"
        if not confirmed(user_text, confirmation_phrase(decision, subject)):
            waited = ""
            if pending.get("requested_at"):
                hrs = (datetime.now(timezone.utc) - pending["requested_at"]).total_seconds() / 3600
                waited = f"waiting {hrs:.1f} h"
            lines = [f"stage: {run['current_stage']}", f"decision: {decision.upper()}",
                     f"note: {note.strip() or '(none — ask for one)'}",
                     f"recorded as: {by}"]
            if waited:
                lines.append(waited)
            lines.append("the artifact being decided is in `workflow/runs/"
                         f"{run_id}/` — read it to them before they confirm")
            if decision == "reject":
                lines.append("rejecting marks the run FAILED; it returns through rework + retry")
            return card(decision, subject, f"{decision.title()} `{gate}` on `{run_id}`",
                        lines, run_id=run_id, gate=gate)
        res = await ex.decide(run_id, gate, by, note.strip(), decision == "approve")
        return done(f"{decision}d `{gate}` on `{run_id}`", res, run_id=run_id, gate=gate)

    @function_tool
    async def rework(run_id: str, to_stage: str, note: str) -> str:
        """Send a failed or gate-waiting run BACK to an earlier stage (D17's loop) —
        two steps, the developer confirms.

        `to_stage` is one of 02-pre-coding, 03-coding, 04-qa-dev. Pending approvals on the
        run expire; the same branch and session memory are kept and the stage runs again.
        `note` says why — it lands in gate-decisions.md, so make it the actual finding.
        """
        import pipeline
        run_id, to_stage = (run_id or "").strip(), (to_stage or "").strip()
        if to_stage not in pipeline.REWORK_TARGETS:
            return f"to_stage must be one of {', '.join(pipeline.REWORK_TARGETS)}."
        run = await _run_row(run_id)
        if not run:
            return f"no run `{run_id}`."
        subject = f"{run_id} to {to_stage}"
        if not confirmed(user_text, confirmation_phrase("rework", subject)):
            return card("rework", subject, f"Send `{run_id}` back to `{to_stage}`",
                        [f"now at: {run['current_stage']} ({run['status']})",
                         f"reason: {note.strip() or '(none — ask for one)'}",
                         "pending approvals on this run expire",
                         "the branch and the stage's session memory are kept",
                         f"recorded as: {by}"], run_id=run_id)
        res = await ex.rework(run_id, to_stage, by, note.strip())
        return done(f"sent `{run_id}` back to `{to_stage}`", res, run_id=run_id)

    @function_tool
    async def retry(run_id: str) -> str:
        """Re-queue a failed run at its CURRENT stage — a fresh attempt with the same
        session memory. Use after the blocker a stage reported has been answered (for a
        BLOCKED stage that usually means the brief or the run folder was edited).
        Reversible and stage-local, so it runs on your say-so; say what you retried.
        """
        run_id = (run_id or "").strip()
        run = await _run_row(run_id)
        if not run:
            return f"no run `{run_id}`."
        if run["status"] not in ("failed", "waiting_gate", "running"):
            return f"`{run_id}` is {run['status']} — retry applies to a run that stopped."
        res = await ex.retry(run_id, by)
        return done(f"re-queued `{run_id}` at `{run['current_stage']}`", res, run_id=run_id)

    @function_tool
    async def set_product(run_id: str, product_repo: str, base_branch: str,
                          working_branch: str) -> str:
        """Point an existing run at a product repository (D15). The host syncs its mirror
        and proves the branches exist, so a wrong repo fails here rather than inside a
        sandbox three stages later. `working_branch` is an EXISTING feat/*|fix/*|proto/*
        branch to continue on — pass "" for a fresh branch derived from the run id.
        """
        run_id = (run_id or "").strip()
        repo = (product_repo or "").strip()
        if not repo:
            return "which repository? A GitHub URL or a path on this host (`pipeline.py repos`)."
        run = await _run_row(run_id)
        if not run:
            return f"no run `{run_id}`."
        res = await ex.set_product(run_id, by, repo, (base_branch or "").strip() or "main",
                                   (working_branch or "").strip())
        return done(f"pointed `{run_id}` at {repo}", res, run_id=run_id)

    return [start_run, decide_gate, rework, retry, set_product]


WRITE_TOOL_PROTOCOL = """
# Acting on the factory (D21)

You have five tools that CHANGE things: `start_run`, `decide_gate`, `rework`, `retry`,
`set_product`. Everything else you have is read-only. The rules are not negotiable and
the server enforces them — arguing with them only wastes the developer's turn.

- **Three of them need the developer's own confirmation: `start_run`, `decide_gate`,
  `rework`.** Call the tool once: it returns a decision card and does nothing. Show the
  card, ask for the exact phrase, and call the tool again after they have typed it. The
  server checks THEIR most recent message for that phrase. You cannot confirm on their
  behalf — writing the phrase yourself, or saying it was said, changes nothing and will
  be visible in the transcript.
- **Never decide a gate you were not asked to decide**, never turn "looks fine" into an
  approval, and never invent the note. On a rejection, ask what the reason is first: it
  is written into `gate-decisions.md`, where the next stage reads it.
- **You act as {by}.** Every action is recorded with their identity, in the same audit
  log as CLI and Slack actions. That is why the confirmation matters.
- **What you still cannot do:** merge anything, edit files, or move a gate the pipeline
  says is not pending. Those refusals come back as REFUSED — relay them plainly instead
  of trying another route.
- Before you act, read enough to be accurate: `pipeline_snapshot` for what is waiting,
  `run_detail` for one run, `read_file` for the artifact the gate is actually about.
  A gate card without the artifact in it is not a decision, it is a prompt to guess.
"""


# ── building the agent for one session ───────────────────────────────────────

def make_custom_append_memory(slug: str, execution_key: str):
    """append_memory for custom agents: role_memory only, no memory.md render
    (there is no agents/<slug>/ folder to render into)."""
    @function_tool
    async def append_memory(entry: str) -> str:
        """Record ONE durable learning in your memory — it is embedded into your
        instructions on future consults. Make it dated-quality judgement: concrete,
        with the why — never a session log. Call once per distinct learning."""
        conn = await asyncpg.connect(db_urls()[1])
        try:
            await conn.execute(
                """INSERT INTO role_memory (role, run_id, stage, execution_key, entry)
                   VALUES ($1, NULL, NULL, $2, $3)""", slug, execution_key, entry.strip())
        finally:
            await conn.close()
        return "memory entry recorded"
    return append_memory


def make_ask_specialist(publish, usage_sink: list[dict]):
    """The orchestrator's handoff: one-shot consult of a fleet role, usage metered
    into the parent turn's ledger, the exchange surfaced in the live trace."""
    @function_tool
    async def ask_specialist(role: str, question: str) -> str:
        """Hand ONE question to a Lantern fleet specialist (their charter, skills and
        memory answer it) and return their answer verbatim. Roles: see AGENTS.md's
        pipeline table (ui-ux, pre-coding, coding, qa-dev, post-coding, security,
        qa-staging, debug). Use for depth you don't have; ask one sharp question,
        not a task list."""
        roles = consult_roles()
        if role not in roles:
            return f"unknown role '{role}' — available: {', '.join(roles)}"
        publish({"kind": "specialist", "role": role, "question": question[:ARG_SNIPPET]})
        conn = await asyncpg.connect(db_urls()[1])
        try:
            await render_role_memory(conn, role)   # their prompt embeds memory — fresh view
        finally:
            await conn.close()
        agent = Agent(name=role, model=model_for(role),
                      model_settings=model_settings_for(role, purpose="chat"),
                      instructions=build_consult_instructions(role),
                      tools=[read_file, list_dir])
        result = await run_oneshot(agent, input=question, max_turns=SPECIALIST_MAX_TURNS)
        u = usage_dict(result)
        usage_sink.append({**u, "model": model_for(role)})
        answer = str(result.final_output)
        publish({"kind": "specialist_done", "role": role,
                 "answer": answer[:OUT_SNIPPET], "tokens": u.get("total_tokens")})
        return answer
    return ask_specialist


async def build_chat_agent(conn, session, publish, usage_sink: list[dict],
                           by: str = "", user_text: str = "") -> Agent:
    slug = session["agent"]
    directory = await agent_directory(conn)
    info = directory.get(slug)
    if info is None:
        raise ValueError(f"agent '{slug}' no longer exists")
    scope = run_scope_note(session["run_id"]) if session["run_id"] else ""

    if info["kind"] == "orchestrator":
        # D21: only the orchestrator gets hands, and only for a signed-in human whose
        # own words this turn are what the confirmation gate reads. A turn with no
        # identity (a replay, a future non-web caller) is read-only by construction.
        actor = by or session["created_by"]
        write = make_write_tools(publish, actor, user_text, session["run_id"]) if by else []
        return Agent(
            name="lantern", model=agent_model(info),
            model_settings=agent_model_settings(info),
            instructions=build_lantern_instructions(actor, can_write=bool(write)) + scope,
            tools=[read_file, list_dir, pipeline_snapshot, run_detail, spend_summary,
                   make_ask_specialist(publish, usage_sink)] + write)
    if info["kind"] == "fleet":
        await render_role_memory(conn, slug)       # same freshness rule as cmd_ask
        return Agent(
            name=slug, model=agent_model(info),
            model_settings=agent_model_settings(info),
            instructions=build_consult_instructions(slug) + scope,
            tools=[read_file, list_dir,
                   make_append_memory(slug, None, None, session["id"])])
    return Agent(
        name=info["name"], model=agent_model(info),
        model_settings=agent_model_settings(info),
        instructions=await build_custom_instructions(conn, info["row"]) + scope,
        tools=[read_file, list_dir,
               make_custom_append_memory(slug, session["id"])])


# ── the turn runner ──────────────────────────────────────────────────────────

# Indirection so tests can fake the model loop without Azure credentials.
run_streamed = Runner.run_streamed
run_oneshot = Runner.run

DELTA_FLUSH_CHARS = 48
DELTA_FLUSH_S = 0.15
THINK_PING_S = 1.0          # at most one «thinking» ping a second; it is a hint


def _tool_call_view(item) -> dict:
    raw = getattr(item, "raw_item", None)
    name = getattr(raw, "name", None) or type(raw).__name__
    args = getattr(raw, "arguments", "") or ""
    if isinstance(args, (dict, list)):
        args = _j(args)
    return {"kind": "tool", "name": str(name), "args": str(args)[:ARG_SNIPPET]}


def _tool_output_view(item) -> dict:
    out = getattr(item, "output", "")
    return {"kind": "tool_done", "output": str(out)[:OUT_SNIPPET]}


async def run_chat_turn(pool: asyncpg.Pool, session, turn_id: int, user_text: str,
                        by: str, bus: TurnBus = BUS) -> None:
    """One user turn, end to end: stream model events onto the bus, persist the
    trace as it grows (so 'what was happening' survives a crash), record the
    ledger, close out the turn row. Designed to run as an asyncio.Task; the bus
    entry MUST already exist (bus.start was called by the sender)."""
    t0 = time.monotonic()
    trace: list[dict] = []
    usage_sink: list[dict] = []
    result = None

    def publish(ev: dict, persist: bool = True) -> None:
        ev = {**ev, "t": round(time.monotonic() - t0, 1)}
        if persist:
            trace.append(ev)
        bus.publish(session["id"], ev)

    async def flush_trace() -> None:
        await pool.execute("UPDATE chat_turns SET trace = $2 WHERE id = $1",
                           turn_id, json.dumps(trace))

    async def close_turn(status: str, final_text: str | None, error: str | None) -> None:
        merged: dict = {}
        for u in usage_sink:
            for k in ("requests", "input_tokens", "cached_input_tokens",
                      "output_tokens", "total_tokens"):
                if u.get(k) is not None:
                    merged[k] = merged.get(k, 0) + u[k]
        models = {u.get("model") for u in usage_sink if u.get("model")}
        model = models.pop() if len(models) == 1 else ("mixed" if models else None)
        await pool.execute(
            """UPDATE chat_turns
               SET status=$2, final_text=$3, error=$4, trace=$5, model=$6,
                   requests=$7, input_tokens=$8, cached_input_tokens=$9,
                   output_tokens=$10, total_tokens=$11, finished_at=now()
               WHERE id = $1""",
            turn_id, status, final_text, error, json.dumps(trace), model,
            merged.get("requests"), merged.get("input_tokens"),
            merged.get("cached_input_tokens"), merged.get("output_tokens"),
            merged.get("total_tokens"))
        await pool.execute(
            "UPDATE chat_sessions SET last_at = now(), title = coalesce(title, $2) WHERE id = $1",
            session["id"], " ".join(user_text.split())[:80] or "(empty)")
        await pool.execute(
            "INSERT INTO events (run_id, actor, type, data) VALUES ($1,$2,$3,$4)",
            session["run_id"], f"human:{by}", "consult",
            json.dumps({"role": session["agent"], "session": session["id"],
                        "channel": "web", "status": status,
                        "prompt": user_text[:300], "usage": merged}))

    async def _close_and_total(status: str, final_text, error) -> None:
        """Stopped/failed turns still settle the ledger and tell the page."""
        await close_turn(status, final_text, error)
        publish({"kind": "totals", "session": await session_totals(pool, session["id"])},
                persist=False)

    try:
        ensure_client()
        async with pool.acquire() as conn:
            # `user_text` is THIS turn's human message and nothing else — the write
            # tools close over it, so a confirmation can only ever come from the
            # message being served (D21).
            agent = await build_chat_agent(conn, session, publish, usage_sink,
                                           by=by, user_text=user_text)
        sdk_session = SQLAlchemySession(session["id"], engine=_sdk_engine(),
                                        create_tables=True)
        result = run_streamed(agent, input=user_text, session=sdk_session,
                              max_turns=MAX_TURNS_LANTERN
                              if session["agent"] == LANTERN_AGENT else MAX_TURNS_CONSULT)

        buf, last_flush = [], time.monotonic()
        last_think = 0.0
        async for ev in result.stream_events():
            etype = getattr(ev, "type", "")
            if etype == "raw_response_event":
                d = ev.data
                dtype = getattr(d, "type", "")
                if dtype == "response.output_text.delta":
                    buf.append(d.delta or "")
                    if (sum(map(len, buf)) >= DELTA_FLUSH_CHARS
                            or time.monotonic() - last_flush >= DELTA_FLUSH_S):
                        publish({"kind": "delta", "text": "".join(buf)}, persist=False)
                        buf, last_flush = [], time.monotonic()
                elif dtype.startswith("response.reasoning"):
                    # Reasoning is the model's scratchpad, not its answer: it
                    # says the status line should read «Thinking» and nothing
                    # more. Never buffered into the reply, never persisted into
                    # the trace — the transcript keeps only what the agent did.
                    if time.monotonic() - last_think >= THINK_PING_S:
                        last_think = time.monotonic()
                        publish({"kind": "thinking"}, persist=False)
            elif etype == "run_item_stream_event":
                if buf:
                    publish({"kind": "delta", "text": "".join(buf)}, persist=False)
                    buf, last_flush = [], time.monotonic()
                item = ev.item
                itype = getattr(item, "type", "")
                if itype == "tool_call_item":
                    publish(_tool_call_view(item))
                    await flush_trace()
                elif itype == "tool_call_output_item":
                    publish(_tool_output_view(item))
                elif itype == "reasoning_item":
                    publish({"kind": "thinking"}, persist=False)
        if buf:
            publish({"kind": "delta", "text": "".join(buf)}, persist=False)

        final = "" if result.final_output is None else str(result.final_output)
        usage_sink.append({**usage_dict(result),
                           "model": getattr(agent, "model", None)})
        await close_turn("done", final, None)
        elapsed = round(time.monotonic() - t0, 1)
        row = await pool.fetchrow("SELECT * FROM chat_turns WHERE id = $1", turn_id)
        publish({"kind": "final", "turn_id": turn_id, "text": final,
                 "model": row["model"], "total_tokens": row["total_tokens"],
                 "input_tokens": row["input_tokens"],
                 "cached_input_tokens": row["cached_input_tokens"],
                 "output_tokens": row["output_tokens"], "elapsed_s": elapsed,
                 "session": await session_totals(pool, session["id"])},
                persist=False)
    except asyncio.CancelledError:
        try:
            if result is not None:
                result.cancel()                 # stop the SDK's background run
                # Whatever the completed requests already cost is real spend —
                # record it rather than leaving the stopped turn unmetered.
                u = usage_dict(result)
                if u:
                    usage_sink.append({**u, "model": getattr(agent, "model", None)})
        except Exception:                       # noqa: BLE001 — best effort on teardown
            pass
        if SHUTTING_DOWN:
            publish({"kind": "error", "message": INTERRUPTED})
            await asyncio.shield(_close_and_total("failed", None, INTERRUPTED))
        else:
            publish({"kind": "stopped"})
            await asyncio.shield(_close_and_total("stopped", None, "stopped by the developer"))
        raise
    except Exception as e:                      # noqa: BLE001 — turn boundary: persist, then surface
        msg = f"{type(e).__name__}: {e}"
        publish({"kind": "error", "message": msg[:600]})
        await _close_and_total("failed", None, msg[:2000])
    finally:
        bus.finish(session["id"])


async def session_totals(pool, session_id: str) -> dict:
    """{est_usd, tokens, turns, unmetered} for one conversation — what the header
    and composer footer show; sent with each final event so they never go stale."""
    from pipeline import est_cost_usd
    rows = await pool.fetch(
        """SELECT model, sum(input_tokens)::bigint AS inp,
                  sum(cached_input_tokens)::bigint AS cached,
                  sum(output_tokens)::bigint AS outp, sum(total_tokens)::bigint AS tot
           FROM chat_turns WHERE session_id = $1 AND total_tokens IS NOT NULL
           GROUP BY model""", session_id)
    counts = await pool.fetchrow(
        """SELECT count(*)::int AS n,
                  count(*) FILTER (WHERE total_tokens IS NULL AND status <> 'running')::int AS unmetered
           FROM chat_turns WHERE session_id = $1""", session_id)
    return {"est_usd": round(sum(est_cost_usd(r["inp"], r["cached"], r["outp"], r["model"])
                                 for r in rows), 4),
            "tokens": int(sum(r["tot"] or 0 for r in rows)),
            "turns": counts["n"], "unmetered": counts["unmetered"]}


_engine = None


def _sdk_engine():
    """One shared async engine for all SDK sessions — per-turn engines would leak
    connections in a long-lived web process (from_url creates a new engine each call)."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(db_urls()[0], pool_size=3, max_overflow=2)
    return _engine
