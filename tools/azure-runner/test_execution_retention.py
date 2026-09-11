"""Destructive controls are confined to owned TemporaryDirectory roots."""
from contextlib import asynccontextmanager
import json
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import execution_retention as retention


class Connection:
    @asynccontextmanager
    async def transaction(self):
        yield
    fetchrow = AsyncMock()
    execute = AsyncMock()


class Retirement(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / 'checkouts'
        self.authority = self.base / 'authority'
        self.path = self.root / 'attempt'
        self.execution = 'run:stage:1'
        with retention.allocation(self.path, self.root, self.execution, 'run', authority=self.authority):
            self.path.mkdir()
            (self.path / 'source.py').write_text('example')
        self.db_patch = patch.object(retention, 'database_check', AsyncMock())
        self.check = self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.temporary.cleanup()

    async def retire(self, **kwargs):
        return await retention.retire(Connection(), self.execution, authority=self.authority,
                                      inspect_mounts=lambda: [], **kwargs)

    def descriptor(self):
        return self.authority / 'records-v2' / (retention.key(self.execution) + '.json')

    async def test_dry_run_preserves_bytes_then_deletes_only_checkout(self):
        evidence = self.base / 'evidence.json'
        evidence.write_text('retain forever')
        result = await self.retire()
        self.assertEqual(result['bytes'], 7)
        self.assertTrue(self.path.exists())
        self.assertEqual((await self.retire(apply=True))['state'], 'deleted')
        self.assertFalse(self.path.exists())
        self.assertEqual(evidence.read_text(), 'retain forever')
        self.assertEqual((await self.retire(apply=True))['state'], 'deleted')
        with self.assertRaises(retention.RetentionHeld):
            with retention.worker_mount(self.path, self.execution, self.authority):
                self.fail('retired checkout started')

    async def test_mount_lookup_does_not_enumerate_retained_history(self):
        # Build 10,000 durable tombstone mappings; only the one-time legacy index
        # rebuild may enumerate them. Steady launch checks are independent of n.
        for i in range(10000):
            path = self.root / ('old-' + str(i))
            location = self.authority / ('path-' + retention.path_key(path) + '.json')
            location.write_text(json.dumps({'path': str(path), 'execution_key': 'old:' + str(i)}))
        (self.authority / 'paths-v2' / 'complete.json').unlink()
        with retention.path_index(self.authority):
            pass
        with patch.object(Path, 'glob', side_effect=AssertionError('unbounded history scan')):
            with retention.worker_mount(self.path, self.execution, self.authority):
                pass
            with self.assertRaisesRegex(retention.RetentionHeld, 'ancestor'):
                with retention.worker_mount(self.root, self.execution, self.authority):
                    pass
            with self.assertRaisesRegex(retention.RetentionHeld, 'different execution'):
                with retention.worker_mount(self.root/'old-9999', self.execution, self.authority):
                    pass

    async def test_legacy_lock_creation_cannot_split_current_lock_identity(self):
        execution='new-lock-identity'
        legacy=self.authority/(retention.key(execution)+'.lock')
        with retention.locked(execution,self.authority):
            # Simulate an old reader opening its permanent top-level pathname.
            # The former existence-based selection switched newer readers to it.
            with legacy.open('a+b'):
                pass
            with self.assertRaisesRegex(retention.RetentionHeld,'lock is busy'):
                with retention.locked(execution,self.authority,timeout=.05):
                    self.fail('two holders for one execution')
        with retention.locked(execution,self.authority,timeout=.05):
            pass

    async def test_crashed_legacy_index_rebuild_is_retried(self):
        marker = self.authority/'paths-v2'/'complete.json'
        marker.unlink()
        legacy = self.root/'legacy-crash'
        (self.authority/('path-'+retention.path_key(legacy)+'.json')).write_text(json.dumps({'path':str(legacy),'execution_key':'legacy'}))
        with patch.object(retention, '_index_ancestors', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                with retention.worker_mount(self.path, self.execution, self.authority):
                    pass
        self.assertFalse(marker.exists())
        with retention.worker_mount(self.path, self.execution, self.authority):
            pass
        self.assertTrue(marker.exists())

    async def test_legacy_addition_during_registration_is_indexed(self):
        original = retention.atomic_json
        legacy = self.root/'late-parent'/'legacy'
        injected = False
        def interleave(path,value):
            nonlocal injected
            original(path,value)
            if value.get('protocol')=='retention-v2-sentinel' and not injected:
                injected=True
                original(self.authority/('path-'+retention.path_key(legacy)+'.json'),{'execution_key':'legacy','path':str(legacy)})
        with patch.object(retention,'atomic_json',side_effect=interleave):
            with retention.allocation(self.root/'current',self.root,'current','run',authority=self.authority):
                (self.root/'current').mkdir()
        self.assertTrue(injected)
        with self.assertRaisesRegex(retention.RetentionHeld,'ancestor'):
            with retention.worker_mount(legacy.parent,'other',self.authority):
                pass

    async def test_legacy_addition_invalidates_index(self):
        legacy = self.root/'legacy-parent'/'old-checkout'
        (self.authority/('path-'+retention.path_key(legacy)+'.json')).write_text(json.dumps({'path':str(legacy),'execution_key':'legacy'}))
        with self.assertRaisesRegex(retention.RetentionHeld,'ancestor'):
            with retention.worker_mount(legacy.parent,'other',self.authority):
                pass

    async def test_slow_allocation_does_not_block_unrelated_mount(self):
        import threading
        started, release = threading.Event(), threading.Event()
        def allocate():
            with retention.allocation(self.root/'slow',self.root,'slow','run',authority=self.authority):
                started.set()
                if not release.wait(5):
                    raise RuntimeError('allocation wait timed out')
                (self.root/'slow').mkdir()
        task = asyncio.create_task(asyncio.to_thread(allocate))
        await asyncio.to_thread(started.wait,3)
        try:
            with retention.worker_mount(self.path,self.execution,self.authority):
                pass
        finally:
            release.set()
            await task

    async def test_inventory_reports_legacy_and_database_failure_without_delete(self):
        legacy = self.root/'legacy'
        legacy.mkdir()
        (legacy/'file').write_bytes(b'123')
        conn = Connection()
        conn.fetchval = AsyncMock(side_effect=OSError('secret database string'))
        result = await retention.inventory(conn, self.root, authority=self.authority, inspect_mounts=lambda: [])
        self.assertEqual(result['known_bytes'], 10)
        self.assertEqual(len(result['entries']), 2)
        self.assertFalse(any(r['eligible'] for r in result['entries']))
        self.assertNotIn('secret', json.dumps(result))
        self.assertTrue(self.path.exists())
        self.assertTrue(legacy.exists())

    async def test_mount_including_stopped_container_holds(self):
        with self.assertRaisesRegex(retention.RetentionHeld, 'container'):
            await retention.retire(Connection(), self.execution, apply=True, authority=self.authority,
                                   inspect_mounts=lambda: [{'container': 'stopped', 'source': str(self.path)}])
        self.assertTrue(self.path.exists())

    async def test_wrong_execution_key_cannot_bypass_path_lock(self):
        with self.assertRaisesRegex(retention.RetentionHeld, 'different execution'):
            with retention.worker_mount(self.path, 'run:other:2', self.authority):
                self.fail('wrong execution mounted a registered path')

    async def test_ancestor_mount_is_refused(self):
        with self.assertRaisesRegex(retention.RetentionHeld, 'ancestor'):
            with retention.worker_mount(self.root, 'other', self.authority):
                self.fail('broad mount exposed a registered checkout')

    async def test_descendant_and_quarantine_wrong_key_are_refused(self):
        (self.path/'nested').mkdir()
        for path in (self.path/'nested', self.root/('.retired-'+retention.key(self.execution))):
            with self.assertRaisesRegex(retention.RetentionHeld, 'different execution'):
                with retention.worker_mount(path, 'other', self.authority):
                    pass

    async def test_crash_after_delete_resumes_audit_without_touching_other_paths(self):
        real_write = retention.atomic_json
        def fail_deleted(path, value):
            if value.get('state') == 'deleted':
                raise OSError('crash after deletion')
            real_write(path, value)
        with patch.object(retention, 'atomic_json', side_effect=fail_deleted), self.assertRaises(OSError):
            await self.retire(apply=True)
        self.assertEqual(json.loads(self.descriptor().read_text())['state'], 'quarantined')
        self.assertEqual((await self.retire(apply=True))['state'], 'deleted')

    async def test_audit_failure_is_retryable_after_filesystem_completion(self):
        with patch.object(retention, 'audit', AsyncMock(side_effect=OSError('DB failure'))), self.assertRaises(OSError):
            await self.retire(apply=True)
        with patch.object(retention, 'audit', AsyncMock()) as audit:
            self.assertEqual((await self.retire(apply=True))['state'], 'deleted')
            audit.assert_awaited_once()

    async def test_database_or_docker_failure_holds(self):
        self.check.side_effect = retention.RetentionHeld('active lease')
        with self.assertRaises(retention.RetentionHeld):
            await self.retire(apply=True)
        self.check.side_effect = None
        with self.assertRaises(OSError):
            await retention.retire(Connection(), self.execution, apply=True, authority=self.authority,
                                   inspect_mounts=lambda: (_ for _ in ()).throw(OSError('Docker offline')))
        self.assertTrue(self.path.exists())

    async def test_substitution_does_not_delete_replacement(self):
        self.path.rename(self.root / 'original')
        self.path.mkdir()
        (self.path / 'precious').write_text('preserve')
        with self.assertRaisesRegex(retention.RetentionHeld, 'substituted'):
            await self.retire(apply=True)
        self.assertEqual((self.path / 'precious').read_text(), 'preserve')

    async def test_hardlink_held(self):
        os.link(self.path / 'source.py', self.base / 'linked')
        with self.assertRaisesRegex(retention.RetentionHeld, 'linked'):
            await self.retire(apply=True)
        self.assertTrue(self.path.exists())

    async def test_crash_before_quarantine_keeps_tombstone_and_resumes(self):
        with patch.object(retention.os, 'rename', side_effect=OSError('injected crash')):
            with self.assertRaises(OSError):
                await self.retire(apply=True)
        self.assertEqual(json.loads(self.descriptor().read_text())['state'], 'retired')
        with self.assertRaises(retention.RetentionHeld):
            with retention.worker_mount(self.path, self.execution, self.authority):
                pass
        self.assertEqual((await self.retire(apply=True))['state'], 'deleted')

    async def test_locked_file_after_quarantine_can_resume(self):
        with patch.object(retention.shutil, 'rmtree', side_effect=PermissionError('locked file')):
            with self.assertRaises(PermissionError):
                await self.retire(apply=True)
        self.assertFalse(self.path.exists())
        self.assertEqual(json.loads(self.descriptor().read_text())['state'], 'quarantined')
        self.assertEqual((await self.retire(apply=True))['state'], 'deleted')

    async def test_unknown_legacy_and_allocating_are_held(self):
        value = json.loads(self.descriptor().read_text())
        value['state'] = 'allocating'
        self.descriptor().write_text(json.dumps(value))
        with self.assertRaises(retention.RetentionHeld):
            await self.retire(apply=True)
        self.descriptor().unlink()
        with self.assertRaises(retention.RetentionHeld):
            await self.retire(apply=True)
        self.assertTrue(self.path.exists())

    async def test_real_other_process_lock_blocks_retirement(self):
        code = "import sys,time; from execution_retention import locked;\nwith locked(sys.argv[1],sys.argv[2]):\n print('locked',flush=True); time.sleep(30)"
        process = subprocess.Popen([sys.executable, '-c', code, self.execution, str(self.authority)],
                                   cwd=Path(__file__).parent, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'locked')
            with self.assertRaisesRegex(retention.RetentionHeld, 'busy'):
                with retention.locked(self.execution, self.authority, timeout=.1):
                    pass
            self.assertTrue(self.path.exists())
        finally:
            process.terminate()
            process.wait(timeout=10)
            process.stdout.close()
        self.assertEqual((await self.retire(apply=True))['state'], 'deleted')

    async def test_failed_allocation_never_becomes_candidate(self):
        other = self.root / 'incomplete'
        with self.assertRaises(OSError):
            with retention.allocation(other, self.root, 'run:stage:2', 'run', authority=self.authority):
                other.mkdir()
                raise OSError('controller died')
        with self.assertRaises(retention.RetentionHeld):
            await retention.retire(Connection(), 'run:stage:2', authority=self.authority, inspect_mounts=lambda: [])


if __name__ == '__main__':
    unittest.main()
