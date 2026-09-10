"""Runtime ownership wiring controls; real Postgres crash proof is integration_leases.py."""
import asyncio
from contextlib import asynccontextmanager
import os
import unittest
from unittest.mock import AsyncMock, patch

import execution_leases as leases
import execution_runtime as runtime


@asynccontextmanager
async def open_transaction(*args, **kwargs):
    yield


class Runtime(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {'LANTERN_EXECUTION_LEASES': '1'})
        self.env.start()
        self.run_token = runtime.RUN.set(None)
        self.stage_token = runtime.STAGE.set(None)
        runtime.CLAIMS.clear()
        self.conn = AsyncMock()
        self.guard = AsyncMock()
        self.parent = leases.Lease('run-a', 'owner', 3)
        self.child = leases.Lease('run-a', 'owner', 1, 42, 3)

    async def asyncTearDown(self):
        runtime.RUN.reset(self.run_token)
        runtime.STAGE.reset(self.stage_token)
        runtime.CLAIMS.clear()
        self.env.stop()

    @asynccontextmanager
    async def guard_scope(self, *args, **kwargs):
        yield self.guard

    async def test_disabled_scope_keeps_legacy_execution_unclaimed(self):
        with patch.dict(os.environ, {'LANTERN_EXECUTION_LEASES': '0'}), patch.object(leases, 'acquire_run', AsyncMock()) as acquire:
            async with runtime.run_scope(self.conn, AsyncMock(), 'run-a'):
                async with runtime.stage_scope(self.conn, AsyncMock(), 'run-a', 'stage', 'host') as execution:
                    self.assertIsNone(execution)
            acquire.assert_not_awaited()

    async def test_claim_passes_exact_handle_to_scope_once(self):
        with patch.object(leases, 'acquire_run', AsyncMock(return_value=self.parent)) as acquire:
            self.assertEqual(await runtime.claim(self.conn, 'run-a'), 'run-a')
            with patch.object(leases, 'lease_guard', self.guard_scope):
                async with runtime.run_scope(self.conn, AsyncMock(), 'run-a'):
                    self.assertEqual(runtime.RUN.get().lease, self.parent)
                    self.assertNotIn('run-a', runtime.CLAIMS)
            acquire.assert_awaited_once()
        self.assertIsNone(runtime.RUN.get())

    async def test_run_scope_restores_context_after_failure(self):
        with patch.object(leases, 'acquire_run', AsyncMock(return_value=self.parent)), patch.object(leases, 'lease_guard', self.guard_scope):
            with self.assertRaisesRegex(ValueError, 'failure'):
                async with runtime.run_scope(self.conn, AsyncMock(), 'run-a'):
                    raise ValueError('failure')
        self.assertIsNone(runtime.RUN.get())

    async def test_failed_claim_never_binds_ownership(self):
        with patch.object(leases, 'acquire_run', AsyncMock(return_value=None)):
            self.assertIsNone(await runtime.claim(self.conn, 'run-a'))
            with self.assertRaises(leases.LeaseLost):
                async with runtime.run_scope(self.conn, AsyncMock(), 'run-a'):
                    self.fail('unclaimed run entered')
        self.assertFalse(runtime.CLAIMS)

    async def test_stage_requires_matching_parent(self):
        runtime.RUN.set(runtime.Ownership(self.parent, self.guard))
        with self.assertRaises(leases.LeaseLost):
            async with runtime.stage_scope(self.conn, AsyncMock(), 'different-run', 'stage', 'host'):
                self.fail('cross-run child was created')
        self.conn.fetchval.assert_not_awaited()

    async def test_stage_attempt_insert_and_acquire_share_parent_transaction(self):
        runtime.RUN.set(runtime.Ownership(self.parent, self.guard))
        self.conn.fetchval.side_effect = [2, 42]
        inside = []

        @asynccontextmanager
        async def transaction(conn, lease):
            self.assertEqual(lease, self.parent)
            inside.append(True)
            yield
            inside.pop()

        async def acquire(conn, parent, execution_id, ttl):
            self.assertTrue(inside)
            self.assertEqual((parent, execution_id), (self.parent, 42))
            return self.child

        with patch.object(leases, 'fenced_transaction', transaction), patch.object(leases, 'acquire_execution', acquire), patch.object(leases, 'lease_guard', self.guard_scope):
            async with runtime.stage_scope(self.conn, AsyncMock(), 'run-a', '03-coding.worker', 'host') as execution:
                self.assertEqual(execution, (2, 'run-a:03-coding.worker:2', 42))
                self.assertEqual(runtime.STAGE.get().lease, self.child)
                self.assertFalse(inside)
        self.assertIsNone(runtime.STAGE.get())
        self.assertEqual(runtime.RUN.get().lease, self.parent)

    async def test_mutation_requires_bound_context(self):
        for stage in (False, True):
            with self.assertRaises(leases.LeaseLost):
                async with runtime.mutation(self.conn, stage=stage):
                    self.fail('unbound write executed')

    async def test_finish_stops_before_fence_then_clears_only_bound_identity(self):
        events = []
        guard = AsyncMock()
        guard.stop.side_effect = lambda: events.append('stop')
        runtime.STAGE.set(runtime.Ownership(self.child, guard))

        @asynccontextmanager
        async def transaction(conn, lease):
            self.assertEqual(lease, self.child)
            events.append('fence')
            yield
            events.append('commit')

        with patch.object(leases, 'fenced_transaction', transaction):
            async with runtime.mutation(self.conn, stage=True, finish=True):
                events.append('finish')
        self.assertEqual(events, ['stop', 'fence', 'finish', 'commit'])
        self.assertEqual(self.conn.execute.await_args.args[1:], (42,))

    async def test_stale_finish_refuses_body_and_owner_clear(self):
        runtime.STAGE.set(runtime.Ownership(self.child, self.guard))

        @asynccontextmanager
        async def stale(*args):
            raise leases.LeaseLost('expired')
            yield

        with patch.object(leases, 'fenced_transaction', stale), self.assertRaises(leases.LeaseLost):
            async with runtime.mutation(self.conn, stage=True, finish=True):
                self.fail('stale completion executed')
        self.guard.stop.assert_awaited_once()
        self.conn.execute.assert_not_awaited()

    async def test_failed_mutation_does_not_clear_ownership(self):
        runtime.STAGE.set(runtime.Ownership(self.child, self.guard))
        with patch.object(leases, 'fenced_transaction', open_transaction), self.assertRaises(ValueError):
            async with runtime.mutation(self.conn, stage=True, finish=True):
                raise ValueError('database mutation failed')
        self.conn.execute.assert_not_awaited()

    async def test_parallel_tasks_do_not_share_stage_context(self):
        runtime.RUN.set(runtime.Ownership(self.parent, self.guard))
        ready = asyncio.Event()
        count = 0
        observed = []

        async def child_task(execution_id):
            nonlocal count
            child = leases.Lease('run-a', 'owner', 1, execution_id, 3)
            token = runtime.STAGE.set(runtime.Ownership(child, self.guard))
            try:
                count += 1
                if count == 2:
                    ready.set()
                await ready.wait()
                await asyncio.sleep(0)
                async with runtime.mutation(self.conn, stage=True):
                    observed.append(runtime.STAGE.get().lease.execution_id)
            finally:
                runtime.STAGE.reset(token)

        with patch.object(leases, 'fenced_transaction', open_transaction):
            await asyncio.gather(child_task(42), child_task(43))
        self.assertCountEqual(observed, [42, 43])
        self.assertIsNone(runtime.STAGE.get())

    async def test_stage_failure_closes_only_owned_running_child(self):
        self.conn.fetchrow.return_value = {'status': 'running'}
        with patch.object(leases, 'fenced_transaction', open_transaction), patch.object(leases, 'assert_current', AsyncMock()) as check:
            await runtime.fail_stage(self.conn, self.child, RuntimeError('stage failed'))
        check.assert_awaited_once_with(self.conn, self.child)
        self.assertEqual(self.conn.execute.await_args.args[1], 42)
        self.assertIn('stage failed', self.conn.execute.await_args.args[2])

    async def test_stage_failure_never_overwrites_completed_children(self):
        for status in ('succeeded', 'failed', 'waiting_gate', 'skipped'):
            self.conn.reset_mock()
            self.conn.fetchrow.return_value = {'status': status}
            with patch.object(leases, 'fenced_transaction', open_transaction), patch.object(leases, 'assert_current', AsyncMock()) as check:
                await runtime.fail_stage(self.conn, self.child, RuntimeError('bookkeeping failure'))
            self.conn.execute.assert_not_awaited()
            check.assert_not_awaited()

    async def test_expired_child_failure_refuses_write(self):
        self.conn.fetchrow.return_value = {'status': 'running'}
        with patch.object(leases, 'fenced_transaction', open_transaction), patch.object(leases, 'assert_current', AsyncMock(side_effect=leases.LeaseLost('expired'))):
            with self.assertRaises(leases.LeaseLost):
                await runtime.fail_stage(self.conn, self.child, RuntimeError('original failure'))
        self.conn.execute.assert_not_awaited()

    async def test_parent_lease_loss_refuses_even_failure_inspection(self):
        @asynccontextmanager
        async def stale(*args):
            raise leases.LeaseLost('parent replaced')
            yield
        with patch.object(leases, 'fenced_transaction', stale), self.assertRaises(leases.LeaseLost):
            await runtime.fail_stage(self.conn, self.child, RuntimeError('original failure'))
        self.conn.fetchrow.assert_not_awaited()
        self.conn.execute.assert_not_awaited()

    async def test_stage_scope_failure_finalizes_before_context_cleanup(self):
        runtime.RUN.set(runtime.Ownership(self.parent, self.guard))
        self.conn.fetchval.side_effect = [2, 42]

        async def fail(conn, lease, error):
            self.assertEqual(runtime.STAGE.get().lease, self.child)
            self.guard.stop.assert_awaited_once()
            self.assertEqual(str(error), 'failed child')

        with patch.object(leases, 'fenced_transaction', open_transaction), patch.object(leases, 'acquire_execution', AsyncMock(return_value=self.child)), patch.object(leases, 'lease_guard', self.guard_scope), patch.object(runtime, 'fail_stage', AsyncMock(side_effect=fail)) as finalize:
            with self.assertRaisesRegex(RuntimeError, 'failed child'):
                async with runtime.stage_scope(self.conn, AsyncMock(), 'run-a', '03-coding.review', 'host'):
                    raise RuntimeError('failed child')
        finalize.assert_awaited_once()
        self.assertIsNone(runtime.STAGE.get())

    async def test_review_failure_requires_matching_parent(self):
        import review
        with self.assertRaises(leases.LeaseLost):
            await review._mark_failed(self.conn, 'run-a', '03-coding.review', RuntimeError('failure'))
        self.conn.execute.assert_not_awaited()

    async def test_review_failure_checks_each_child_before_write(self):
        import review
        runtime.RUN.set(runtime.Ownership(self.parent, self.guard))
        self.conn.fetch.return_value = [{'id': 42, 'lease_fence': 1}]
        with patch.object(runtime, 'mutation', open_transaction), patch.object(leases, 'assert_current', AsyncMock(side_effect=leases.LeaseLost('child expired'))):
            with self.assertRaises(leases.LeaseLost):
                await review._mark_failed(self.conn, 'run-a', '03-coding.review', RuntimeError('failure'))
        self.conn.execute.assert_not_awaited()

    async def test_review_failure_writes_only_current_child(self):
        import review
        runtime.RUN.set(runtime.Ownership(self.parent, self.guard))
        self.conn.fetch.return_value = [{'id': 42, 'lease_fence': 1}]
        with patch.object(runtime, 'mutation', open_transaction), patch.object(leases, 'assert_current', AsyncMock()) as check:
            await review._mark_failed(self.conn, 'run-a', '03-coding.review', RuntimeError('failure'))
        check.assert_awaited_once_with(self.conn, self.child)
        self.assertEqual(self.conn.execute.await_args.args[1], 42)


class Publication(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import pipeline
        self.pipeline = pipeline
        self.env = patch.dict(os.environ, {'LANTERN_EXECUTION_LEASES': '1'})
        self.env.start()
        self.lease = leases.Lease('run-a', 'owner', 1, 42, 3)
        self.conn = AsyncMock()
        self.handoff = {'head_sha': 'a'*40, 'branch': 'feat/example'}

    async def asyncTearDown(self):
        self.env.stop()

    @asynccontextmanager
    async def stage_scope(self, *args):
        token = runtime.STAGE.set(runtime.Ownership(self.lease, AsyncMock()))
        try:
            yield (1, 'run-a:03-coding.publish:1', 42)
        finally:
            runtime.STAGE.reset(token)

    async def publish(self, effect, publish_result=None, publish_error=None, observation_error=None, legacy=None, legacy_v2=None):
        from contextlib import ExitStack
        with ExitStack() as stack:
            stack.enter_context(patch.object(runtime, 'stage_scope', self.stage_scope))
            stack.enter_context(patch.object(runtime, 'mutation', open_transaction))
            stack.enter_context(patch.object(self.pipeline, '_read_handoff', return_value=self.handoff))
            stack.enter_context(patch.object(self.pipeline, 'product_target', AsyncMock(return_value=('https://github.com/owner/product.git', 'main'))))
            stack.enter_context(patch.object(self.pipeline, 'product_work_branch', AsyncMock(return_value='feat/example')))
            stack.enter_context(patch.object(leases, 'read_effect', AsyncMock(side_effect=[legacy, legacy_v2, None if effect.created else effect])))
            request = {'run_id': 'run-a', 'head_sha': 'a'*40, 'branch': 'feat/example',
                       'repo': 'https://github.com/owner/product.git', 'base': 'main', 'work': 'feat/example',
                       'version': 3, 'repository_id': 123, 'base_sha': 'c'*40, 'expected_remote_sha': None}
            stack.enter_context(patch.object(self.pipeline.github_publication, 'prepare_request', return_value=request))
            stack.enter_context(patch.object(self.pipeline.github_publication, 'reconcile', return_value=publish_result, side_effect=observation_error))
            stack.enter_context(patch.object(leases, 'reconcile_effect', AsyncMock()))
            self.record = stack.enter_context(patch.object(self.pipeline, '_record_coding_publication', AsyncMock()))
            begin = stack.enter_context(patch.object(leases, 'begin_effect', AsyncMock(return_value=effect)))
            perform = stack.enter_context(patch.object(self.pipeline, '_publish_coding_branch', AsyncMock(return_value=publish_result, side_effect=publish_error)))
            confirm = stack.enter_context(patch.object(leases, 'confirm_effect', AsyncMock()))
            uncertain = stack.enter_context(patch.object(leases, 'mark_effect_uncertain', AsyncMock()))
            try:
                result = await self.pipeline.publish_coding_branch(self.conn, 'run-a')
                return result, begin, perform, confirm, uncertain
            except Exception as error:
                return error, begin, perform, confirm, uncertain

    async def test_new_intent_publishes_once_then_confirms(self):
        payload = {'pr_url': 'local-test-ref', 'head_sha': 'a'*40}
        result, begin, perform, confirm, uncertain = await self.publish(leases.Effect(True, 'intended', None, None), payload)
        self.assertEqual(result, payload)
        perform.assert_awaited_once()
        confirm.assert_awaited_once()
        uncertain.assert_not_awaited()
        self.assertEqual(begin.await_args.args[2], 'publish-v3:run-a:' + 'a'*40)
        self.assertEqual(begin.await_args.args[4]['repo'], 'https://github.com/owner/product.git')
        self.assertEqual(perform.await_args.kwargs['expected'], begin.await_args.args[4])

    def recorded_request(self):
        return {'run_id': 'run-a', 'head_sha': 'a'*40, 'branch': 'feat/example',
                'repo': 'https://github.com/owner/product.git', 'base': 'main', 'work': 'feat/example',
                'version': 3, 'repository_id': 123, 'base_sha': 'c'*40, 'expected_remote_sha': None}

    async def test_confirmed_duplicate_observes_without_reinvocation(self):
        payload = {'pr_url': 'local-test-ref', 'publication_request': self.recorded_request()}
        result, _, perform, confirm, uncertain = await self.publish(leases.Effect(False, 'confirmed', 'local-test-ref', payload), payload)
        self.assertEqual(result['pr_url'], payload['pr_url'])
        perform.assert_not_awaited()
        confirm.assert_not_awaited()
        uncertain.assert_not_awaited()

    async def test_unconfirmed_duplicates_hold_without_reinvocation(self):
        for status in ('intended', 'uncertain'):
            with self.subTest(status=status):
                result, _, perform, confirm, uncertain = await self.publish(leases.Effect(False, status, None, None))
                self.assertIsInstance(result, RuntimeError)
                self.assertIn('request is unavailable', str(result))
                perform.assert_not_awaited()
                confirm.assert_not_awaited()
                uncertain.assert_not_awaited()

    async def test_legacy_intent_blocks_v3_replay(self):
        result, begin, perform, confirm, uncertain = await self.publish(
            leases.Effect(True, 'intended', None, None), legacy=leases.Effect(False, 'uncertain', None, None))
        self.assertIn('legacy publication intent', str(result))
        begin.assert_not_awaited()
        perform.assert_not_awaited()

    async def test_v2_intent_blocks_v3_replay(self):
        for status in ('intended', 'uncertain', 'confirmed'):
            result, begin, perform, _, _ = await self.publish(
                leases.Effect(True, 'intended', None, None), legacy_v2=leases.Effect(False, status, None, None))
            self.assertIn('legacy publication intent', str(result))
            begin.assert_not_awaited()
            perform.assert_not_awaited()

    async def test_interrupted_v3_parent_enters_split_reconciliation(self):
        payload = {'publication_request': self.recorded_request(), 'pr_url': 'observed-pr'}
        for status in ('intended', 'uncertain'):
            result, _, perform, confirm, _ = await self.publish(leases.Effect(False, status, None, payload), payload)
            self.assertEqual(result['pr_url'], 'observed-pr')
            perform.assert_awaited_once()
            confirm.assert_not_awaited()

    async def test_confirmed_duplicate_observation_failure_holds(self):
        payload = {'publication_request': self.recorded_request(), 'pr_url': 'old-pr'}
        result, _, perform, confirm, uncertain = await self.publish(
            leases.Effect(False, 'confirmed', 'old-pr', payload), observation_error=RuntimeError('provider head changed'))
        self.assertIn('provider head changed', str(result))
        perform.assert_not_awaited()
        confirm.assert_not_awaited()
        uncertain.assert_not_awaited()

    async def test_handoff_changes_during_provider_call_emit_no_authoritative_artifacts(self):
        def changed(*args, **kwargs):
            self.handoff['head_sha'] = 'b' * 40
            return {'pr_url': 'observed-pr'}
        result, _, perform, confirm, uncertain = await self.publish(
            leases.Effect(True, 'intended', None, None), publish_error=changed)
        self.assertIn('target or handoff changed', str(result))
        perform.assert_awaited_once()
        confirm.assert_not_awaited()
        self.record.assert_not_awaited()
        uncertain.assert_awaited_once()

    async def test_split_before_action_callback_checks_fence_before_intent(self):
        @asynccontextmanager
        async def stale(*args, **kwargs):
            raise leases.LeaseLost('old controller cannot initiate an action')
            yield
        def publisher(*args):
            args[7]('pr')
            self.fail('stale controller reached provider call')
        with patch.object(self.pipeline, 'product_target', AsyncMock(return_value=('https://github.com/owner/product.git', 'main'))), \
                patch.object(self.pipeline, 'product_work_branch', AsyncMock(return_value='feat/example')), \
                patch.object(self.pipeline, '_publish_branch', publisher), \
                patch.object(runtime, 'mutation', stale), \
                patch.object(leases, 'begin_effect', AsyncMock()) as begin:
            with self.assertRaisesRegex(leases.LeaseLost, 'old controller'):
                await self.pipeline._publish_coding_branch(self.conn, 'run-a', self.recorded_request())
        begin.assert_not_awaited()

    async def test_split_before_action_callback_rechecks_handoff(self):
        def publisher(*args):
            self.handoff['head_sha'] = 'b' * 40
            args[7]('pr')
            self.fail('changed handoff reached provider call')
        with patch.object(self.pipeline, 'product_target', AsyncMock(return_value=('https://github.com/owner/product.git', 'main'))), \
                patch.object(self.pipeline, 'product_work_branch', AsyncMock(return_value='feat/example')), \
                patch.object(self.pipeline, '_read_handoff', return_value=self.handoff), \
                patch.object(self.pipeline, '_publish_branch', publisher), \
                patch.object(runtime, 'mutation', open_transaction), \
                patch.object(leases, 'begin_effect', AsyncMock()) as begin:
            with self.assertRaisesRegex(RuntimeError, 'target or handoff changed'):
                await self.pipeline._publish_coding_branch(self.conn, 'run-a', self.recorded_request())
        begin.assert_not_awaited()

    async def test_gate_reobserves_after_review_and_holds_changed_provider(self):
        from contextlib import ExitStack
        payload = {'publication_request': self.recorded_request(), 'pr_url': 'observed-pr'}
        self.conn.fetchrow.return_value = {'current_stage': '03-coding', 'coding_mode': 'auto'}
        with ExitStack() as stack:
            stack.enter_context(patch.object(runtime, 'mutation', open_transaction))
            stack.enter_context(patch.object(self.pipeline.builders, 'run_coding', AsyncMock(return_value=None)))
            stack.enter_context(patch.object(self.pipeline, 'publish_coding_branch', AsyncMock(return_value=payload)))
            stack.enter_context(patch.object(self.pipeline.review, 'after_publish', AsyncMock(return_value=payload)))
            observe = stack.enter_context(patch.object(self.pipeline.github_publication, 'reconcile', side_effect=RuntimeError('provider moved during review')))
            gate = stack.enter_context(patch.object(self.pipeline, 'open_gate', AsyncMock()))
            stack.enter_context(patch.object(self.pipeline, 'log_event', AsyncMock()))
            stack.enter_context(patch.object(self.pipeline, 'render_runboard', AsyncMock()))
            await self.pipeline._step_run(self.conn, 'run-a')
        observe.assert_called_once()
        gate.assert_not_awaited()

    async def test_provider_failure_records_uncertainty(self):
        result, _, perform, confirm, uncertain = await self.publish(leases.Effect(True, 'intended', None, None), publish_error=OSError('provider disconnected'))
        self.assertIsInstance(result, OSError)
        perform.assert_awaited_once()
        confirm.assert_not_awaited()
        uncertain.assert_awaited_once()

    async def test_lease_loss_cannot_confirm_or_rewrite_ledger(self):
        result, _, perform, confirm, uncertain = await self.publish(leases.Effect(True, 'intended', None, None), publish_error=leases.LeaseLost('lost'))
        self.assertIsInstance(result, leases.LeaseLost)
        perform.assert_awaited_once()
        confirm.assert_not_awaited()
        uncertain.assert_not_awaited()


class Builders(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_builders_receive_distinct_connections_and_close_them(self):
        import builders
        root = AsyncMock()
        children = [AsyncMock(), AsyncMock()]
        connect = AsyncMock(side_effect=children)
        observed = []

        async def execute(conn, run_id, stage, runner):
            observed.append(conn)
            await asyncio.sleep(.01)

        await builders.fan_out(root, 'run-a', 'host', ['one','two'], execute, 2, connect=connect)
        self.assertEqual(observed, children)
        self.assertNotIn(root, observed)
        for child in children:
            child.close.assert_awaited_once()

    async def test_parallel_failure_closes_connections_and_preserves_lease_loss(self):
        import builders
        children = [AsyncMock(), AsyncMock()]

        async def execute(conn, run_id, stage, runner):
            if stage.endswith('.one'):
                raise leases.LeaseLost('expired builder')

        with self.assertRaises(leases.LeaseLost):
            await builders.fan_out(AsyncMock(), 'run-a', 'host', ['one','two'], execute, 2, connect=AsyncMock(side_effect=children))
        for child in children:
            child.close.assert_awaited_once()

    async def test_parallel_builders_cannot_share_a_live_connection(self):
        import builders
        execute = AsyncMock()
        with self.assertRaises(builders.BuilderError):
            await builders.fan_out(AsyncMock(), 'run-a', 'host', ['one','two'], execute, 2)
        execute.assert_not_awaited()

    async def test_host_seed_and_merge_have_before_and_after_fences(self):
        import builders
        import pipeline
        from contextlib import ExitStack
        for reject_at in (1, 2, 3, 4, None):
            with self.subTest(reject_at=reject_at), ExitStack() as stack:
                count = 0

                @asynccontextmanager
                async def fence(*args, **kwargs):
                    nonlocal count
                    count += 1
                    if count == reject_at:
                        raise leases.LeaseLost('lost root')
                    yield

                stack.enter_context(patch.object(runtime, 'mutation', fence))
                stack.enter_context(patch.object(builders, 'builder_names', return_value=['one','two']))
                stack.enter_context(patch.object(builders, 'parallelism', return_value=2))
                seed = stack.enter_context(patch.object(builders, 'seed_branches', return_value=('mirror','a'*40)))
                record = {'run_id':'run-a', 'branch':'feat/test', 'head_sha':'b'*40, 'builders':[]}
                merge = stack.enter_context(patch.object(builders, 'merge', return_value=record))
                write = stack.enter_context(patch.object(builders, 'write_merge_record'))
                fan_out = stack.enter_context(patch.object(builders, 'fan_out', AsyncMock()))
                stack.enter_context(patch.object(pipeline, 'product_target', AsyncMock(return_value=('repo','main'))))
                stack.enter_context(patch.object(pipeline, 'product_work_branch', AsyncMock(return_value='feat/test')))
                stack.enter_context(patch.object(pipeline, 'log_event', AsyncMock()))
                execute = AsyncMock()
                if reject_at:
                    with self.assertRaises(leases.LeaseLost):
                        await builders.run_coding(AsyncMock(), 'run-a', '03-coding', 'host', execute)
                    write.assert_not_called()
                    execute.assert_not_awaited()
                    self.assertEqual(seed.call_count, int(reject_at > 1))
                    self.assertEqual(merge.call_count, int(reject_at > 3))
                else:
                    await builders.run_coding(AsyncMock(), 'run-a', '03-coding', 'host', execute)
                    self.assertEqual(count, 4)
                    write.assert_called_once_with(record)
                    execute.assert_awaited_once()
                    self.assertFalse(merge.call_args.kwargs['persist'])
                    self.assertEqual(fan_out.await_args.kwargs['connect'], pipeline.connect)


if __name__ == '__main__':
    unittest.main()
