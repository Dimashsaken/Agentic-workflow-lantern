"""Actual direct TLS recorder fixture; explicitly NOT gateway/egress acceptance.

Creates only named ephemeral Docker resources and a disposable test database.
No application credentials, host trust changes, live gates or external target.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import asyncpg
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
sys.path.insert(0, str(ROOT/'tools/azure-runner'))
import execution_leases as leases
from qa_provenance import Capture, CaptureHeld, Identity, persist, verify
from qa_transport import Destination, Policy

SERVER = '''import http.server, ssl
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  html=b'<!doctype html><html><body style="font:24px sans-serif;padding:60px"><h1>Lantern TLS capture fixture</h1><p>Certificate verified in ephemeral browser trust.</p><label>Test credential <input type="password" id="secret"></label><p id="status">Capture ready</p></body></html>'
  self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers(); self.wfile.write(html)
 def log_message(self,*args): pass
s=http.server.HTTPServer(('0.0.0.0',8443),Handler)
c=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); c.load_cert_chain('/fixture/server.pem','/fixture/server.key')
s.socket=c.wrap_socket(s.socket,server_side=True); s.serve_forever()
'''


def docker(*args, check=True, timeout=180):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('Docker fixture command failed: '+result.stderr[-1000:])
    return result


def certs(root):
    now = datetime.now(timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Lantern disposable capture CA')])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
          .not_valid_after(now+timedelta(hours=2)).add_extension(x509.BasicConstraints(ca=True,path_length=0),True)
          .add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),True).sign(key,hashes.SHA256()))
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'qa-fixture.test')]))
              .issuer_name(name).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=1))
              .add_extension(x509.SubjectAlternativeName([x509.DNSName('qa-fixture.test')]),False)
              .sign(key,hashes.SHA256()))
    (root/'ca.pem').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (root/'server.pem').write_bytes(server.public_bytes(serialization.Encoding.PEM))
    (root/'server.key').write_bytes(server_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    return ca.fingerprint(hashes.SHA256()).hex()


async def proof():
    recording = uuid4().hex
    network, fixture, recorder = ['lantern-capture-'+x+'-'+recording[:12] for x in ('net','fixture','recorder')]
    media = ROOT/'workflow/runs/feat-20260910-agentic-infrastructure/04-qa-dev/media'/('bcd-tls-'+recording)
    authority = Path.home()/'.lantern/authority/bcd-capture'/recording
    media.mkdir(parents=True)
    image = docker('image','inspect','lantern-qa-recorder:continuation-3','--format','{{.Id}}').stdout.strip()
    base = docker('image','inspect','lantern-sandbox:agentic-infrastructure','--format','{{.Id}}').stdout.strip()
    params = dict(host='127.0.0.1',port=55432,user='lantern',password=Path(os.environ['LANTERN_TEST_DB_PASSWORD_FILE']).read_text().strip())
    db = 'lantern_capture_'+recording
    admin = await asyncpg.connect(**params,database='lantern_validation')
    conn = None
    created = False
    result = {'kind':'local_direct_tls_recorder_proof','test_only':True,'external_transport_verified':False,
              'gateway_accepted':False,'recording_id':recording,'recorder_image':image,'fixture_image':base}
    try:
        await admin.execute('CREATE DATABASE '+db)
        created = True
        conn = await asyncpg.connect(**params,database=db)
        await conn.execute((ROOT/'tools/azure-runner/schema.sql').read_text())
        run = 'test-capture-'+recording
        key = run+':04-qa-dev:1'
        await conn.execute("INSERT INTO runs(id,brief,pipeline_version,current_stage,created_by) VALUES($1,'disposable TLS fixture','test','04-qa-dev','test')",run)
        parent = await leases.acquire_run(conn,run,'capture-fixture',ttl=600)
        execution = await conn.fetchval("INSERT INTO stage_executions(run_id,stage,runner,attempt,idempotency_key,status) VALUES($1,'04-qa-dev','local-fixture',1,$2,'running') RETURNING id",run,key)
        lease = await leases.acquire_execution(conn,parent,execution,ttl=600)
        identity = Identity(run,key,execution,1,lease.fence)
        approvals_before = await conn.fetch('SELECT * FROM approvals')
        with tempfile.TemporaryDirectory(prefix='lantern-tls-capture-') as temporary:
            temp = Path(temporary)
            fingerprint = certs(temp)
            (temp/'server.py').write_bytes(SERVER.encode())
            trust, plan_dir = temp/'public', temp/'plan'
            trust.mkdir(); plan_dir.mkdir()
            (trust/'ca.pem').write_bytes((temp/'ca.pem').read_bytes())
            docker('network','create','--internal',network)
            docker('run','-d','--name',fixture,'--network',network,'--network-alias','qa-fixture.test',
                   '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--user','1000:1000',
                   '--mount',f'type=bind,source={temp.as_posix()},target=/fixture,readonly',
                   '--entrypoint','/opt/lantern/venv/bin/python',base,'/fixture/server.py')
            inspect = json.loads(docker('inspect',fixture).stdout)[0]
            ip = inspect['NetworkSettings']['Networks'][network]['IPAddress']
            origin = 'https://qa-fixture.test:8443'
            policy = Policy(key,[Destination(origin,(ip,),time.time()+1200)],test_only=True).document()
            deploy = dict(deployment_id=fixture,revision=hashlib.sha256(SERVER.encode()).hexdigest(),origin=origin,descriptor_id='controller:'+recording)
            sentinel = 'DO-NOT-PERSIST-'+uuid4().hex
            actions = [dict(id='navigate',requirement='AC-1',kind='navigate',url=origin),
                       dict(id='heading',requirement='AC-1',kind='assert_text',selector='h1',text='Lantern TLS capture fixture'),
                       dict(id='credential',requirement='AC-2',kind='fill',selector='#secret',value=sentinel),
                       dict(id='status',requirement='AC-2',kind='assert_text',selector='#status',text='Capture ready')]
            plan = dict(recording_id=recording,viewport=dict(width=1280,height=720),origins=[origin],actions=actions)
            (plan_dir/'recording.json').write_text(json.dumps(plan))
            capture = Capture(identity,authority,media,policy,deploy,['AC-1','AC-2'],gateway_image=None,
                              recorder_image=image,ca_fingerprint=fingerprint,recording_id=recording,transport_mode='direct_fixture')
            # Probe the fixture listener before launching the recorder, without trusting its application claims.
            for _ in range(30):
                ready = docker('exec',fixture,'/opt/lantern/venv/bin/python','-c',"import socket; socket.create_connection(('127.0.0.1',8443),1).close()",check=False)
                if ready.returncode == 0: break
                await asyncio.sleep(.2)
            else: raise RuntimeError('fixture not ready')
            run_result = await asyncio.to_thread(docker,'run','--name',recorder,'--network',network,
                '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--user','1000:1000',
                '--tmpfs','/tmp:rw,nosuid,nodev,size=256m','--tmpfs','/home/worker:rw,nosuid,nodev,size=64m,uid=1000,gid=1000',
                '--mount',f'type=bind,source={trust.as_posix()},target=/trust,readonly',
                '--mount',f'type=bind,source={plan_dir.as_posix()},target=/plan,readonly',
                '--mount',f'type=bind,source={media.as_posix()},target=/recordings',image)
            observed = json.loads(run_result.stdout.strip())
            assert observed['recording_id'] == recording
            for outcome in observed['outcomes']:
                capture.outcome(outcome['command_id'],outcome['requirement'],outcome['passed'])
            assert hashlib.sha256((temp/'server.py').read_bytes()).hexdigest() == deploy['revision']
            files = dict(video=recording+'.webm',trace=recording+'.trace.json')
            assert sentinel not in (media/files['trace']).read_text() and sentinel not in run_result.stdout
            sealed = capture.seal(deploy,files,writers_closed=observed['writers_closed'])
            await persist(conn,lease,sealed)
            for field, wrong in [('attempt',2),('execution_key',key+'-wrong')]:
                try: await persist(conn,lease,{**sealed,field:wrong})
                except CaptureHeld: pass
                else: raise AssertionError('wrong durable identity accepted')
            saved = json.loads(await conn.fetchval('SELECT output::text FROM stage_executions WHERE id=$1',execution))['qa_capture']
            assert saved == sealed
            assert verify(authority,media,recording,identity,deploy) == sealed
            await leases.release(conn,lease,'succeeded')
            try: await persist(conn,lease,sealed)
            except leases.LeaseLost: pass
            else: raise AssertionError('stale writer accepted')
            assert await conn.fetch('SELECT * FROM approvals') == approvals_before
            expected = dict(identity=identity.document(),deployment=deploy)
            (OUT/'bcd-capture-expected.json').write_text(json.dumps(expected,indent=2)+'\n')
            result.update(passed=True,authority=str(authority),media_root=str(media),expected_file=str(OUT/'bcd-capture-expected.json'),
                identity=identity.document(),deployment=deploy,media=sealed['media'],outcomes=observed['outcomes'],
                secret_absent_from_trace=True,durable_output_matched=True,wrong_attempt_and_key_refused=True,stale_writer_refused=True,
                approvals_unchanged=True,disposable_database=db,ignore_https_errors=False,trust_scope='ephemeral recorder NSS home')
    finally:
        for name in (recorder,fixture): docker('rm','-f',name,check=False)
        docker('network','rm',network,check=False)
        result['docker_resources_removed'] = all(docker('inspect',name,check=False).returncode != 0 for name in (recorder,fixture)) and docker('network','inspect',network,check=False).returncode != 0
        if conn: await conn.close()
        if created: await admin.execute('DROP DATABASE '+db)
        await admin.close()
        result['disposable_database_removed'] = created
        (OUT/'bcd-capture-proof.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    asyncio.run(proof())
