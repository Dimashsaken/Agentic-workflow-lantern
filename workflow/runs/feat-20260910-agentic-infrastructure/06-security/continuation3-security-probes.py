"""Independent regression probes; temporary owned roots, injected DB/provider only."""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools/azure-runner'))
import execution_retention as retention
import execution_leases as leases
import maintenance_runtime as maintenance
import github_publication as publication
import review
from isolated_tools import CURRENT_CANCELLATION
from qa_transport import Policy, Destination, TransportHeld
import qa_provenance


@asynccontextmanager
async def transaction(*args, **kwargs):
    yield


class Conn:
    transaction = transaction
    fetchrow = AsyncMock()
    execute = AsyncMock()


class Boundaries(unittest.IsolatedAsyncioTestCase):
    async def test_capture_persistence_binds_mode_and_durable_attempt(self):
        lease = leases.Lease('probe', 'owner', 1, 1, 1)
        base = {'transport_mode': 'direct_fixture', 'test_only': True,
                'images': {'gateway': None, 'recorder': 'sha256:'+'a'*64},
                'execution_id': 1, 'run_id': 'probe', 'fence': 1,
                'attempt': 1, 'execution_key': 'probe:04-qa-dev:1'}
        for change in ({'transport_mode': None}, {'transport_mode': 'unknown'},
                       {'test_only': False}, {'images': {'gateway': 'sha256:'+'b'*64, 'recorder': 'sha256:'+'a'*64}},
                       {'attempt': 2}, {'execution_key': 'other:04-qa-dev:1'}):
            conn = AsyncMock()
            conn.fetchrow.return_value = {'attempt': 1, 'idempotency_key': 'probe:04-qa-dev:1'}
            with self.subTest(change=change), patch.object(leases, 'fenced_transaction', transaction):
                with self.assertRaises(qa_provenance.CaptureHeld):
                    await qa_provenance.persist(conn, lease, {**base, **change})
                conn.execute.assert_not_awaited()
        conn = AsyncMock()
        conn.fetchrow.return_value = {'attempt': 1, 'idempotency_key': 'probe:04-qa-dev:1'}
        with patch.object(leases, 'fenced_transaction', transaction):
            await qa_provenance.persist(conn, lease, base)
        conn.execute.assert_awaited_once()

    async def test_external_policy_rejects_site_local_ipv6(self):
        with self.assertRaises(TransportHeld):
            Policy('probe', [Destination('https://example.org', ('fec0::1',), 1100)], created_at=1000)

    async def test_up_to_date_requires_final_provider_observation(self):
        approved = {'version': 3, 'run_id': 'probe', 'repo': 'https://github.com/test/product',
                    'base': 'main', 'branch': 'feat/test', 'work': 'feat/test',
                    'repository_id': 1, 'head_sha': 'a'*40, 'base_sha': 'b'*40,
                    'expected_remote_sha': None}
        lease = leases.Lease('probe', 'owner', 1, 1, None, True)
        conn = AsyncMock()
        conn.fetchrow.side_effect = [{'input': json.dumps({'publication_request': approved, 'pr_number': 1})}, None]
        controller = SimpleNamespace(_gh_api=lambda *args: None, sync_product_mirror=lambda *args: Path('.'))
        before = publication.Observation('a'*40, {'number': 1, 'head': {'sha': 'a'*40}})
        after = publication.Observation('c'*40, {'number': 1, 'head': {'sha': 'c'*40}})
        with patch.object(leases, 'fenced_transaction', transaction), \
                patch.object(publication, 'observe', side_effect=[before, after]), \
                patch.object(publication, '_repository_and_base', return_value=(1, 'b'*40)), \
                patch.object(review, '_sha', side_effect=['b'*40, 'a'*40]), \
                patch.object(review, '_is_ancestor', return_value=True):
            with self.assertRaises(publication.PublicationHeld):
                await maintenance.run_pass(conn, lease, controller)

    async def test_repeated_cancellation_still_joins_thread(self):
        started, stopped, release, ended = [threading.Event() for _ in range(4)]
        def work():
            class Worker:
                def stop(self):
                    stopped.set()
            CURRENT_CANCELLATION.get().register(Worker())
            started.set()
            release.wait(5)
            ended.set()
        task = asyncio.create_task(maintenance.joined_thread(work))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 3))
            task.cancel()
            self.assertTrue(await asyncio.to_thread(stopped.wait, 3))
            task.cancel()
            await asyncio.sleep(.05)
            returned_before_join = task.done() and not ended.is_set()
        finally:
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(await asyncio.to_thread(ended.wait, 3))
        self.assertFalse(returned_before_join, 'second cancellation returned with a live worker thread')

    async def test_descendant_cannot_use_wrong_execution_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root, authority = base/'checkouts', base/'authority'
            target = root/'attempt'
            with retention.allocation(target, root, 'owner', 'run', authority=authority):
                target.mkdir()
                (target/'nested').mkdir()
            with self.assertRaises(retention.RetentionHeld):
                with retention.worker_mount(target/'nested', 'other', authority):
                    pass

    async def test_quarantine_is_not_a_snapshot_exception(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root, authority = base/'checkouts', base/'authority'
            target = root/'attempt'
            with retention.allocation(target, root, 'owner', 'run', authority=authority):
                target.mkdir()
                (target/'nested').mkdir()
            with patch.object(retention, 'database_check', AsyncMock()), \
                    patch.object(retention.shutil, 'rmtree', side_effect=PermissionError('fixture lock')):
                with self.assertRaises(PermissionError):
                    await retention.retire(Conn(), 'owner', apply=True, authority=authority,
                                           inspect_mounts=lambda: [])
            quarantine = root/('.retired-' + retention.key('owner'))
            for execution in ('owner', 'other'):
                with self.subTest(execution=execution), self.assertRaises(retention.RetentionHeld):
                    with retention.worker_mount(quarantine, execution, authority):
                        pass

    async def test_trial_base_and_parent_movement_are_held(self):
        approved = {'version': 3, 'run_id': 'probe', 'repo': 'https://github.com/test/product',
                    'base': 'main', 'branch': 'feat/test', 'work': 'feat/test',
                    'repository_id': 1, 'head_sha': 'a'*40, 'base_sha': 'b'*40,
                    'expected_remote_sha': None}
        lease = leases.Lease('probe', 'owner', 1, 1, None, True)
        observed = publication.Observation('a'*40, {'number': 1, 'head': {'sha': 'a'*40}})
        for bad_base in (True, False):
            conn = AsyncMock()
            conn.fetchrow.side_effect = [{'input': json.dumps({'publication_request': approved, 'pr_number': 1})}, None]
            controller = SimpleNamespace(_gh_api=lambda *args: None, sync_product_mirror=lambda *args: Path('.'),
                                         GIT_AUTHOR_NAME='fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid')
            trial = {'clone': '.', 'clean': True, 'merge_sha': 'c'*40,
                     'base_sha': ('e' if bad_base else 'd')*40}
            git_result = subprocess.CompletedProcess([], 0, stdout=' '.join(['c'*40, 'f'*40, 'd'*40]))
            with self.subTest(bad_base=bad_base), \
                    patch.object(leases, 'fenced_transaction', transaction), \
                    patch.object(publication, 'observe', return_value=observed), \
                    patch.object(publication, '_repository_and_base', return_value=(1, 'd'*40)), \
                    patch.object(review, '_sha', side_effect=['d'*40, 'a'*40]), \
                    patch.object(review, '_is_ancestor', return_value=False), \
                    patch.object(review, 'trial_merge', return_value=trial), \
                    patch.object(review, '_git', return_value=git_result), \
                    patch.object(review, 'regate_local', side_effect=AssertionError('regate must not run')):
                with self.assertRaises(publication.PublicationHeld):
                    await maintenance.run_pass(conn, lease, controller)


if __name__ == '__main__':
    unittest.main(verbosity=2)
