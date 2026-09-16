"""Shared fakes for Mission Control route tests (stdlib, no database, no HTTP client).

The venv has no httpx, so FastAPI's TestClient is unusable: routes are called as plain
coroutines with a stub Request (only `.cookies` is read) and the module-global pool is
swapped for FakePool, which answers the app's queries from canned rows by matching SQL
substrings — the pattern test_gate_latency.py established. Rows are plain dicts.

    pool = FakePool(runs=[...], execs=[...])
    html = body_of(get(mc.run_page, "feat-x", signed(), pool=pool))
"""

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone

import asyncpg

import app as mc

NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)


def _norm(sql: str) -> str:
    return " ".join(sql.lower().split())


class FakePool:
    """Answers the app's queries from canned rows; records every query and write."""

    def __init__(self, runs=(), execs=(), approvals=(), arts=(), events=(), memory=(),
                 latency=(), runners=(), agg=(), today=(), feed=(), daily=(), per_run=(),
                 alltime=(), chat_daily=(), chat_alltime=(), alarms=(), repos=(), fail_latency=False):
        self.runs, self.execs = list(runs), list(execs)
        self.approvals, self.arts, self.events = list(approvals), list(arts), list(events)
        self.memory, self.latency, self.runners = list(memory), list(latency), list(runners)
        self.agg, self.today, self.feed = list(agg), list(today), list(feed)
        self.daily, self.per_run, self.alltime = list(daily), list(per_run), list(alltime)
        self.chat_daily, self.chat_alltime, self.alarms = list(chat_daily), list(chat_alltime), list(alarms)
        self.fail_latency = fail_latency
        self.repos = list(repos)
        self.queries: list[str] = []
        self.executed: list[tuple[str, tuple]] = []

    # ── reads ────────────────────────────────────────────────────────────────

    async def fetch(self, sql, *args):
        self.queries.append(sql)
        s = _norm(sql)
        if "percentile_cont" in s:
            if self.fail_latency:
                raise asyncpg.PostgresError("aggregate blew up")
            return self.latency
        if "from product_repos" in s:
            return self.repos
        if "from runs" in s:
            if "distinct product_repo" in s:
                return [{"product_repo": r["product_repo"]} for r in self.runs
                        if r.get("product_repo")]
            if args:                                   # /gates: id = ANY($1)
                return [r for r in self.runs if r["id"] in args[0]]
            return self.runs
        if "from approvals" in s:
            rows = self.approvals
            if "run_id = $1" in s:
                rows = [a for a in rows if a["run_id"] == args[0]]
            if "status='pending'" in s:
                rows = [a for a in rows if a["status"] == "pending"]
            elif "status != 'pending'" in s:
                rows = [a for a in rows if a["status"] != "pending"]
            return rows
        if "from runners" in s:
            return self.runners
        if "from stage_executions" in s:
            if "distinct on" in s:
                latest = {}
                for e in self.execs:
                    k = (e["run_id"], e["stage"])
                    if k not in latest or e["attempt"] > latest[k]["attempt"]:
                        latest[k] = e
                return list(latest.values())
            if "where run_id = $1" in s:
                return [e for e in self.execs if e["run_id"] == args[0]]
            if "date_trunc('day', started_at)::date as day" in s:
                return self.daily
            if "max(attempt)" in s:
                return self.agg
            if "group by run_id, model" in s:
                return self.per_run
            if "date_trunc('day', now())" in s:
                return self.today
            if "attempt > 1" in s:
                return self.feed
            if "group by model" in s:
                return self.alltime
            return []
        if "from artifacts" in s:
            return [a for a in self.arts if not args or a["run_id"] == args[0]]
        if "from events" in s:
            if "usage-check" in s:
                return self.alarms
            if "run_id = any($1)" in s:
                return [e for e in self.events if e.get("run_id") in args[0]]
            return [e for e in self.events if not args or e.get("run_id") == args[0]]
        if "from role_memory" in s:
            return [m for m in self.memory if m["execution_key"] == args[0]]
        if "from chat_turns" in s:
            return self.chat_daily if "date_trunc" in s else self.chat_alltime
        raise AssertionError(f"unexpected fetch: {sql}")

    async def fetchrow(self, sql, *args):
        self.queries.append(sql)
        s = _norm(sql)
        if "percentile_cont" in s:
            raise AssertionError("gate latency must be one grouped fetch(), not a scalar fetchrow()")
        if "from product_repos" in s:
            return next((r for r in self.repos if r["id"] == args[0]), None)
        if "from artifacts" in s:                      # /media: by id, or by the uri a manifest names
            key = "id" if "where id = $1" in s else "uri"
            return next((a for a in self.arts if a.get(key) == args[0]), None)
        if "from runs" in s:
            return next((r for r in self.runs if r["id"] == args[0]), None)
        if "from stage_executions" in s:
            return next((e for e in self.execs
                         if e["id"] == args[0] and (len(args) < 2 or e["run_id"] == args[1])), None)
        if "update approvals" in s:
            a = next((x for x in self.approvals if x["id"] == args[3] and x["status"] == "pending"), None)
            if a is None:
                return None
            a["status"] = "approved" if args[0] == "approved" else "rejected"
            self.executed.append((" ".join(sql.split()), args))
            return {"run_id": a["run_id"], "gate": a["gate"]}
        raise AssertionError(f"unexpected fetchrow: {sql}")

    async def fetchval(self, sql, *args):
        self.queries.append(sql)
        s = _norm(sql)
        if "current_stage from runs" in s:
            r = next((r for r in self.runs if r["id"] == args[0]), None)
            return r["current_stage"] if r else None
        if "count(*)" in s:
            return 0
        raise AssertionError(f"unexpected fetchval: {sql}")

    # ── writes ───────────────────────────────────────────────────────────────

    async def execute(self, sql, *args):
        self.executed.append((" ".join(sql.split()), args))
        return "OK"

    @contextlib.asynccontextmanager
    async def acquire(self):
        yield self

    def transaction(self):
        return _NullTx()


class _NullTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class Req:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}


def signed(user: str = "tester") -> Req:
    return Req({mc.SESSION_COOKIE: mc.make_session(user)})


def body_of(resp) -> str:
    return resp.body.decode("utf-8")


def get(route, *args, pool=None, **kw):
    """Call a route coroutine with the fake pool installed for its duration."""
    mc.pool = pool
    try:
        return asyncio.run(route(*args, **kw))
    finally:
        mc.pool = None


# ── row factories ────────────────────────────────────────────────────────────

def run_row(id="feat-20260908-fake", status="waiting_gate", current_stage="00-story.write", **over) -> dict:
    row = {
        "id": id, "status": status, "current_stage": current_stage,
        "created_by": "tester", "created_at": NOW - timedelta(days=2),
        "updated_at": NOW - timedelta(hours=1), "completed_at": None,
        "pipeline_version": "3", "brief": "workflow/briefs/fake.md",
        "product_repo": None, "product_branch": None, "product_working_branch": None,
        "coding_mode": "human",
    }
    row.update(over)
    return row


def exec_row(id, run_id, stage, attempt=1, status="succeeded", started=None, seconds=120,
             model="gpt-5.6-sol", inp=100_000, cached=80_000, out=5_000, error=None,
             runner="ec2", key=None, **over) -> dict:
    started = started or (NOW - timedelta(hours=3))
    finished = None if status == "running" else started + timedelta(seconds=seconds)
    metered = inp is not None
    row = {
        "id": id, "run_id": run_id, "stage": stage, "runner": runner, "attempt": attempt,
        "status": status, "input": None, "output": None, "run_state": None,
        "run_state_version": None, "error": error,
        "error_class": None, "idempotency_key": key or f"{run_id}:{stage}:{attempt}",
        "heartbeat_at": started, "model": model if metered else None,
        "requests": 7 if metered else None,
        "input_tokens": inp, "cached_input_tokens": cached if metered else None,
        "output_tokens": out if metered else None,
        "total_tokens": (inp + out) if metered else None,
        "started_at": started, "finished_at": finished,
    }
    row.update(over)
    return row


def approval_row(id=7, run_id="feat-20260908-fake", gate="story_signoff", status="pending",
                 age_seconds=3 * 3600, payload=None, **over) -> dict:
    row = {
        "id": id, "run_id": run_id, "gate": gate, "status": status, "payload": payload,
        "requested_at": NOW - timedelta(seconds=age_seconds), "decided_at": None,
        "decided_by": None, "decision_note": None, "channel": "cli", "external_ref": None,
        "stage_execution_id": None,
    }
    row.update(over)
    return row


def live_approval(age_seconds, **over) -> dict:
    """Aged against wall-clock time for route-level tests (routes compute `now`)."""
    return approval_row(requested_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds + 30), **over)


def agg_row(key: str, value, model="gpt-5.6-sol", inp=100_000, cached=80_000, outp=5_000, n=1, unmetered=0) -> dict:
    return {key: value, "model": model, "inp": inp, "cached": cached, "outp": outp, "n": n,
            "unmetered": unmetered}


def repo_row(url="https://github.com/org/app", check=None, **over) -> dict:
    """A product_repos row (D27); `check` is stored the way asyncpg returns jsonb: as text."""
    import json
    import product_repos
    row = {"id": product_repos.repo_id(url), "url": url, "name": product_repos.display_name(url),
           "kind": product_repos.kind(url), "default_branch": "main", "is_factory": False,
           "check_result": json.dumps(check) if check is not None else None,
           "checked_at": NOW if check is not None else None, "connected_by": "tester",
           "connected_at": NOW - timedelta(days=1), "last_used_at": None, "archived": False,
           "updated_at": NOW}
    row.update(over)
    return row
