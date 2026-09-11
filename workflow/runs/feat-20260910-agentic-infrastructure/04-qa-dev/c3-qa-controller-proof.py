"""Independent real-SQL QA controller probes; optional real direct-TLS recording.

Disposable environment settings only. No live model/gate/provider/deployment claim.
"""
import asyncio
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from urllib.parse import urlsplit
from uuid import uuid4
from unittest.mock import patch

import asyncpg

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
sys.path.insert(0,str(ROOT/'tools/azure-runner'))
import execution_leases as leases
import qa_execution as qa
from qa_provenance import CaptureHeld, Identity, verify
from qa_transport import Policy, Destination, TransportHeld


async def proof(actual_capture=False):
    dsn = os.environ['QA_PROOF_ADMIN_DSN']
    parsed = urlsplit(dsn)
    if (os.environ.get('QA_PROOF_DISPOSABLE_ONLY') != '1' or parsed.hostname not in {'127.0.0.1','localhost'}
            or parsed.port == 5432 or parsed.path != '/lantern_validation'):
        raise RuntimeError('refusing non-designated disposable database')
    origin = os.environ['QA_PROOF_ORIGIN']
    if not urlsplit(origin).hostname.endswith('.test'):
        raise RuntimeError('only an environment-injected test target is allowed')
    admin = await asyncpg.connect(dsn)
    database = 'lantern_c3_qa_'+uuid4().hex
    await admin.execute('CREATE DATABASE '+database)
    conn = await asyncpg.connect(dsn.rsplit('/',1)[0]+'/'+database)
    result = dict(kind='independent_disposable_sql_qa_controller_proof',registered_fleet_execution=False,
                  controller_entry='qa_execution.execute_capture',actual_browser_capture=actual_capture,
                  gateway_accepted=False,external_transport_verified=False,test_only=True,results=[])
    fixture = None
    temporary = tempfile.TemporaryDirectory(prefix='lantern-c3-qa-controller-')
    try:
        await conn.execute((ROOT/'tools/azure-runner/schema.sql').read_text())
        run = 'test-qa-controller-'+uuid4().hex
        await conn.execute("INSERT INTO runs(id,brief,pipeline_version,current_stage,created_by) VALUES($1,'disposable QA controller','test','04-qa-dev','test')",run)
        parent = await leases.acquire_run(conn,run,'qa-controller-proof',ttl=900)
        approvals_before = await conn.fetch('SELECT * FROM approvals')
        count = 0

        async def execution(stage='04-qa-dev'):
            nonlocal count
            count += 1
            key = f'{run}:{stage}:{count}'
            eid = await conn.fetchval("INSERT INTO stage_executions(run_id,stage,runner,attempt,idempotency_key,status) VALUES($1,$2,'disposable-local-test',$3,$4,'running') RETURNING id",run,stage,count,key)
            lease = await leases.acquire_execution(conn,parent,eid,ttl=600)
            return lease,key

        def spec(key):
            folder = Path(temporary.name)/uuid4().hex
            now = time.time()
            return dict(policy=Policy(key,[Destination(origin,('127.0.0.1',),now+500)],test_only=True).document(),
                deployment=dict(deployment_id='owned-fixture',revision='a'*40,origin=origin,descriptor_id='controller-fixture'),
                requirements=['AC-10'],images=dict(gateway=None,recorder='sha256:'+'b'*64),ca_fingerprint='c'*64,
                authority=str(folder/'authority'),media=str(folder/'media'),transport_mode='direct_fixture',
                viewport=dict(width=1280,height=720),actions=[dict(id='navigate',requirement='AC-10',kind='navigate',url=origin)])

        async def negative(name,mutate=None,*,stage='04-qa-dev',allow=True,launch_mutate=None,observe_mutate=None,pre=None):
            lease,key = await execution(stage)
            value=spec(key)
            if mutate: mutate(value)
            events=[]
            async def launch(plan):
                events.append('launch')
                answer=dict(recording_id=plan['recording_id'],writers_closed=True,files=dict(video='unused.webm',trace='unused.trace.json'),
                            outcomes=[dict(command_id=a['id'],requirement=a['requirement'],passed=True) for a in plan['actions']])
                if launch_mutate: await launch_mutate(answer,lease)
                return answer
            async def stop(): events.append('stop')
            async def observe():
                events.append('observe')
                answer=deepcopy(value['deployment'])
                if observe_mutate: observe_mutate(answer,events)
                return answer
            if pre: await pre(lease)
            try:
                await qa.execute_capture(conn,lease,value,launch=launch,stop=stop,observe_deployment=observe,allow_direct_fixture=allow)
            except (CaptureHeld,leases.LeaseLost,TransportHeld):
                pass
            else:
                raise AssertionError(name+' unexpectedly accepted')
            saved=await conn.fetchval('SELECT output FROM stage_executions WHERE id=$1',lease.execution_id)
            assert not saved or 'qa_capture' not in json.loads(saved)
            if 'launch' in events: assert events.count('stop')==1
            result['results'].append(dict(scenario=name,passed=True,launched='launch' in events,quiesced='stop' in events))
            try: await leases.release(conn,lease,'failed')
            except leases.LeaseLost: pass

        await negative('direct_fixture_requires_explicit_test_injection',allow=False)
        await negative('non_qa_execution_rejected',stage='03-coding')
        await negative('wrong_execution_key_rejected',lambda v:v['policy'].update(execution_key='wrong'))
        await negative('unaccepted_external_gateway_has_zero_launches',lambda v:(v.update(transport_mode='gateway'),v['images'].update(gateway='sha256:'+'d'*64)))
        await negative('missing_requirement_mapping_has_zero_launches',lambda v:v.update(requirements=['AC-10','AC-11']))
        await negative('changed_start_descriptor_has_zero_launches',observe_mutate=lambda d,e:d.update(revision='f'*40))
        async def wrong_recording(a,l): a['recording_id']='0'*32
        await negative('wrong_recording_outcome_quiesces_before_hold',launch_mutate=wrong_recording)
        async def open_writers(a,l): a['writers_closed']=False
        await negative('open_writers_quiesce_before_hold',launch_mutate=open_writers)
        async def extra_outcome(a,l): a['outcomes'].append(dict(a['outcomes'][0]))
        await negative('extra_outcome_quiesces_before_hold',launch_mutate=extra_outcome)
        async def nonboolean(a,l): a['outcomes'][0]['passed']=1
        await negative('non_boolean_outcome_quiesces_before_hold',launch_mutate=nonboolean)
        async def fail_requirement(a,l): a['outcomes'][0]['passed']=False
        await negative('failed_requirement_has_no_receipt',launch_mutate=fail_requirement)
        await negative('changed_end_descriptor_has_no_receipt',observe_mutate=lambda d,e:d.update(revision='e'*40) if e.count('observe')==2 else None)
        async def stale(l): await conn.execute('UPDATE stage_executions SET lease_fence=lease_fence+1 WHERE id=$1',l.execution_id)
        await negative('stale_owner_before_launch_has_no_receipt',pre=stale)
        async def lose(a,l): await stale(l)
        await negative('lease_loss_during_capture_quiesces_and_holds',launch_mutate=lose)
        await negative('expired_policy_has_zero_launches',lambda v:(v['policy'].update(created_at=time.time()-100),v['policy']['destinations'][0].update(expires_at=time.time()-1)))

        lease,key = await execution()
        value=spec(key)
        launched,stopping,stopped=asyncio.Event(),asyncio.Event(),asyncio.Event()
        async def cancelled_launch(plan):
            launched.set()
            await asyncio.Future()
        async def slow_stop():
            stopping.set()
            await asyncio.sleep(.05)
            stopped.set()
        async def observation(): return value['deployment']
        task=asyncio.create_task(qa.execute_capture(conn,lease,value,launch=cancelled_launch,stop=slow_stop,observe_deployment=observation,allow_direct_fixture=True))
        await launched.wait(); task.cancel(); await stopping.wait(); task.cancel()
        try: await task
        except asyncio.CancelledError: pass
        else: raise AssertionError('cancelled capture unexpectedly accepted')
        assert stopped.is_set()
        assert not await conn.fetchval('SELECT output FROM stage_executions WHERE id=$1',lease.execution_id)
        await leases.release(conn,lease,'failed')
        result['results'].append(dict(scenario='repeated_cancellation_joins_stop_before_return',passed=True,launched=True,quiesced=True))

        if actual_capture:
            module_spec=importlib.util.spec_from_file_location('c3_capture_fixture',OUT/'c3-capture-fixture.py')
            module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
            fixture=module.Fixture()
            await fixture.start()
            lease,key=await execution()
            value=spec(key)
            deployment=await fixture.observe()
            value.update(policy=Policy(key,[Destination(origin,(fixture.ip,),time.time()+600)],test_only=True).document(),
                         deployment=deployment,requirements=['AC-10','AC-11'],images=dict(gateway=None,recorder=fixture.recorder_image),
                         ca_fingerprint=fixture.ca,actions=fixture.actions(),
                         authority=str(Path(os.environ['QA_PROOF_AUTHORITY'])/fixture.id),media=str(OUT/'media'/('c3-fleet-'+fixture.id)))
            async def launch(plan): return await fixture.record(plan,value['media'])
            async def stop():
                for name in fixture.recorder_names:
                    module.docker('rm','-f',name)
                    assert module.docker('inspect',name,check=False).returncode != 0
            record=await qa.execute_capture(conn,lease,value,launch=launch,stop=stop,observe_deployment=fixture.observe,allow_direct_fixture=True)
            saved=json.loads(await conn.fetchval('SELECT output FROM stage_executions WHERE id=$1',lease.execution_id))['qa_capture']
            assert saved==record
            identity=Identity(run,key,lease.execution_id,record['attempt'],lease.fence)
            assert verify(value['authority'],value['media'],record['recording_id'],identity,deployment)==record
            assert record['test_only'] is True and record['transport_mode']=='direct_fixture'
            result.update(media=record['media'],media_root=str(Path(value['media']).relative_to(OUT)),recording_id=record['recording_id'],
                          identity=identity.document(),deployment_sha256=record['deployment_sha256'],images=record['images'],
                          receipt_sha256=hashlib.sha256((Path(value['authority'])/(record['recording_id']+'.json')).read_bytes()).hexdigest(),
                          secret_absent=True,writers_quiesced=True,transport_mode='direct_fixture',durable_receipt_matches=True)
            result['results'].append(dict(scenario='actual_direct_tls_recorder_sealed_by_fleet_controller_and_persisted',passed=True))
            await leases.release(conn,lease,'succeeded')
        assert await conn.fetch('SELECT * FROM approvals')==approvals_before
        result['approvals_unchanged']=True
        result['passed']=all(item['passed'] for item in result['results'])
    finally:
        if fixture: result['fixture_cleanup']=fixture.close()
        temporary.cleanup()
        await conn.close()
        await admin.execute('DROP DATABASE '+database)
        await admin.close()
        result['new_test_database_removed']=True
        result['configured_database_touched']=False
        result['source_sha256']={name:hashlib.sha256((ROOT/'tools/azure-runner'/name).read_bytes()).hexdigest()
                                for name in ['qa_execution.py','qa_provenance.py','qa_transport.py','execution_leases.py']}
        name='c3-qa-controller-capture.json' if actual_capture else 'c3-qa-controller-sql.json'
        (OUT/name).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=result['passed'],count=len(result['results']),actual_browser_capture=actual_capture)))


if __name__=='__main__':
    asyncio.run(proof('--capture' in sys.argv))
