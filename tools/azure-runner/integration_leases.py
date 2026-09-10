"""Real disposable Postgres ownership/crash proof; no Azure or live fleet claims.

Run with the existing asyncpg environment. This script ONLY creates/deletes the
fixed localhost:55432 database lantern_validation_leases; it refuses an existing
database so concurrent tests or retained evidence cannot be destroyed. Password
comes from ignored .venv/integration-db-password and is never emitted.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

import asyncpg
import execution_leases as l
import execution_runtime as runtime

ROOT = Path(__file__).resolve().parent
DATABASE = 'lantern_validation_leases'
RUN = 'feat-20260910-disposable-lease-proof'


async def connect(database=DATABASE):
    return await asyncpg.connect(host='127.0.0.1', port=55432, user='lantern',
        password=(ROOT / '.venv/integration-db-password').read_text().strip(),
        database=database, timeout=10)


async def insert_run(conn, run_id=RUN):
    await conn.execute("INSERT INTO runs(id,brief,pipeline_version,current_stage,created_by) VALUES($1,'disposable proof','test','00-story.research','integration-test')", run_id)


async def child(conn, lease):
    async with l.fenced_transaction(conn, lease):
        execution_id = await conn.fetchval("INSERT INTO stage_executions(run_id,stage,input) VALUES($1,'00-story.research','{}') RETURNING id", lease.run_id)
        return await l.acquire_execution(conn, lease, execution_id)


async def worker(provider_file):
    conn = await connect()
    parent = await l.acquire_run(conn, RUN, 'killed-worker')
    execution = await child(conn, parent)
    await conn.execute("UPDATE stage_executions SET input_tokens=17, error='known diagnostic before death' WHERE id=$1", execution.execution_id)
    await l.begin_effect(conn, execution, 'disposable:publication', 'push', {'revision': 'a'*40})
    # An actual non-transactional local side effect: death occurs before confirming
    # it in Postgres. This tests the protocol, not GitHub/provider integration.
    with Path(provider_file).open('a', encoding='utf-8') as provider:
        provider.write('a'*40 + '\n')
        provider.flush()
        os.fsync(provider.fileno())
    await conn.execute("INSERT INTO events(run_id,actor,type,data) VALUES($1,'integration-test','durable-boundary','{}')", RUN)
    print(json.dumps({'ready': True, 'execution_id': execution.execution_id, 'parent_fence': parent.fence, 'child_fence': execution.fence}), flush=True)
    await asyncio.sleep(3600)


async def rejected(awaitable, kind=l.LeaseLost):
    try:
        await awaitable
    except kind:
        return
    raise AssertionError(f'expected {kind.__name__}')


async def main():
    admin = await connect('lantern_validation')
    made = False
    conn = other = None
    result = {'environment': 'real PostgreSQL localhost:55432 disposable database', 'database': DATABASE}
    try:
        if await admin.fetchval('SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=$1)', DATABASE):
            raise RuntimeError('Disposable lease database already exists; refusing to overwrite')
        await admin.execute('CREATE DATABASE lantern_validation_leases')
        made = True
        conn, other = await connect(), await connect()
        sql = (ROOT / 'schema.sql').read_text(encoding='utf-8')
        start = sql.index('-- Execution ownership/effects:')
        end = sql.index('CREATE TABLE IF NOT EXISTS approvals', start)
        migration = sql[start:end]
        await conn.execute(sql[:start] + sql[end:])
        await insert_run(conn, RUN + '-legacy')
        await conn.execute("UPDATE runs SET status='executing' WHERE id=$1", RUN + '-legacy')
        await conn.execute("INSERT INTO approvals(run_id,gate) VALUES($1,'story_signoff')", RUN + '-legacy')
        before = await conn.fetch('SELECT * FROM approvals')
        started = time.perf_counter()
        async with conn.transaction():
            await conn.execute("SET LOCAL lock_timeout='5s'")
            await conn.execute("SET LOCAL statement_timeout='60s'")
            await conn.execute(migration)
        result['forward_seconds'] = round(time.perf_counter() - started, 4)
        await conn.execute(migration)  # idempotent second application
        legacy = await l.recover_expired(conn, safe_stages=('00-story.research',))
        assert legacy[0]['status'] == 'failed'
        assert await conn.fetch('SELECT * FROM approvals') == before
        result['legacy_and_pending_gates'] = 'held; approvals byte-equivalent'

        await insert_run(conn)
        a, b = await asyncio.gather(l.acquire_run(conn, RUN, 'dispatcher-a'), l.acquire_run(other, RUN, 'dispatcher-b'))
        assert (a is None) != (b is None)
        owner = a or b
        execution = await child(conn, owner)
        sibling = await child(conn, owner)
        await l.renew(other, owner)
        await l.renew(other, execution)
        await l.renew(other, sibling)
        effect = await l.begin_effect(conn, execution, 'disposable:once', 'push', {'revision': 'b'*40})
        assert effect.created
        duplicate = await l.begin_effect(other, sibling, 'disposable:once', 'push', {'revision': 'b'*40})
        assert not duplicate.created and duplicate.status == 'intended'
        await rejected(l.begin_effect(other, sibling, 'disposable:once', 'push', {'revision':'c'*40}), l.EffectConflict)
        await rejected(l.confirm_effect(other, sibling, 'disposable:once', 'ref'), l.EffectConflict)
        await l.confirm_effect(conn, execution, 'disposable:once', 'ref')
        result['two_dispatchers_parallel_children_duplicate_intents'] = 'pass'

        # Actual renewable lease: dedicated connection, multiple heartbeats, stop
        # before completing, and a database-side expiry cancels local work.
        async with l.lease_guard(connect, owner, ttl=2, interval=.02) as guard:
            expiry = await conn.fetchval('SELECT lease_expires_at FROM runs WHERE id=$1', RUN)
            async with asyncio.timeout(1.5):
                while await conn.fetchval('SELECT lease_expires_at FROM runs WHERE id=$1', RUN) <= expiry:
                    await asyncio.sleep(.01)
            await guard.stop()
        try:
            async with l.lease_guard(connect, sibling, ttl=2, interval=.02):
                await conn.execute("UPDATE stage_executions SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=$1", sibling.execution_id)
                await asyncio.sleep(1)
        except l.LeaseLost:
            pass
        else:
            raise AssertionError('real heartbeat did not cancel expired worker')
        result['dedicated_connection_renewal_and_loss_cancellation'] = 'pass'

        # The second connection cannot advance while a fenced mutation owns the row.
        async with l.fenced_transaction(conn, owner):
            attempt = asyncio.create_task(l.release(other, owner, 'running'))
            await asyncio.sleep(.05)
            assert not attempt.done()
        await attempt
        await rejected(l.renew(conn, execution))
        newer = await l.acquire_run(conn, RUN, 'new-owner')
        assert newer.fence > owner.fence
        await rejected(l.renew(other, owner))
        await l.release(conn, newer, 'running')
        await conn.execute("UPDATE stage_executions SET status='failed' WHERE run_id=$1", RUN)
        result['transaction_lock_and_stale_parent_child'] = 'pass'

        with tempfile.TemporaryDirectory(prefix='lantern-lease-provider-') as temp:
            provider_file = Path(temp) / 'provider-effect.txt'
            process = await asyncio.create_subprocess_exec(sys.executable, __file__, '--worker', str(provider_file), stdout=asyncio.subprocess.PIPE)
            try:
                ready = json.loads(await asyncio.wait_for(process.stdout.readline(), 20))
                assert ready['ready']
            finally:
                if process.returncode is None:
                    process.kill()
                await process.wait()
            observed_provider_lines = provider_file.read_text().splitlines()
            assert observed_provider_lines == ['a'*40]
        # Deterministic server-time expiry, not wall-clock flakiness.
        await conn.execute("UPDATE runs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=$1", RUN)
        recovered = await l.recover_expired(other, safe_stages=('00-story.research',))
        assert recovered[0]['status'] == 'failed' and recovered[0]['ambiguous_effects']
        row = await conn.fetchrow('SELECT * FROM stage_executions WHERE id=$1', ready['execution_id'])
        assert row['input_tokens'] == 17 and 'known diagnostic before death' in row['error'] and 'unknown tail usage' in row['error']
        assert await conn.fetchval("SELECT count(*) FROM events WHERE type='durable-boundary'") == 1
        assert await conn.fetchval("SELECT status FROM execution_effects WHERE operation_key='disposable:publication'") == 'uncertain'
        stale = l.Lease(RUN, 'killed-worker', ready['child_fence'], ready['execution_id'], ready['parent_fence'])
        await rejected(l.confirm_effect(conn, stale, 'disposable:publication', 'ref'))
        assert await l.acquire_run(conn, RUN, 'restart') is None
        # Explicit test operator retry; no approval row is manufactured or changed.
        await conn.execute("UPDATE runs SET status='running' WHERE id=$1", RUN)
        restarted = await l.acquire_run(conn, RUN, 'restart')
        retry = await child(conn, restarted)
        duplicate = await l.begin_effect(conn, retry, 'disposable:publication', 'push', {'revision':'a'*40})
        assert not duplicate.created and duplicate.status == 'uncertain'
        await l.reconcile_effect(conn, retry, 'disposable:publication', {'revision':'a'*40}, 'local-provider-effect', {'observed_revision':observed_provider_lines[0], 'provider':'disposable local file'})
        assert await conn.fetchval("SELECT count(*) FROM execution_effects WHERE operation_key='disposable:publication'") == 1
        assert await conn.fetch('SELECT * FROM approvals') == before
        result['process_kill_restart_usage_diagnostics_uncertain_hold_reconcile'] = 'pass'

        # Child expiry must fence a live dispatcher and all sibling outputs.
        await conn.execute("UPDATE stage_executions SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=$1", retry.execution_id)
        assert (await l.recover_expired(other))[0]['status'] == 'failed'
        await rejected(l.renew(conn, restarted))
        result['expired_child_holds_parent'] = 'pass'

        # Exercise the actual runtime wrapper against real rows: a failed substage
        # closes itself even when the dispatcher catches it and continues review.
        runtime_run = RUN + '-runtime'
        await insert_run(conn, runtime_run)
        with patch.dict(os.environ, {'LANTERN_EXECUTION_LEASES':'1'}):
            async with runtime.run_scope(conn, connect, runtime_run):
                import builders
                backend_ids = []

                async def parallel_child(child_conn, run_id, stage, runner):
                    backend_ids.append(await child_conn.fetchval('SELECT pg_backend_pid()'))
                    async with runtime.stage_scope(child_conn, connect, run_id, stage, runner) as attempt:
                        await asyncio.sleep(.02)
                        async with runtime.mutation(child_conn, stage=True, finish=True):
                            await child_conn.execute("UPDATE stage_executions SET status='succeeded' WHERE id=$1", attempt[2])

                await builders.fan_out(conn, runtime_run, 'host', ['one','two'], parallel_child, 2, connect=connect)
                assert len(set(backend_ids)) == 2
                assert await conn.fetchval("SELECT count(*) FROM stage_executions WHERE run_id=$1 AND status='succeeded'", runtime_run) == 2
                result['runtime_parallel_builders_distinct_postgres_connections'] = 'pass'
                try:
                    async with runtime.stage_scope(conn, connect, runtime_run, '03-coding.review', 'host') as attempt:
                        failed_id = attempt[2]
                        raise RuntimeError('controlled review failure')
                except RuntimeError as error:
                    assert str(error) == 'controlled review failure'
                failed = await conn.fetchrow('SELECT status,lease_owner,error FROM stage_executions WHERE id=$1', failed_id)
                assert failed['status'] == 'failed' and failed['lease_owner'] is None
                assert 'controlled review failure' in failed['error']
                try:
                    async with runtime.stage_scope(conn, connect, runtime_run, '03-coding.publish', 'host') as attempt:
                        completed_id = attempt[2]
                        completed_lease = runtime.STAGE.get().lease
                        async with runtime.mutation(conn, stage=True, finish=True):
                            await conn.execute("UPDATE stage_executions SET status='succeeded' WHERE id=$1", completed_id)
                        raise RuntimeError('post-completion bookkeeping failure')
                except RuntimeError as error:
                    assert str(error) == 'post-completion bookkeeping failure'
                assert await conn.fetchval('SELECT status FROM stage_executions WHERE id=$1', completed_id) == 'succeeded'
                async with runtime.mutation(conn, finish=True):
                    await conn.execute("UPDATE runs SET status='failed' WHERE id=$1", runtime_run)
            await rejected(runtime.fail_stage(conn, completed_lease, RuntimeError('stale late failure')))
        result['runtime_failure_finalization_and_completed_child_preservation'] = 'pass'

        started = time.perf_counter()
        async with conn.transaction():
            await conn.execute("SET LOCAL lock_timeout='5s'")
            await conn.execute("SET LOCAL statement_timeout='60s'")
            await conn.execute("DROP TABLE execution_effects; DROP INDEX idx_stage_active_lease; DROP INDEX idx_runs_active_lease; ALTER TABLE stage_executions DROP COLUMN lease_owner, DROP COLUMN lease_expires_at, DROP COLUMN lease_fence; ALTER TABLE runs DROP COLUMN lease_owner, DROP COLUMN lease_expires_at, DROP COLUMN lease_fence")
        result['rollback_seconds'] = round(time.perf_counter() - started, 4)
        assert await conn.fetch('SELECT * FROM approvals') == before
        assert await conn.fetchval('SELECT count(*) FROM runs') == 3
        result['rollback_preserves_existing_rows'] = 'pass'
        result['server_version'] = await conn.fetchval('SHOW server_version')
        print(json.dumps(result, indent=2))
    finally:
        for connection in (conn, other):
            if connection:
                await connection.close()
        if made:
            await admin.execute('DROP DATABASE lantern_validation_leases')
        await admin.close()


if __name__ == '__main__':
    asyncio.run(worker(sys.argv[2]) if len(sys.argv) == 3 and sys.argv[1] == '--worker' else main())
