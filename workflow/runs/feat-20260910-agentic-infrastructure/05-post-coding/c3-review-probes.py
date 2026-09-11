"""Independent local post-coding retest; no external provider or database."""
import ast
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'tools/azure-runner'))
import execution_retention as retention
import execution_runtime as ownership
import execution_leases as leases

results = []
def check(name, okay, detail=None):
    results.append({'name': name, 'passed': bool(okay), 'detail': detail})
    if not okay:
        raise AssertionError(name)

with tempfile.TemporaryDirectory(prefix='lantern-postcoding-retest-') as temporary:
    base=Path(temporary); auth=base/'authority'; clones=base/'clones'
    ready=threading.Event(); release=threading.Event(); errors=[]
    def allocate():
        try:
            with retention.allocation(clones/'slow', clones, 'slow:1', 'run', authority=auth):
                (clones/'slow').mkdir(); ready.set(); release.wait(15)
        except BaseException as error:
            errors.append(type(error).__name__+': '+str(error)); ready.set()
    thread=threading.Thread(target=allocate); thread.start(); assert ready.wait(5)
    started=time.monotonic()
    try:
        with retention.worker_mount(base/'unrelated','other:1',auth):
            pass
    finally:
        release.set(); thread.join(5)
    check('slow_clone_does_not_block_unrelated_mount', not errors and time.monotonic()-started<1,
          {'seconds':round(time.monotonic()-started,3),'errors':errors})
    legacy=clones/'late-legacy'/'child'
    retention.atomic_json(auth/('path-'+retention.path_key(legacy)+'.json'),
                          {'execution_key':'legacy:1','path':str(legacy)})
    for label, path in [('late_legacy_ancestor_held',legacy.parent),('late_legacy_other_owner_held',legacy)]:
        try:
            with retention.worker_mount(path,'other:2',auth):
                pass
        except retention.RetentionHeld:
            check(label,True)
        else:
            check(label,False)
    with retention.worker_mount(clones/'slow','slow:1',auth):
        check('registered_owner_mount_still_works',True)

# A legacy writer can add a mapping during the new writer's compatibility copies.
with tempfile.TemporaryDirectory(prefix='lantern-postcoding-index-race-') as temporary:
    base=Path(temporary);auth=base/'authority';clones=base/'clones';legacy=clones/'legacy-parent'/'child'
    real_write=retention.atomic_json;injected=[]
    def interleaved_write(path,value):
        real_write(path,value)
        if value.get('protocol')=='retention-v2-sentinel' and not injected:
            real_write(auth/('path-'+retention.path_key(legacy)+'.json'),{'execution_key':'legacy:1','path':str(legacy)})
            injected.append(True)
    with patch.object(retention,'atomic_json',interleaved_write):
        with retention.allocation(clones/'current',clones,'current:1','run',authority=auth):
            (clones/'current').mkdir()
    try:
        with retention.worker_mount(legacy.parent,'other:1',auth):
            pass
    except retention.RetentionHeld:
        check('legacy_write_during_current_allocation_held',bool(injected))
    else:
        check('legacy_write_during_current_allocation_held',False)
source=(ROOT/'tools/azure-runner/pipeline.py').read_text(encoding='utf-8')
node=next(n for n in ast.parse(source).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='insert_artifact')
namespace={'ownership':ownership,'json':json,'factory':SimpleNamespace(stage_dir=lambda value:value.split('.')[0])}
exec(compile(ast.Module(body=[node],type_ignores=[]),'<pipeline.insert_artifact>','exec'),namespace)
async def artifacts():
    token=ownership.STAGE.set(ownership.Ownership(leases.Lease('run','owner',1,42,1,True,7,'a'*64),None))
    run_token=ownership.RUN.set(None)
    try:
        for flag in ('0','1'):
            conn=AsyncMock(); conn.fetchval.return_value='03-coding.fix'; seen=[]
            @asynccontextmanager
            async def fenced(conn,lease):
                seen.append(lease.execution_id)
                yield
            with patch.dict(os.environ,{'LANTERN_EXECUTION_LEASES':flag}),patch.object(leases,'fenced_transaction',fenced):
                await namespace['insert_artifact'](conn,'run','03-coding','report','report.md')
            metadata=json.loads(conn.execute.call_args.args[-1])
            check('artifact_child_fenced_flag_'+flag,seen==[42] and metadata=={'stage_execution_id':42,'lease_fence':1},metadata)
            conn.reset_mock()
            @asynccontextmanager
            async def stale(conn,lease):
                raise leases.LeaseLost('injected stale parent')
                yield
            with patch.dict(os.environ,{'LANTERN_EXECUTION_LEASES':flag}),patch.object(leases,'fenced_transaction',stale):
                try:
                    await namespace['insert_artifact'](conn,'run','03-coding','report','report.md')
                except leases.LeaseLost:
                    check('artifact_stale_child_denied_flag_'+flag,conn.execute.await_count==0)
                else:
                    check('artifact_stale_child_denied_flag_'+flag,False)
    finally:
        ownership.STAGE.reset(token); ownership.RUN.reset(run_token)
asyncio.run(artifacts())

# Execute the production nested clone-preparation function with actual Git,
# then call the real coding handoff writer in a wholly disposable repository.
import subprocess
import review
import orchestrator
import factory
with tempfile.TemporaryDirectory(prefix='lantern-postcoding-base-') as temporary:
    base=Path(temporary); product=base/'product'; mirror=base/'mirror'; trial=base/'trial'; child=base/'checkouts'/'child'
    def git(*args,cwd=base):
        return subprocess.run(['git',*map(str,args)],cwd=cwd,capture_output=True,text=True,check=True).stdout.strip()
    git('init','-q','-b','main',product)
    git('config','user.name','Disposable Review',cwd=product);git('config','user.email','review@example.invalid',cwd=product)
    (product/'base.txt').write_text('base');git('add','.',cwd=product);git('commit','-qm','base',cwd=product)
    git('checkout','-qb','feat/example',cwd=product);(product/'feature.txt').write_text('feature');git('add','.',cwd=product);git('commit','-qm','feature',cwd=product)
    git('checkout','-q','main',cwd=product);(product/'base.txt').write_text('advanced');git('add','.',cwd=product);git('commit','-qm','advanced',cwd=product)
    base_sha=git('rev-parse','HEAD',cwd=product)
    git('clone','-q','--bare',product,mirror)
    trial_data=review.trial_merge(mirror,'main','feat/example','pc-local',('Disposable Review','review@example.invalid'),clone=trial)
    check('actual_trial_merge_is_clean',trial_data['clean'])
    definition=next(n for n in ast.parse((ROOT/'tools/azure-runner/maintenance_runtime.py').read_text()).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='run_fix')
    prepare=next(n for n in definition.body if isinstance(n,ast.FunctionDef) and n.name=='prepare')
    context={'clone':trial,'fix_clone':child,'fix_root':child.parent,'execution_key':'pc:fix:1',
             'parent':SimpleNamespace(run_id='pc-local'),'base_sha':base_sha,
             'source':{'publication_request':{'base':'main'}},'publication':SimpleNamespace(PublicationHeld=RuntimeError)}
    exec(compile(ast.Module(body=[prepare],type_ignores=[]),'<maintenance.run_fix.prepare>','exec'),context)
    with patch.dict(os.environ,{'LANTERN_RETENTION_AUTHORITY':str(base/'authority'),'LANTERN_ISOLATED_TOOLS':'0','LANTERN_TRUSTED_EVIDENCE':'0'}):
        context['prepare']()
        check('fix_clone_pins_exact_observed_base',git('rev-parse','refs/remotes/origin/main',cwd=child)==base_sha)
        (child/'feature.txt').write_text('fixed');git('add','.',cwd=child)
        git('-c','user.name=Disposable Review','-c','user.email=review@example.invalid','commit','-qm','fix',cwd=child)
        original_handoff=base/'workflow/runs/pc-local/03-coding/handoff.json';original_handoff.parent.mkdir(parents=True)
        original_handoff.write_text('retain earlier handoff')
        token=factory.MAINTENANCE_OUTPUT.set('independent-child')
        try:
            with patch.object(orchestrator,'REPO',base),patch.object(factory,'REPO',base),patch.dict(os.environ,
                 {'LANTERN_PRODUCT_DIR':str(child),'LANTERN_PRODUCT_WRITABLE':'1','LANTERN_CODING_BRANCH':'feat/example',
                  'LANTERN_PRODUCT_BRANCH':'main','LANTERN_CODING_START_SHA':trial_data['merge_sha'],'LANTERN_BUILDER':''}):
                problems=orchestrator.finalize_coding('pc-local','03-coding.fix')
            check('real_finalize_coding_accepts_fixed_child',not problems,problems)
            check('child_handoff_preserves_earlier_evidence',original_handoff.read_text()=='retain earlier handoff' and
                 (original_handoff.parent/'babysit/fixes/independent-child/handoff.json').is_file())
        finally:
            factory.MAINTENANCE_OUTPUT.reset(token)
        old_source=subprocess.run(['git','show','09fdb11:tools/azure-runner/execution_retention.py'],cwd=ROOT,capture_output=True,text=True,check=True).stdout
        old={'__name__':'retention_before_continuation'};exec(compile(old_source,'<retention-baseline>','exec'),old)
        for name,target,key in [('legacy_same_owner_held',child,'pc:fix:1'),('legacy_wrong_owner_held',child,'other:1'),('legacy_ancestor_held',child.parent,'other:2')]:
            try:
                with old['worker_mount'](target,key,base/'authority'):
                    pass
            except old['RetentionHeld']:
                check(name,True)
            else:
                check(name,False)
files=['tools/azure-runner/execution_retention.py','tools/azure-runner/pipeline.py','tools/azure-runner/maintenance_runtime.py','tools/azure-runner/factory.py','tools/evals/check_pr.py']
output={'kind':'independent_post_coding_local_retest','external_provider':False,'database':False,
        'scope':'Actual retention filesystem/thread API and actual artifact function with injected SQL/fence','results':results,
        'source_sha256':{file:hashlib.sha256((ROOT/file).read_bytes()).hexdigest() for file in files}}
location=Path(__file__).with_suffix('.json')
location.write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':sum(item['passed'] for item in results),'total':len(results),'output':str(location)},indent=2))
