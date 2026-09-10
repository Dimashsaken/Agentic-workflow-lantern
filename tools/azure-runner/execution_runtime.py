"""Opt-in dispatcher fencing, shared by both existing executor implementations.

The outer run owns advancement; each nested stage owns its own completion.
Raw attempt files remain diagnostics. Only fenced host records may authorize work.
"""
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import os
from uuid import uuid4

import execution_leases as leases


RUN = ContextVar("lantern_run_ownership", default=None)
STAGE = ContextVar("lantern_stage_ownership", default=None)
OWNER = "dispatcher:" + uuid4().hex
CLAIMS = {}


def enabled():
    return os.environ.get("LANTERN_EXECUTION_LEASES") == "1"


def ttl():
    return float(os.environ.get("LANTERN_LEASE_TTL", "120"))


@dataclass
class Ownership:
    lease: leases.Lease
    guard: object


async def claim(conn, run_id):
    lease = await leases.acquire_run(conn, run_id, OWNER, ttl())
    if lease:
        CLAIMS[run_id] = lease
        return run_id
    return None


@asynccontextmanager
async def run_scope(conn, connect, run_id):
    if not enabled():
        yield
        return
    lease = CLAIMS.pop(run_id, None)
    if lease is None:
        lease = await leases.acquire_run(conn, run_id, OWNER, ttl())
    if lease is None:
        raise leases.LeaseLost("run was not claimed by this dispatcher")
    async with leases.lease_guard(connect, lease, ttl=ttl(), interval=min(20, ttl()/3)) as guard:
        token = RUN.set(Ownership(lease, guard))
        try:
            yield
        finally:
            RUN.reset(token)


@asynccontextmanager
async def mutation(conn, *, stage=False, finish=False):
    ownership = STAGE.get() if stage else RUN.get()
    if not enabled():
        yield
        return
    if ownership is None:
        raise leases.LeaseLost("mutation has no bound ownership")
    if finish:
        await ownership.guard.stop()
    async with leases.fenced_transaction(conn, ownership.lease):
        yield
        if finish:
            if stage:
                await conn.execute("UPDATE stage_executions SET lease_owner=NULL, lease_expires_at=NULL WHERE id=$1", ownership.lease.execution_id)
            else:
                await conn.execute("UPDATE runs SET lease_owner=NULL, lease_expires_at=NULL WHERE id=$1", ownership.lease.run_id)


async def fail_stage(conn, lease, error):
    """Close only this still-owned child; completed rows remain immutable.

    Checking the parent first prevents a delayed failure handler from changing a
    replacement execution. A completed child may be followed by an unrelated
    bookkeeping failure; that does not undo its recorded completion.
    """
    from factory import classify_error, redact

    parent = leases.Lease(lease.run_id, lease.owner, lease.parent_fence)
    async with leases.fenced_transaction(conn, parent):
        row = await conn.fetchrow("SELECT status FROM stage_executions WHERE id=$1 FOR UPDATE", lease.execution_id)
        if row is None or row['status'] != 'running':
            return
        await leases.assert_current(conn, lease)
        await conn.execute("""UPDATE stage_executions SET status='failed',
            error=concat_ws(E'\\n',NULLIF(error,''),$2::text), error_class=$3,
            finished_at=clock_timestamp(), lease_owner=NULL, lease_expires_at=NULL
            WHERE id=$1 AND status='running'""", lease.execution_id,
            redact(str(error) or type(error).__name__)[:4000], classify_error(error))


@asynccontextmanager
async def stage_scope(conn, connect, run_id, stage, runner):
    parent = RUN.get()
    if not enabled():
        yield None
        return
    if parent is None or parent.lease.run_id != run_id:
        raise leases.LeaseLost("stage has no parent run lease")
    async with leases.fenced_transaction(conn, parent.lease):
        attempt = await conn.fetchval("SELECT coalesce(max(attempt),0)+1 FROM stage_executions WHERE run_id=$1 AND stage=$2", run_id, stage)
        key = f"{run_id}:{stage}:{attempt}"
        execution_id = await conn.fetchval("""INSERT INTO stage_executions
            (run_id,stage,runner,attempt,status,idempotency_key,heartbeat_at)
            VALUES($1,$2,$3,$4,'running',$5,clock_timestamp()) RETURNING id""",
            run_id, stage, runner, attempt, key)
        lease = await leases.acquire_execution(conn, parent.lease, execution_id, ttl())
    async with leases.lease_guard(connect, lease, ttl=ttl(), interval=min(20, ttl()/3)) as guard:
        token = STAGE.set(Ownership(lease, guard))
        try:
            yield attempt, key, execution_id
        except BaseException as error:
            # Stop the child heartbeat before terminal writes. Parent ownership is
            # checked again in the transaction; stale failure handlers cannot write.
            await guard.stop()
            await fail_stage(conn, lease, error)
            raise
        finally:
            STAGE.reset(token)
