"""Host-only PostgreSQL ownership and publication ledger.

Use a dedicated asyncpg connection for renewal. Wrap each database mutation in
``fenced_transaction(conn, lease)``; it locks run then child in that order. External
effects require begin_effect BEFORE invocation and confirm_effect AFTER success.
Only ``Effect.created`` authorizes invocation: a duplicate intended/uncertain
effect must be reconciled against its provider, never replayed automatically.
No function resumes SDK state or changes human approvals.
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass
import asyncio
import hashlib
import json
import math


class LeaseLost(RuntimeError):
    """Ownership expired, changed, or no longer has the expected active status."""


class EffectConflict(RuntimeError):
    """An operation key was reused for a different request or owner."""


@dataclass(frozen=True)
class Lease:
    run_id: str
    owner: str
    fence: int
    execution_id: int | None = None
    parent_fence: int | None = None


@dataclass(frozen=True)
class Effect:
    created: bool
    status: str
    external_ref: str | None
    result: object


def request_hash(request) -> str:
    """Stable JSON request hash; callers must omit credentials from requests."""
    encoded = json.dumps(request, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _ttl(ttl):
    if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not math.isfinite(ttl) or ttl <= 0:
        raise ValueError("lease TTL must be a positive finite number")
    return float(ttl)


async def acquire_run(conn, run_id, owner, ttl=120):
    """Claim only queued work. Expired/legacy executing rows require recovery first."""
    if not owner:
        raise ValueError("lease owner must be nonempty")
    fence = await conn.fetchval("""
        UPDATE runs SET status='executing', lease_owner=$2,
          lease_fence=lease_fence+1,
          lease_expires_at=clock_timestamp()+$3 * interval '1 second',
          updated_at=clock_timestamp()
        WHERE id=$1 AND status='running'
          AND (lease_expires_at IS NULL OR lease_expires_at <= clock_timestamp())
        RETURNING lease_fence
    """, run_id, owner, _ttl(ttl))
    return Lease(run_id, owner, fence) if fence is not None else None


async def assert_current(conn, lease):
    """Check AND lock ownership inside an existing transaction (not an autocommit check)."""
    if not conn.is_in_transaction():
        raise RuntimeError("lease assertion requires a transaction")
    row = await conn.fetchrow("SELECT * FROM runs WHERE id=$1 FOR UPDATE", lease.run_id)
    expected = lease.parent_fence if lease.execution_id is not None else lease.fence
    now = await conn.fetchval("SELECT clock_timestamp()")
    if (not row or row['status'] != 'executing' or row['lease_owner'] != lease.owner
            or row['lease_fence'] != expected or row['lease_expires_at'] is None
            or row['lease_expires_at'] <= now):
        raise LeaseLost("run lease is no longer current")
    if lease.execution_id is not None:
        child = await conn.fetchrow("SELECT * FROM stage_executions WHERE id=$1 FOR UPDATE", lease.execution_id)
        now = await conn.fetchval("SELECT clock_timestamp()")
        metadata = json.loads(child['input'] or '{}') if child and isinstance(child['input'], str) else (child['input'] or {} if child else {})
        if (not child or child['run_id'] != lease.run_id or child['status'] != 'running'
                or child['lease_owner'] != lease.owner or child['lease_fence'] != lease.fence
                or child['lease_expires_at'] is None or child['lease_expires_at'] <= now
                or not isinstance(metadata, dict) or metadata.get('parent_run_fence') != lease.parent_fence):
            raise LeaseLost("execution lease is no longer current")


@asynccontextmanager
async def fenced_transaction(conn, lease):
    """Serialize a host mutation with recovery/takeover; never await external I/O here."""
    async with conn.transaction():
        await assert_current(conn, lease)
        yield


async def acquire_execution(conn, parent, execution_id, ttl=120):
    """Attach a newly inserted running execution to the active dispatcher fence."""
    if parent.execution_id is not None:
        raise ValueError("parent must be a run lease")
    async with fenced_transaction(conn, parent):
        fence = await conn.fetchval("""
            UPDATE stage_executions SET lease_owner=$2, lease_fence=lease_fence+1,
              lease_expires_at=clock_timestamp()+$3 * interval '1 second',
              heartbeat_at=clock_timestamp(),
              input=COALESCE(input, '{}'::jsonb) || jsonb_build_object('parent_run_fence', $4::bigint)
            WHERE id=$1 AND run_id=$5 AND status='running' AND lease_owner IS NULL
              AND lease_fence=0 RETURNING lease_fence
        """, execution_id, parent.owner, _ttl(ttl), parent.fence, parent.run_id)
        if fence is None:
            raise LeaseLost("execution is not a fresh running attempt")
    return Lease(parent.run_id, parent.owner, fence, execution_id, parent.fence)


async def renew(conn, lease, ttl=120):
    async with fenced_transaction(conn, lease):
        if lease.execution_id is None:
            await conn.execute("UPDATE runs SET lease_expires_at=clock_timestamp()+$2 * interval '1 second' WHERE id=$1", lease.run_id, _ttl(ttl))
        else:
            await conn.execute("UPDATE stage_executions SET lease_expires_at=clock_timestamp()+$2 * interval '1 second', heartbeat_at=clock_timestamp() WHERE id=$1", lease.execution_id, _ttl(ttl))


@asynccontextmanager
async def lease_guard(connect, lease, ttl=120, interval=20):
    """Renew via dedicated asyncpg connection; cancel guarded task on lease loss.

    ``connect`` is an async zero-argument callable creating an independent connection.
    Connection/renew failures fail closed. Exit joins renewal and closes connection.
    Yields a handle with idempotent async ``stop()``. Stop renewal before the final
    fenced completion transaction; stop itself neither releases nor extends a lease.
    """
    if _ttl(interval) >= _ttl(ttl):
        raise ValueError("renewal interval must be shorter than TTL")
    parent = asyncio.current_task()
    failure = []
    ready = asyncio.Event()

    async def heartbeat():
        conn = None
        try:
            async with asyncio.timeout(ttl - interval):
                conn = await connect()
            while True:
                async with asyncio.timeout(ttl - interval):
                    await renew(conn, lease, ttl)
                ready.set()
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            failure.append(LeaseLost("lease heartbeat failed; work cancelled"))
            ready.set()
            parent.cancel()
        finally:
            if conn is not None:
                await conn.close()

    task = asyncio.create_task(heartbeat())

    class Guard:
        async def stop(self):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            if failure:
                raise failure[0]

    guard = Guard()
    try:
        await ready.wait()
        if failure:
            raise failure[0]
        yield guard
    except asyncio.CancelledError:
        if failure:
            raise failure[0] from None
        raise
    finally:
        await guard.stop()


async def release(conn, lease, status):
    """Finish leased work; preserve its fence so old handles cannot become valid."""
    allowed = {'running', 'waiting_gate', 'failed', 'done', 'cancelled'} if lease.execution_id is None else {'succeeded', 'failed', 'waiting_gate', 'skipped'}
    if status not in allowed:
        raise ValueError("invalid lease release status")
    async with fenced_transaction(conn, lease):
        if lease.execution_id is None:
            await conn.execute("UPDATE runs SET status=$2, lease_owner=NULL, lease_expires_at=NULL, updated_at=clock_timestamp() WHERE id=$1", lease.run_id, status)
        else:
            await conn.execute("UPDATE stage_executions SET status=$2, lease_owner=NULL, lease_expires_at=NULL, finished_at=clock_timestamp() WHERE id=$1", lease.execution_id, status)


def _effect(row, created):
    result = row['result']
    return Effect(created, row['status'], row['external_ref'], json.loads(result) if isinstance(result, str) else result)


async def begin_effect(conn, lease, operation_key, kind, request):
    if lease.execution_id is None:
        raise ValueError("effects require an execution lease")
    if not operation_key or not kind:
        raise ValueError("operation key and kind must be nonempty")
    digest = request_hash(request)
    async with fenced_transaction(conn, lease):
        row = await conn.fetchrow("""
          INSERT INTO execution_effects(operation_key, run_id, stage_execution_id,
            lease_fence, kind, request_sha256, status)
          VALUES($1,$2,$3,$4,$5,$6,'intended') ON CONFLICT DO NOTHING RETURNING *
        """, operation_key, lease.run_id, lease.execution_id, lease.fence, kind, digest)
        created = row is not None
        if not created:
            row = await conn.fetchrow("SELECT * FROM execution_effects WHERE operation_key=$1 FOR UPDATE", operation_key)
        if row['run_id'] != lease.run_id or row['kind'] != kind or row['request_sha256'] != digest:
            raise EffectConflict("operation key already identifies a different request")
        return _effect(row, created)


async def _finish_effect(conn, lease, operation_key, status, external_ref, result, reconcile_hash=None):
    if lease.execution_id is None:
        raise ValueError("effects require an execution lease")
    async with fenced_transaction(conn, lease):
        row = await conn.fetchrow("SELECT * FROM execution_effects WHERE operation_key=$1 FOR UPDATE", operation_key)
        if not row or row['run_id'] != lease.run_id:
            raise EffectConflict("operation does not belong to this run")
        if reconcile_hash is None:
            if row['stage_execution_id'] != lease.execution_id or row['lease_fence'] != lease.fence:
                raise EffectConflict("operation belongs to a different execution")
        elif row['request_sha256'] != reconcile_hash:
            raise EffectConflict("reconciliation request differs from recorded intent")
        if row['status'] == 'confirmed':
            if status != 'confirmed' or row['external_ref'] != external_ref:
                raise EffectConflict("confirmed operation cannot be changed")
            return _effect(row, False)
        if row['status'] == 'uncertain' and reconcile_hash is None and status == 'confirmed':
            raise EffectConflict("uncertain operation requires explicit reconciliation")
        updated = await conn.fetchrow("""UPDATE execution_effects SET status=$2,
          external_ref=$3, result=$4::jsonb, updated_at=clock_timestamp()
          WHERE operation_key=$1 RETURNING *""", operation_key, status, external_ref,
          json.dumps(result, allow_nan=False) if result is not None else None)
        return _effect(updated, False)


async def confirm_effect(conn, lease, operation_key, external_ref, result=None):
    return await _finish_effect(conn, lease, operation_key, 'confirmed', external_ref, result)


async def mark_effect_uncertain(conn, lease, operation_key, result=None):
    return await _finish_effect(conn, lease, operation_key, 'uncertain', None, result)


async def reconcile_effect(conn, lease, operation_key, request, external_ref, result):
    """Host must first inspect provider state; this records that explicit observation.

    This does not authorize repeating an effect. Unknown outcomes remain uncertain.
    """
    if not external_ref or not result:
        raise ValueError("reconciliation requires observed external reference and evidence")
    return await _finish_effect(conn, lease, operation_key, 'confirmed', external_ref, result, request_hash(request))


async def recover_expired(conn, safe_stages=()):
    """Hold expired/legacy attempts; optionally requeue explicitly read-only stages.

    Never replay ambiguous effects or serialized SDK state. Existing diagnostics,
    usage and approval rows are untouched. Active parent + expired child also holds
    the parent, fencing its sibling outputs until a person chooses a fresh attempt.
    """
    recovered = []
    async with conn.transaction():
        runs = await conn.fetch("""SELECT * FROM runs r WHERE status='executing' AND
          (lease_expires_at IS NULL OR lease_expires_at <= clock_timestamp() OR EXISTS
            (SELECT 1 FROM stage_executions e WHERE e.run_id=r.id AND e.status='running'
             AND (e.lease_expires_at IS NULL OR e.lease_expires_at<=clock_timestamp())))
          ORDER BY id FOR UPDATE SKIP LOCKED""")
        for run in runs:
            children = await conn.fetch("SELECT id FROM stage_executions WHERE run_id=$1 AND status='running' ORDER BY id FOR UPDATE", run['id'])
            ambiguous = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM execution_effects WHERE run_id=$1 AND status<>'confirmed')", run['id'])
            # A never-leased legacy process is not known safe even for read-only work.
            retry = run['current_stage'] in safe_stages and not ambiguous and run['lease_owner'] is not None
            status = 'running' if retry else 'failed'
            await conn.execute("""UPDATE execution_effects SET status='uncertain',
              updated_at=clock_timestamp() WHERE run_id=$1 AND status='intended'""", run['id'])
            await conn.execute("""UPDATE stage_executions SET status='failed',
              error=concat_ws(E'\\n', NULLIF(error,''), 'Execution interrupted: lease lost; unknown tail usage; SDK replay disabled'),
              error_class='terminal', finished_at=clock_timestamp(),
              lease_owner=NULL, lease_expires_at=NULL
              WHERE run_id=$1 AND status='running'""", run['id'])
            await conn.execute("""UPDATE runs SET status=$2, lease_owner=NULL,
              lease_expires_at=NULL, lease_fence=lease_fence+1,
              updated_at=clock_timestamp() WHERE id=$1""", run['id'], status)
            summary = {'run_id': run['id'], 'status': status, 'ambiguous_effects': ambiguous,
                       'execution_ids': [row['id'] for row in children], 'sdk_replay': False}
            await conn.execute("INSERT INTO events(run_id, actor, type, data) VALUES($1,'orchestrator','execution_recovered',$2::jsonb)", run['id'], json.dumps(summary))
            recovered.append(summary)
    return recovered
