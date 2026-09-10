"""Maintenance authority controls; opt-in SQL tests use a new disposable DB only."""
import asyncio
from datetime import datetime, timezone
import json
import os
import threading
import subprocess
import tempfile
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import execution_leases as leases
import maintenance_runtime as maintenance

REQUEST = {'version': 3, 'run_id': 'test-maintenance', 'repo': 'https://github.com/test/product',
           'base': 'main', 'branch': 'feat/test', 'work': 'feat/test',
           'repository_id': 123, 'head_sha': 'a'*40, 'base_sha': 'b'*40, 'expected_remote_sha': None}
RUN = {'id': REQUEST['run_id'], 'coding_mode': 'auto', 'status': 'running',
       'current_stage': '04-qa-dev', 'lease_owner': None, 'lease_fence': 7,
       'product_repo': REQUEST['repo'], 'product_branch': 'main', 'product_working_branch': 'feat/test'}
APPROVAL = {'id': 1, 'status': 'approved', 'decided_by': 'human-test-fixture',
            'decided_at': datetime.now(timezone.utc), 'payload': {'publication_request': REQUEST, 'pr_number': 5, 'pr_url': 'https://github.com/test/product/pull/5'}}


class Binding(unittest.IsolatedAsyncioTestCase):
    def connection(self, approval=None, rework=None):
        conn = AsyncMock()
        conn.fetchrow.side_effect = [APPROVAL if approval is None else approval, rework]
        conn.fetchval.return_value = False
        return conn

    async def test_valid_binds_decision_and_target(self):
        result = await maintenance.binding(self.connection(), RUN)
        self.assertEqual(result['approval_id'], 1)
        self.assertEqual(result['run_fence'], 7)
        self.assertEqual(result['publication_request'], REQUEST)

    async def test_newer_decisions_and_legacy_approval_hold(self):
        for change in ({'status': 'pending'}, {'status': 'rejected'}, {'decided_by': None},
                       {'payload': {}}, {'payload': {'publication_request': {**REQUEST, 'version': 2}}}):
            with self.subTest(change=change), self.assertRaises(leases.LeaseLost):
                await maintenance.binding(self.connection({**APPROVAL, **change}), RUN)

    async def test_target_or_position_changed(self):
        for change in ({'coding_mode': 'human'}, {'status': 'executing'}, {'lease_owner': 'dispatcher'},
                       {'current_stage': '03-coding'}, {'product_working_branch': 'feat/other'}):
            with self.subTest(change=change), self.assertRaises(leases.LeaseLost):
                await maintenance.binding(self.connection(), {**RUN, **change})

    async def test_rework_after_approval_holds(self):
        with self.assertRaises(leases.LeaseLost):
            await maintenance.binding(self.connection(rework={'id': 3, 'at': APPROVAL['decided_at']}), RUN)

    async def test_later_pending_gate_holds(self):
        conn = self.connection()
        conn.fetchval.return_value = True
        with self.assertRaises(leases.LeaseLost):
            await maintenance.binding(conn, RUN)

    async def test_direct_entry_default_off_even_with_force(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, 'disabled'):
            await maintenance.babysit(AsyncMock(), 'anything', 'host', force=True)

    async def test_cancelled_thread_is_joined_and_late_worker_refused(self):
        from isolated_tools import CURRENT_CANCELLATION, IsolationError
        started, stopped = threading.Event(), threading.Event()
        def work():
            cancellation = CURRENT_CANCELLATION.get()
            class Worker:
                def stop(self):
                    stopped.set()
            cancellation.register(Worker())
            started.set()
            if not stopped.wait(5):
                raise AssertionError('worker never cancelled')
            with self.assertRaises(IsolationError):
                cancellation.register(Worker())
            return 'joined'
        task = asyncio.create_task(maintenance.joined_thread(work))
        await asyncio.to_thread(started.wait, 5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(stopped.is_set())


@unittest.skipUnless(os.environ.get('LANTERN_TEST_MAINTENANCE_DB') == '1', 'opt-in disposable PostgreSQL maintenance proof')
class Postgres(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncpg
        self.database = 'lantern_maintenance_' + uuid4().hex
        self.params = {'host': '127.0.0.1', 'port': 55432, 'user': 'lantern',
                       'password': Path(os.environ.get('LANTERN_TEST_DB_PASSWORD_FILE', str(Path(__file__).parent / '.venv/integration-db-password'))).read_text().strip(), 'timeout': 10}
        self.admin = await asyncpg.connect(**self.params, database='lantern_validation')
        await self.admin.execute('CREATE DATABASE ' + self.database)
        self.conn = await asyncpg.connect(**self.params, database=self.database)
        self.other = await asyncpg.connect(**self.params, database=self.database)
        await self.conn.execute((Path(__file__).with_name('schema.sql')).read_text())
        await self.conn.execute("INSERT INTO runs(id,brief,pipeline_version,current_stage,created_by,coding_mode,product_repo,product_branch,product_working_branch) VALUES($1,'disposable maintenance proof','test','04-qa-dev','test','auto',$2,'main','feat/test')", REQUEST['run_id'], REQUEST['repo'])
        await self.conn.execute("INSERT INTO approvals(run_id,gate,status,payload,decided_at,decided_by) VALUES($1,'code_complete','approved',$2::jsonb,clock_timestamp(),'human-test-fixture')", REQUEST['run_id'], json.dumps(APPROVAL['payload']))
        self.before = await self.conn.fetch('SELECT * FROM approvals')
        self.run_before = dict(await self.conn.fetchrow('SELECT * FROM runs'))

    async def asyncTearDown(self):
        await self.conn.close()
        await self.other.close()
        await self.admin.execute('DROP DATABASE ' + self.database)
        await self.admin.close()

    async def claim(self, conn=None, owner='maintenance-a'):
        return await maintenance.acquire(conn or self.conn, REQUEST['run_id'], owner)

    async def test_competing_maintenance_and_dispatch_serialize(self):
        values = await asyncio.gather(self.claim(), self.claim(self.other, 'maintenance-b'), return_exceptions=True)
        self.assertEqual(sum(isinstance(x, leases.Lease) for x in values), 1)
        self.assertIsNone(await leases.acquire_run(self.other, REQUEST['run_id'], 'dispatcher'))
        self.assertEqual(await self.conn.fetch('SELECT * FROM approvals'), self.before)
        self.assertEqual(dict(await self.conn.fetchrow('SELECT * FROM runs')), self.run_before)

    async def test_dispatch_winner_blocks_maintenance(self):
        lease = await leases.acquire_run(self.conn, REQUEST['run_id'], 'dispatcher')
        self.assertIsNotNone(lease)
        with self.assertRaises(leases.LeaseLost):
            await self.claim(self.other)

    async def test_legacy_claim_waits_then_observes_inserted_maintenance(self):
        async with self.conn.transaction():
            await self.conn.fetchrow('SELECT id FROM runs WHERE id=$1 FOR UPDATE', REQUEST['run_id'])
            pending = asyncio.create_task(maintenance.legacy_claim(self.other, REQUEST['run_id']))
            for _ in range(100):
                wait = await self.conn.fetchval('SELECT wait_event_type FROM pg_stat_activity WHERE pid=$1', self.other.get_server_pid())
                if wait == 'Lock':
                    break
                await asyncio.sleep(.01)
            else:
                self.fail('legacy claimant did not block on shared run lock')
            await self.claim()
        self.assertEqual(await pending, 'UPDATE 0')
        self.assertEqual(await self.conn.fetchval('SELECT status FROM runs WHERE id=$1', REQUEST['run_id']), 'running')

    async def test_renewal_expiry_recovery_stale_write(self):
        lease = await self.claim()
        await leases.renew(self.other, lease)
        await leases.begin_effect(self.conn, lease, 'effect', 'branch', {'revision': 'a'*40})
        await self.conn.execute("UPDATE stage_executions SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=$1", lease.execution_id)
        with self.assertRaises(leases.LeaseLost):
            await self.claim(self.other)
        self.assertEqual(await maintenance.recover(self.other), [lease.execution_id])
        with self.assertRaises(leases.LeaseLost):
            await leases.confirm_effect(self.conn, lease, 'effect', 'ref')
        self.assertEqual(await self.conn.fetchval("SELECT status FROM execution_effects WHERE operation_key='effect'"), 'uncertain')
        self.assertEqual(await self.conn.fetch('SELECT * FROM approvals'), self.before)
        self.assertEqual(dict(await self.conn.fetchrow('SELECT * FROM runs')), self.run_before)

    async def test_changed_approval_cancels_without_run_rewrite(self):
        lease = await self.claim()
        await self.other.execute("UPDATE approvals SET decision_note='changed fixture decision'")
        with self.assertRaises(leases.LeaseLost):
            await leases.renew(self.conn, lease)
        changed = await self.conn.fetch('SELECT * FROM approvals')
        self.assertEqual(await maintenance.recover(self.conn), [lease.execution_id])
        self.assertEqual(await self.conn.fetch('SELECT * FROM approvals'), changed)
        self.assertEqual(dict(await self.conn.fetchrow('SELECT * FROM runs')), self.run_before)

    async def test_normal_finish_preserves_run_and_gate(self):
        lease = await self.claim()
        await maintenance.finish(self.conn, lease, {'outcome': 'up_to_date'})
        with self.assertRaises(leases.LeaseLost):
            await maintenance.finish(self.conn, lease, {'outcome': 'updated'})
        self.assertEqual(await self.conn.fetch('SELECT * FROM approvals'), self.before)
        self.assertEqual(dict(await self.conn.fetchrow('SELECT * FROM runs')), self.run_before)
        self.assertIsNotNone(await leases.acquire_run(self.other, REQUEST['run_id'], 'dispatcher'))

    @unittest.skipUnless(os.environ.get('LANTERN_TEST_MAINTENANCE_DOCKER') == '1', 'opt-in actual Docker/Git maintenance pass')
    async def test_actual_trial_immutable_regate_and_conditional_local_push(self):
        def git(*args, cwd=None):
            return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, timeout=30)
        with tempfile.TemporaryDirectory(prefix='lantern-maintenance-proof-') as temporary:
            root = Path(temporary)
            work, mirror = root/'work', root/'mirror.git'
            def checked(*args, cwd=work):
                result = git(*args, cwd=cwd)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout.strip()
            checked('init', '-q', '-b', 'main', str(work), cwd=root)
            checked('config', 'user.name', 'Disposable Test')
            checked('config', 'user.email', 'fixture@example.invalid')
            (work/'lantern.toml').write_text('[quality]\ntest = "python3 -c \'print(123)\'"\n')
            checked('add', '.')
            checked('commit', '-qm', 'initial')
            original_base = checked('rev-parse', 'HEAD')
            checked('checkout', '-qb', 'feat/test')
            (work/'feature.txt').write_text('feature')
            checked('add', '.')
            checked('commit', '-qm', 'feature')
            approved_head = checked('rev-parse', 'HEAD')
            checked('checkout', '-q', 'main')
            (work/'base.txt').write_text('new base')
            checked('add', '.')
            checked('commit', '-qm', 'base advances')
            new_base = checked('rev-parse', 'HEAD')
            checked('clone', '--bare', '--no-hardlinks', str(work), str(mirror), cwd=root)
            request = {**REQUEST, 'head_sha': approved_head, 'base_sha': original_base}
            payload = {**APPROVAL['payload'], 'publication_request': request}
            await self.conn.execute('UPDATE approvals SET payload=$1::jsonb', json.dumps(payload))
            before = await self.conn.fetch('SELECT * FROM approvals')
            writes = []
            def provider(method, path, data=None):
                self.assertEqual(method, 'GET', 'maintenance must not POST/merge/comment')
                head = checked('rev-parse', 'refs/heads/feat/test', cwd=mirror)
                base = checked('rev-parse', 'refs/heads/main', cwd=mirror)
                if path == '/repos/test/product':
                    return 200, {'id': 123, 'full_name': 'test/product'}
                if '/git/ref/' in path:
                    branch = 'main' if path.endswith('/main') else 'feat/test'
                    return 200, {'ref': 'refs/heads/'+branch, 'object': {'type': 'commit', 'sha': base if branch == 'main' else head}}
                return 200, [{'number': 5, 'html_url': 'https://github.com/test/product/pull/5', 'state': 'open',
                    'head': {'sha': head, 'ref': 'feat/test', 'repo': {'id': 123, 'full_name': 'test/product'}},
                    'base': {'sha': base, 'ref': 'main', 'repo': {'id': 123, 'full_name': 'test/product'}}}]
            def publisher(*args, cwd=None):
                writes.append(args)
                return git(*args, cwd=cwd)
            controller = SimpleNamespace(_gh_api=provider, sync_product_mirror=lambda repo: mirror,
                GIT_AUTHOR_NAME='Disposable Test', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                SANDBOX_IMAGE='lantern-sandbox:agentic-infrastructure', _git=publisher, _authed=lambda repo: str(mirror))
            lease = await self.claim()
            await leases.renew(self.other, lease, ttl=600)
            with patch.dict(os.environ, {'LANTERN_ISOLATED_TOOLS': '1'}):
                result = await maintenance.run_pass(self.conn, lease, controller)
            self.assertEqual(result['outcome'], 'updated')
            self.assertEqual(len(writes), 1)
            self.assertEqual(checked('rev-parse', 'refs/heads/main', cwd=mirror), new_base)
            self.assertNotEqual(checked('rev-parse', 'refs/heads/feat/test', cwd=mirror), approved_head)
            self.assertEqual(await self.conn.fetch('SELECT * FROM approvals'), before)
            await maintenance.finish(self.conn, lease, result)


if __name__ == '__main__':
    unittest.main()
