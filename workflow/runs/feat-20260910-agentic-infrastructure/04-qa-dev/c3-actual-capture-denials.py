"""Actual-recorder negative controls at the new controller/receipt boundary."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
sys.path.insert(0,str(ROOT/'tools/azure-runner'))
import execution_leases as leases
import qa_execution as qa
from evidence_manifest import probe_video
from qa_provenance import CaptureHeld
from qa_transport import Policy,Destination
module_spec=importlib.util.spec_from_file_location('c3_fixture',OUT/'c3-capture-fixture.py')
module=importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(module)


async def main():
    dsn=os.environ['QA_PROOF_ADMIN_DSN']
    parsed=urlsplit(dsn)
    if (os.environ.get('QA_PROOF_DISPOSABLE_ONLY')!='1' or parsed.hostname not in {'localhost','127.0.0.1'}
            or parsed.port==5432 or parsed.path!='/lantern_validation'):
        raise RuntimeError('non-designated database refused')
    admin=await asyncpg.connect(dsn)
    db='lantern_c3_qa_denial_'+uuid4().hex
    await admin.execute('CREATE DATABASE '+db)
    conn=await asyncpg.connect(dsn.rsplit('/',1)[0]+'/'+db)
    fixture=None
    result=dict(kind='actual_recorder_controller_negative_controls',test_only=True,transport_mode='direct_fixture',
                external_transport_verified=False,gateway_accepted=False,registered_fleet_execution=False,results=[])
    try:
        await conn.execute((ROOT/'tools/azure-runner/schema.sql').read_text())
        run='test-qa-denials-'+uuid4().hex
        await conn.execute("INSERT INTO runs(id,brief,pipeline_version,current_stage,created_by) VALUES($1,'actual recorder negative fixtures','test','04-qa-dev','test')",run)
        parent=await leases.acquire_run(conn,run,'qa-denials',ttl=900)
        approvals=await conn.fetch('SELECT * FROM approvals')
        fixture=module.Fixture()
        await fixture.start()
        for attempt,scenario in enumerate(('failed_assertion','deployment_drift','lease_loss'),1):
            key=f'{run}:04-qa-dev:{attempt}'
            eid=await conn.fetchval("INSERT INTO stage_executions(run_id,stage,runner,attempt,idempotency_key,status) VALUES($1,'04-qa-dev','disposable-actual-recorder',$2,$3,'running') RETURNING id",run,attempt,key)
            lease=await leases.acquire_execution(conn,parent,eid,ttl=600)
            actions=fixture.actions()
            if scenario=='failed_assertion': actions[-1]['text']='Intentionally absent expected value'
            media=OUT/'media'/f'c3-fleet-denial-{fixture.id}-{scenario}'
            authority=Path(os.environ['QA_PROOF_AUTHORITY'])/(fixture.id+'-'+scenario)
            value=dict(policy=Policy(key,[Destination(fixture.origin,(fixture.ip,),time.time()+500)],test_only=True).document(),
                deployment=await fixture.observe(),requirements=['AC-10','AC-11'],images=dict(gateway=None,recorder=fixture.recorder_image),
                ca_fingerprint=fixture.ca,authority=str(authority),media=str(media),transport_mode='direct_fixture',
                viewport=dict(width=1280,height=720),actions=actions)
            observed={}
            calls=0
            stopped=False
            async def launch(plan):
                answer=await fixture.record(plan,media)
                observed.update(answer)
                if scenario=='lease_loss':
                    await conn.execute('UPDATE stage_executions SET lease_fence=lease_fence+1 WHERE id=$1',eid)
                return answer
            async def stop():
                nonlocal stopped
                for name in fixture.recorder_names:
                    module.docker('rm','-f',name,check=False)
                    assert module.docker('inspect',name,check=False).returncode!=0
                stopped=True
            async def observe():
                nonlocal calls
                calls+=1
                answer=await fixture.observe()
                if scenario=='deployment_drift' and calls==2:
                    answer['revision']='0'*40
                return answer
            try:
                await qa.execute_capture(conn,lease,value,launch=launch,stop=stop,observe_deployment=observe,allow_direct_fixture=True)
            except (CaptureHeld,leases.LeaseLost) as error:
                error_class=type(error).__name__
            else:
                raise AssertionError(scenario+' unexpectedly accepted')
            assert stopped and observed['writers_closed'] is True
            assert not await conn.fetchval('SELECT output FROM stage_executions WHERE id=$1',eid)
            assert not authority.exists() or not list(authority.glob('*.json'))
            video=media/observed['files']['video']
            metadata=probe_video(video)
            offset=round(metadata['duration_seconds']-.2,2)
            frame=media/('frame-'+str(offset)+'.png')
            subprocess.run(['ffmpeg','-v','error','-n','-ss',str(offset),'-i',str(video),'-frames:v','1',str(frame)],check=True)
            result['results'].append(dict(scenario=scenario,passed=True,denial=error_class,recording_id=observed['recording_id'],
                all_recorded_commands_passed=all(x['passed'] for x in observed['outcomes']),outcomes=observed['outcomes'],
                controller_receipt_absent=True,durable_receipt_absent=True,recorder_quiesced=True,
                video=dict(path=str(video.relative_to(OUT)).replace('\\','/'),sha256=hashlib.sha256(video.read_bytes()).hexdigest(),**metadata),
                trace=dict(path=str((media/observed['files']['trace']).relative_to(OUT)).replace('\\','/'),sha256=hashlib.sha256((media/observed['files']['trace']).read_bytes()).hexdigest()),
                frame=dict(path=str(frame.relative_to(OUT)).replace('\\','/'),seconds=offset,sha256=hashlib.sha256(frame.read_bytes()).hexdigest())))
            try: await leases.release(conn,lease,'failed')
            except leases.LeaseLost: pass
        assert await conn.fetch('SELECT * FROM approvals')==approvals
        result.update(passed=True,approvals_unchanged=True)
    finally:
        if fixture: result['fixture_cleanup']=fixture.close()
        await conn.close()
        await admin.execute('DROP DATABASE '+db)
        await admin.close()
        result.update(new_test_database_removed=True,configured_database_touched=False)
        result['source_sha256']={name:hashlib.sha256((ROOT/'tools/azure-runner'/name).read_bytes()).hexdigest()
                                for name in ('qa_execution.py','qa_provenance.py','execution_leases.py')}
        (OUT/'c3-actual-capture-denials.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=result['passed'],count=len(result['results']),actual_browser_recordings=len(result['results']))))


if __name__=='__main__':
    asyncio.run(main())
