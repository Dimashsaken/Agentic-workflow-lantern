"""Current application, copied harness and existing disposable run; no gate writes."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit

import asyncpg

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent


async def snapshot(target, runtime, before=None):
    connection = await asyncpg.connect(os.environ['LANTERN_DATABASE_URL'].replace('+asyncpg', ''), timeout=5)
    try:
        async with connection.transaction(readonly=True):
            run_id = os.environ['QA_RUN_ID']
            row = await connection.fetchrow('SELECT id,status,current_stage,updated_at FROM runs WHERE id=$1', run_id)
            approvals = await connection.fetch('SELECT id,gate,status,decided_at,decided_by FROM approvals WHERE run_id=$1 ORDER BY id', run_id)
            executions = await connection.fetch('SELECT id,stage,status,attempt,idempotency_key,input_tokens,output_tokens,total_tokens,output FROM stage_executions WHERE run_id=$1 ORDER BY id', run_id)
            assert row and row['status'] in {'waiting_gate', 'failed'}
            if row['status'] == 'waiting_gate':
                assert len(approvals) == 1 and approvals[0]['status'] == 'pending'
            else:
                assert not approvals
            result = {'run':dict(row), 'approvals':[dict(x) for x in approvals], 'executions':[dict(x) for x in executions],
                'source_sha256':{f'tools/mission-control/{n}':hashlib.sha256((runtime/'tools/mission-control'/n).read_bytes()).hexdigest() for n in ['app.py','ui.py','drawer.py','traceability.py']}}
            result = json.loads(json.dumps(result, default=str))
            target.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
            if before:
                assert json.loads(before.read_text()) == result, 'Protected state changed'
    finally:
        await connection.close()


def main():
    target = urlsplit(os.environ['QA_BASE_URL'])
    db = urlsplit(os.environ['LANTERN_DATABASE_URL'].replace('+asyncpg',''))
    assert target.hostname in {'localhost','127.0.0.1'} and db.path == '/lantern_validation'
    source = Path(os.environ['QA_RUN_ARTIFACT_ROOT']).resolve()
    assert source.name == os.environ['QA_RUN_ID'] and source.is_dir()
    runtime = Path(tempfile.mkdtemp(prefix='lantern-qa-provenance-'))
    # Tracked source plus new Python runtime modules, never dotenv or media secrets.
    paths = subprocess.check_output(['git','ls-files'], cwd=ROOT, text=True).splitlines()
    paths += [str(p.relative_to(ROOT)) for p in (ROOT/'tools/azure-runner').glob('*.py')]
    for relative in set(paths):
        p = Path(relative)
        if p.parts[:2] == ('workflow','runs') or p.name == '.env':
            continue
        dest = runtime/p
        if (ROOT/p).is_file():
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/p,dest)
    shutil.copytree(source,runtime/'workflow/runs'/source.name)
    before = OUT/os.environ['QA_BEFORE_FILE']
    after = OUT/os.environ['QA_AFTER_FILE']
    asyncio.run(snapshot(before,runtime))
    env = dict(os.environ)
    env['QA_USER']='local-qa'
    env['QA_PASS']=secrets.token_hex(32)
    env['LANTERN_WEB_USERS']=env['QA_USER']+':'+env['QA_PASS']
    env['LANTERN_WEB_SECRET']=secrets.token_hex(32)
    env['LANTERN_EXECUTION_LEASES']='0'
    env['LANTERN_ISOLATED_TOOLS']='0'
    with (runtime/'service.log').open('w',encoding='utf-8') as log:
        server = subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host',target.hostname,'--port',str(target.port)],cwd=runtime/'tools/mission-control',env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(40):
                if server.poll() is not None:
                    raise RuntimeError('Local app exited; inspect ignored service.log')
                try:
                    with urllib.request.urlopen(os.environ['QA_BASE_URL']+'/login',timeout=2) as response:
                        if response.status == 200: break
                except OSError:
                    time.sleep(.25)
            else:
                raise RuntimeError('Local app readiness failed')
            completed = subprocess.run([os.environ['QA_NODE'],str(ROOT/'tools/qa-recorder/agent-infrastructure-live.mjs')],env=env)
            asyncio.run(snapshot(after,runtime,before))
            assert completed.returncode == 0, 'Browser assertions failed; evidence retained'
        finally:
            server.terminate()
            server.wait(timeout=15)
    print('Actual app QA complete; protected state unchanged; server stopped')


if __name__ == '__main__':
    main()
