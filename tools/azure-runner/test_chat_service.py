"""Chat service tests — the turn lifecycle without a model (docs/CHAT.md).

    .venv/Scripts/python test_chat_service.py     (needs LANTERN_DATABASE_URL + init-db)

Runner.run_streamed is faked, so this proves the plumbing the UI depends on:
schema upgrade idempotence, session/turn persistence, the trace + token ledger
landing on the turn row, the failure path recording honestly, orphaned-turn
reaping, and the TurnBus replay/fan-out semantics. No Azure credentials are
used; every row the test writes is deleted at the end.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
# Faked model loop → dummy credentials are enough anywhere (CI, fresh laptop).
for var, dummy in (("AZURE_OPENAI_ENDPOINT", "https://test.invalid"),
                   ("AZURE_OPENAI_API_KEY", "test"),
                   ("LANTERN_MODEL_REASONING", "test-reasoning"),
                   ("LANTERN_MODEL_FAST", "test-fast")):
    os.environ.setdefault(var, dummy)

import chat_service as cs  # noqa: E402
from orchestrator import db_urls  # noqa: E402

USER = "test-chat-user"
AGENT_NAME = "Test Chat Agent"
AGENT_SLUG = "test-chat-agent"

failures: list[str] = []


def check(name: str, ok: bool) -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        failures.append(name)


def fake_stream(events, final="All done.", usage=None, fail_after=None):
    """A stand-in for Runner.run_streamed: replays scripted events."""
    u = usage or {"requests": 2, "input_tokens": 1200, "output_tokens": 80,
                  "total_tokens": 1280}
    usage_ns = SimpleNamespace(
        **{k: v for k, v in u.items()},
        input_tokens_details=SimpleNamespace(cached_tokens=u.get("cached", 0)))

    class Result:
        final_output = final
        context_wrapper = SimpleNamespace(usage=usage_ns)

        def cancel(self, mode="immediate"):
            pass

        async def stream_events(self):
            for i, ev in enumerate(events):
                if fail_after is not None and i == fail_after:
                    raise RuntimeError("model exploded mid-stream")
                yield ev

    def runner(agent, input, session=None, max_turns=None):
        return Result()
    return runner


def delta(text):
    return SimpleNamespace(type="raw_response_event",
                           data=SimpleNamespace(type="response.output_text.delta", delta=text))


def tool_call(name, args):
    return SimpleNamespace(
        type="run_item_stream_event",
        item=SimpleNamespace(type="tool_call_item",
                             raw_item=SimpleNamespace(name=name, arguments=args)))


def tool_out(output):
    return SimpleNamespace(
        type="run_item_stream_event",
        item=SimpleNamespace(type="tool_call_output_item", output=output))


async def cleanup(conn) -> None:
    await conn.execute(
        "DELETE FROM chat_turns WHERE session_id IN "
        "(SELECT id FROM chat_sessions WHERE created_by = $1)", USER)
    await conn.execute("DELETE FROM chat_sessions WHERE created_by = $1", USER)
    await conn.execute("DELETE FROM custom_agents WHERE slug LIKE 'test-chat-%'")
    await conn.execute("DELETE FROM role_memory WHERE role LIKE 'test-chat-%'")
    await conn.execute("DELETE FROM events WHERE actor = $1", f"human:{USER}")


async def main() -> None:
    conn = await asyncpg.connect(db_urls()[1])
    pool = await asyncpg.create_pool(db_urls()[1], min_size=1, max_size=3)

    # 1 — schema upgrade is idempotent
    await cs.ensure_chat_tables(conn)
    await cs.ensure_chat_tables(conn)
    n = await conn.fetchval(
        "SELECT count(*) FROM information_schema.tables WHERE table_name IN "
        "('chat_sessions', 'chat_turns', 'custom_agents')")
    check("ensure_chat_tables creates all three tables, twice, without error", n == 3)

    await cleanup(conn)
    try:
        # 2 — custom agents: creation, collision rules, composed instructions
        slug = await cs.create_custom_agent(conn, AGENT_NAME, "Answers test questions.",
                                            "", "reasoning", USER)
        check("create_custom_agent slugs the name", slug == AGENT_SLUG)
        try:
            await cs.create_custom_agent(conn, AGENT_NAME, "again", "", "fast", USER)
            check("duplicate custom agent rejected", False)
        except ValueError:
            check("duplicate custom agent rejected", True)
        try:
            await cs.create_custom_agent(conn, "security", "shadow a fleet role", "", "fast", USER)
            check("fleet-role name collision rejected", False)
        except ValueError:
            check("fleet-role name collision rejected", True)
        check("composed instructions mention grounding + memory",
              "read_file" in cs.compose_instructions("X", "y")
              and "append_memory" in cs.compose_instructions("X", "y"))
        directory = await cs.agent_directory(conn)
        check("directory holds lantern + fleet + the custom agent",
              cs.LANTERN_AGENT in directory and "security" in directory
              and AGENT_SLUG in directory)

        # 3 — sessions share the consult id convention
        sid = await cs.create_session(conn, USER, AGENT_SLUG)
        check("session id follows consult:{user}:{agent}:{name}",
              sid.startswith(f"consult:{USER}:{AGENT_SLUG}:web-"))
        session = await conn.fetchrow("SELECT * FROM chat_sessions WHERE id = $1", sid)

        # 4 — a full successful turn: deltas + tools stream, trace + ledger persist
        bus = cs.TurnBus()
        cs.run_streamed = fake_stream(
            [delta("Hello "), delta("world."),
             tool_call("read_file", '{"path": "AGENTS.md"}'),
             tool_out("# Lantern — contract…")],
            final="Hello world. It is all in AGENTS.md.")
        turn_id = await conn.fetchval(
            "INSERT INTO chat_turns (session_id, asked_by, user_text) VALUES ($1,$2,$3) RETURNING id",
            sid, USER, "What is Lantern?")
        bus.start(sid, turn_id)
        replay0, q = bus.subscribe(sid)
        await cs.run_chat_turn(pool, session, turn_id, "What is Lantern?", USER, bus)

        q_events = []
        while not q.empty():
            ev = q.get_nowait()
            if ev:
                q_events.append(ev)
        seen = [e["kind"] for e in q_events]
        check("subscriber saw deltas, the tool call, and the final",
              "delta" in seen and "tool" in seen and "final" in seen)
        turn = await conn.fetchrow("SELECT * FROM chat_turns WHERE id = $1", turn_id)
        trace = json.loads(turn["trace"])
        check("turn closed done with the final text",
              turn["status"] == "done" and "AGENTS.md" in turn["final_text"])
        check("trace persisted the tool call with its args",
              any(e["kind"] == "tool" and e["name"] == "read_file" for e in trace))
        check("ledger landed on the turn row (P0.4)",
              turn["total_tokens"] == 1280 and turn["input_tokens"] == 1200
              and turn["model"] is not None)
        title = await conn.fetchval("SELECT title FROM chat_sessions WHERE id = $1", sid)
        check("first turn titled the session", title == "What is Lantern?")
        ev_row = await conn.fetchrow(
            "SELECT * FROM events WHERE actor = $1 AND type = 'consult' ORDER BY id DESC LIMIT 1",
            f"human:{USER}")
        check("consult audit event written with usage",
              ev_row is not None and json.loads(ev_row["data"])["usage"]["total_tokens"] == 1280)
        check("bus entry cleared after the turn", bus.active(sid) is None)
        final_ev = next(e for e in q_events if e["kind"] == "final")
        totals = await cs.session_totals(pool, sid)
        check("final event carries the session ledger the header shows",
              final_ev["session"]["tokens"] == 1280 == totals["tokens"]
              and totals["turns"] == 1 and totals["est_usd"] > 0)

        # 5 — failure path: error recorded, turn never left running
        cs.run_streamed = fake_stream([delta("part"), delta("never sent")], fail_after=1)
        turn_id2 = await conn.fetchval(
            "INSERT INTO chat_turns (session_id, asked_by, user_text) VALUES ($1,$2,$3) RETURNING id",
            sid, USER, "boom")
        bus.start(sid, turn_id2)
        await cs.run_chat_turn(pool, session, turn_id2, "boom", USER, bus)
        turn2 = await conn.fetchrow("SELECT * FROM chat_turns WHERE id = $1", turn_id2)
        check("failed turn recorded honestly (status + error, no final text)",
              turn2["status"] == "failed" and "model exploded" in turn2["error"]
              and turn2["final_text"] is None)

        # 5b — a cancel during process shutdown is an interruption, not a Stop
        async def slow_events():
            yield delta("thinking…")
            await asyncio.sleep(30)

        class SlowResult:
            final_output = None
            context_wrapper = SimpleNamespace(usage=None)

            def cancel(self, mode="immediate"):
                pass

            def stream_events(self):
                return slow_events()

        cs.run_streamed = lambda agent, input, session=None, max_turns=None: SlowResult()
        for flag, want_status, want_error in ((False, "stopped", "stopped by the developer"),
                                              (True, "failed", cs.INTERRUPTED)):
            tid = await conn.fetchval(
                "INSERT INTO chat_turns (session_id, asked_by, user_text) VALUES ($1,$2,'slow') RETURNING id",
                sid, USER)
            bus.start(sid, tid)
            task = asyncio.create_task(cs.run_chat_turn(pool, session, tid, "slow", USER, bus))
            bus.attach_task(sid, task)
            await asyncio.sleep(0.3)
            cs.SHUTTING_DOWN = flag
            bus.stop(sid)
            try:
                await task
            except asyncio.CancelledError:
                pass
            cs.SHUTTING_DOWN = False
            row = await conn.fetchrow("SELECT status, error FROM chat_turns WHERE id = $1", tid)
            check(f"cancel with SHUTTING_DOWN={flag} records «{want_status}»",
                  row["status"] == want_status and row["error"] == want_error)

        # 6 — orphaned 'running' rows are reaped, but a live one is not
        orphan = await conn.fetchval(
            "INSERT INTO chat_turns (session_id, asked_by, user_text) VALUES ($1,$2,$3) RETURNING id",
            sid, USER, "orphan")
        live_bus = cs.TurnBus()
        n = await cs.reap_stale_turns(conn, live_bus, sid)
        orphan_row = await conn.fetchrow("SELECT * FROM chat_turns WHERE id = $1", orphan)
        check("orphaned running turn marked failed «interrupted»",
              n == 1 and orphan_row["status"] == "failed"
              and orphan_row["error"] == cs.INTERRUPTED)
        held = await conn.fetchval(
            "INSERT INTO chat_turns (session_id, asked_by, user_text) VALUES ($1,$2,$3) RETURNING id",
            sid, USER, "held")
        live_bus.start(sid, held)
        n = await cs.reap_stale_turns(conn, live_bus, sid)
        check("a turn the bus owns is left alone", n == 0)
        live_bus.finish(sid)

        # 7 — bus semantics: one turn per session, replay for late subscribers
        b = cs.TurnBus()
        b.start("s", 1)
        try:
            b.start("s", 2)
            check("second concurrent turn refused", False)
        except RuntimeError:
            check("second concurrent turn refused", True)
        b.publish("s", {"kind": "tool", "name": "x"})
        replay, q2 = b.subscribe("s")
        check("late subscriber replays what it missed",
              len(replay) == 1 and replay[0]["name"] == "x")
        check("stop with no task is a no-op, not an error", b.stop("s") is False)
        b.finish("s")
        # The v1 regression: a page that attached while the session was IDLE must
        # still hear the next turn (subscribers are per-session, not per-turn).
        replay_idle, q_idle = b.subscribe("s2")
        b.start("s2", 9)
        b.publish("s2", {"kind": "turn_started", "turn_id": 9})
        check("idle-attached subscriber hears a later turn",
              replay_idle == [] and q_idle.get_nowait()["turn_id"] == 9)
        b.close_all()
        check("close_all releases every open stream", q_idle.get_nowait() is None)
        b.finish("s2")
    finally:
        await cleanup(conn)
        await conn.close()
        await pool.close()

    if failures:
        print(f"\n{len(failures)} FAILED"); sys.exit(1)
    print("\nall chat_service checks passed")


if __name__ == "__main__":
    asyncio.run(main())
