import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

import qa_execution as qa
from qa_provenance import CaptureHeld
from qa_transport import Destination, Policy, TransportHeld
import execution_leases as leases

@asynccontextmanager
async def fence(conn, lease):
    yield

class Controller(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.lease = leases.Lease('run','owner',1,7,1)
        self.row = {'run_id':'run','stage':'04-qa-dev','attempt':2,'idempotency_key':'run:qa:2'}
        self.conn = AsyncMock()
        self.conn.fetchrow.return_value = self.row
        self.descriptor = {'origin':'https://fixture.test','revision':'a'*40,'deployment_id':'d1','descriptor_id':'controller:1'}
        policy = Policy('run:qa:2',[Destination('https://fixture.test',('127.0.0.1',),time.time()+60)],test_only=True)
        self.spec = {'policy':policy.document(),'transport_mode':'direct_fixture','deployment':self.descriptor,
                     'requirements':['AC-1'],'images':{'gateway':None,'recorder':'sha256:'+'a'*64},
                     'ca_fingerprint':'b'*64,'authority':str(self.root/'authority'),'media':str(self.root/'media'),
                     'viewport':{'width':1280,'height':720},'actions':[{'id':'a','kind':'navigate','url':'https://fixture.test','requirement':'AC-1'}]}
        self.stop = AsyncMock()
        self.observe = AsyncMock(return_value=self.descriptor)
        self.launch = AsyncMock()
        self.patch = patch.object(qa.leases,'fenced_transaction',fence)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    async def execute(self, **kwargs):
        return await qa.execute_capture(self.conn,self.lease,self.spec,launch=self.launch,
          stop=self.stop,observe_deployment=self.observe,allow_direct_fixture=True,**kwargs)

    async def test_fixture_requires_explicit_test_entry(self):
        with self.assertRaises(CaptureHeld):
            await qa.execute_capture(self.conn,self.lease,self.spec,launch=self.launch,stop=self.stop,observe_deployment=self.observe)
        self.launch.assert_not_called()

    async def test_external_cannot_bypass_activation_with_callback(self):
        self.spec['transport_mode']='gateway'
        self.spec['images']['gateway']='sha256:'+'c'*64
        with self.assertRaises(TransportHeld):
            await self.execute()
        self.launch.assert_not_called()

    async def test_wrong_stage_and_expired_policy_never_launch(self):
        self.row['stage']='03-coding'
        with self.assertRaises(CaptureHeld):
            await self.execute()
        self.row['stage']='04-qa-dev'
        self.spec['policy']['created_at']=time.time()-60
        self.spec['policy']['destinations'][0]['expires_at']=time.time()-1
        with self.assertRaises(CaptureHeld):
            await self.execute()
        self.launch.assert_not_called()

    async def test_start_deployment_drift_prevents_launch(self):
        self.observe.return_value={**self.descriptor,'revision':'d'*40}
        with self.assertRaises(CaptureHeld):
            await self.execute()
        self.launch.assert_not_called()

    async def test_launch_failure_is_quiesced(self):
        self.launch.side_effect=RuntimeError('recorder failed')
        with self.assertRaises(RuntimeError):
            await self.execute()
        self.stop.assert_awaited_once()

    async def test_forged_outcome_cannot_reach_seal(self):
        async def launch(plan):
            return {'recording_id':plan['recording_id'],'writers_closed':True,
                    'outcomes':[{'command_id':'forged','requirement':'AC-1','passed':True}]}
        self.launch.side_effect=launch
        with patch.object(qa.Capture,'seal') as seal, self.assertRaises(CaptureHeld):
            await self.execute()
        seal.assert_not_called()
        self.stop.assert_awaited_once()

    async def test_repeated_cancel_does_not_outlive_cleanup(self):
        started, finished=asyncio.Event(),asyncio.Event()
        async def stop():
            started.set()
            await asyncio.sleep(.05)
            finished.set()
        task=asyncio.create_task(qa.quiesce(stop))
        await started.wait()
        task.cancel()
        await asyncio.sleep(.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(finished.is_set())

    async def test_policy_expiry_stops_active_recording_before_it_returns(self):
        self.spec['policy']['destinations'][0]['expires_at'] = time.time() + .08
        async def launch(plan):
            await asyncio.Future()
        self.launch.side_effect = launch
        with patch.object(qa, 'WATCHDOG_INTERVAL', .01), self.assertRaisesRegex(CaptureHeld, 'expired'):
            await asyncio.wait_for(self.execute(), timeout=1)
        self.stop.assert_awaited_once()

    async def test_gateway_death_stops_active_recording(self):
        launched = asyncio.Event()
        async def launch(plan):
            launched.set()
            await asyncio.Future()
        async def health():
            return not launched.is_set()
        self.launch.side_effect = launch
        with patch.object(qa, 'WATCHDOG_INTERVAL', .01), self.assertRaisesRegex(CaptureHeld, 'healthy'):
            await asyncio.wait_for(self.execute(check_transport=health), timeout=1)
        self.stop.assert_awaited_once()

    async def test_lease_loss_stops_active_recording(self):
        launched = asyncio.Event()
        async def launch(plan):
            launched.set()
            await asyncio.Future()
        @asynccontextmanager
        async def lose(conn, lease):
            if launched.is_set():
                raise leases.LeaseLost('test lost lease')
            yield
        self.launch.side_effect = launch
        with patch.object(qa.leases, 'fenced_transaction', lose), \
                patch.object(qa, 'WATCHDOG_INTERVAL', .01), self.assertRaises(leases.LeaseLost):
            await asyncio.wait_for(self.execute(), timeout=1)
        self.stop.assert_awaited_once()

    async def test_cleanup_failure_prevents_receipt(self):
        self.launch.return_value = {}
        self.stop.side_effect = RuntimeError('cleanup not confirmed')
        with patch.object(qa.Capture, 'seal') as seal, self.assertRaisesRegex(RuntimeError, 'cleanup'):
            await self.execute()
        seal.assert_not_called()

    async def test_watchdog_timeout_stops_recording(self):
        started = asyncio.Event()
        async def launch(plan):
            started.set()
            await asyncio.Future()
        async def check():
            if started.is_set():
                await asyncio.Future()
        with patch.object(qa, 'WATCHDOG_INTERVAL', .01), patch.object(qa, 'WATCHDOG_CHECK_TIMEOUT', .02):
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(qa.monitored_recording({}, launch=launch, stop=self.stop, check=check), 1)
        self.stop.assert_awaited_once()

    async def test_process_is_stopped_before_uncooperative_launcher_is_joined(self):
        launched, stopped = asyncio.Event(), asyncio.Event()
        async def launch(plan):
            launched.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                await stopped.wait()
        async def stop():
            stopped.set()
        async def check():
            if launched.is_set():
                raise CaptureHeld('gateway died')
        with patch.object(qa, 'WATCHDOG_INTERVAL', .01), self.assertRaisesRegex(CaptureHeld, 'gateway died'):
            await asyncio.wait_for(qa.monitored_recording({}, launch=launch, stop=stop, check=check), 1)
        self.assertTrue(stopped.is_set())

    async def test_successful_watchdog_returns_result_and_stops_once(self):
        check = AsyncMock()
        launch = AsyncMock(return_value={'owned': True})
        result = await qa.monitored_recording({}, launch=launch, stop=self.stop, check=check)
        self.assertEqual(result, {'owned': True})
        self.stop.assert_awaited_once()
        self.assertEqual(check.await_count, 2)

if __name__=='__main__':
    unittest.main()
