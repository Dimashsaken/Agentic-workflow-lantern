"""Chat service — the engine behind Mission Control's Chat tab (docs/CHAT.md, D13).

Web consult mode: the same advisory, read-only agents as `pipeline.py ask` (D11),
plus an orchestrator agent ("lantern") that reads the pipeline database and can
hand questions to specialists, plus user-created custom agents. Harness-agnostic
on purpose: FastAPI imports it today, a Slack surface can import it tomorrow.

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
import json
import os
import re
import secrets
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
    consult_roles, db_urls, list_dir, make_append_memory, model_for, read_file,
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
                           "LANTERN_MODEL_REASONING", "LANTERN_MODEL_FAST")
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
    var = "LANTERN_MODEL_FAST" if info.get("model_pref") == "fast" else "LANTERN_MODEL_REASONING"
    return os.environ.get(var, "")


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


def build_lantern_instructions() -> str:
    """The orchestrator chat: the system contract + the pipeline database in view."""
    contract = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    return (
        "# Lantern — orchestrator consult\n"
        "You are **Lantern**, the voice of the agentic delivery pipeline, consulted "
        "by a signed-in developer from Mission Control. You speak first-person, "
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
        "The deliberate line (D11): consults are advisory and read-only. You cannot "
        "start runs, decide gates, or change files — when asked to, say exactly "
        "what the human should do instead (`pipeline.py run ...`, the Gates tab, a "
        "brief in workflow/briefs/). Numbers you report come from the tools, never "
        "from memory of them.\n\n"
        "# The system you narrate (AGENTS.md, verbatim)\n\n" + contract)


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


async def build_chat_agent(conn, session, publish, usage_sink: list[dict]) -> Agent:
    slug = session["agent"]
    directory = await agent_directory(conn)
    info = directory.get(slug)
    if info is None:
        raise ValueError(f"agent '{slug}' no longer exists")
    scope = run_scope_note(session["run_id"]) if session["run_id"] else ""

    if info["kind"] == "orchestrator":
        return Agent(
            name="lantern", model=agent_model(info),
            instructions=build_lantern_instructions() + scope,
            tools=[read_file, list_dir, pipeline_snapshot, run_detail, spend_summary,
                   make_ask_specialist(publish, usage_sink)])
    if info["kind"] == "fleet":
        await render_role_memory(conn, slug)       # same freshness rule as cmd_ask
        return Agent(
            name=slug, model=agent_model(info),
            instructions=build_consult_instructions(slug) + scope,
            tools=[read_file, list_dir,
                   make_append_memory(slug, None, None, session["id"])])
    return Agent(
        name=info["name"], model=agent_model(info),
        instructions=await build_custom_instructions(conn, info["row"]) + scope,
        tools=[read_file, list_dir,
               make_custom_append_memory(slug, session["id"])])


# ── the turn runner ──────────────────────────────────────────────────────────

# Indirection so tests can fake the model loop without Azure credentials.
run_streamed = Runner.run_streamed
run_oneshot = Runner.run

DELTA_FLUSH_CHARS = 48
DELTA_FLUSH_S = 0.15


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
            agent = await build_chat_agent(conn, session, publish, usage_sink)
        sdk_session = SQLAlchemySession(session["id"], engine=_sdk_engine(),
                                        create_tables=True)
        result = run_streamed(agent, input=user_text, session=sdk_session,
                              max_turns=MAX_TURNS_LANTERN
                              if session["agent"] == LANTERN_AGENT else MAX_TURNS_CONSULT)

        buf, last_flush = [], time.monotonic()
        async for ev in result.stream_events():
            etype = getattr(ev, "type", "")
            if etype == "raw_response_event":
                d = ev.data
                if getattr(d, "type", "") == "response.output_text.delta":
                    buf.append(d.delta or "")
                    if (sum(map(len, buf)) >= DELTA_FLUSH_CHARS
                            or time.monotonic() - last_flush >= DELTA_FLUSH_S):
                        publish({"kind": "delta", "text": "".join(buf)}, persist=False)
                        buf, last_flush = [], time.monotonic()
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
