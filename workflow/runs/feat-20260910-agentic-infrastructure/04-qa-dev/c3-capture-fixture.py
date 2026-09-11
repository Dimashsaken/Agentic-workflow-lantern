"""Owned direct-TLS substrate for c3 fleet-capture integration; never external acceptance.

Every target/image/credential comes from caller environment. Only fresh names are
created; existing evidence is never removed. The fixture private key is temporary.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

SERVER = '''import http.server, ssl, time
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path == '/ready':
   time.sleep(.6)
  body = b'<!doctype html><html><body style="font:24px sans-serif;padding:60px"><h1>Lantern fleet capture fixture</h1><label>Test secret <input type="password" id="secret"></label><p id="status">Controller fixture ready</p><script>setTimeout(()=>{const p=document.createElement("p");p.id="complete";p.textContent="Recorded steps completed";document.body.appendChild(p)},2200)</script></body></html>'
  self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers(); self.wfile.write(body)
 def log_message(self,*args): pass
s=http.server.HTTPServer(('0.0.0.0',PORT),Handler)
c=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); c.load_cert_chain('/fixture/server.pem','/fixture/server.key')
s.socket=c.wrap_socket(s.socket,server_side=True); s.serve_forever()
'''


def docker(*args, check=True, timeout=180):
    result = subprocess.run([os.environ['QA_PROOF_DOCKER'], *args], capture_output=True,
                            text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('owned fixture Docker command failed (detail redacted)')
    return result


def create_certificates(root, hostname):
    now = datetime.now(timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Lantern disposable fleet QA CA')])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
          .not_valid_after(now+timedelta(hours=2)).add_extension(x509.BasicConstraints(ca=True,path_length=0),True)
          .add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),True).sign(key,hashes.SHA256()))
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,hostname)]))
              .issuer_name(name).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=1))
              .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]),False).sign(key,hashes.SHA256()))
    (root/'ca.pem').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (root/'server.pem').write_bytes(server.public_bytes(serialization.Encoding.PEM))
    (root/'server.key').write_bytes(server_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    return ca.fingerprint(hashes.SHA256()).hex()


class Fixture:
    def __init__(self):
        if os.environ.get('QA_PROOF_DISPOSABLE_ONLY') != '1':
            raise RuntimeError('explicit disposable fixture configuration required')
        self.origin = os.environ['QA_PROOF_ORIGIN']
        parsed = urlsplit(self.origin)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or not parsed.hostname.endswith('.test')):
            raise RuntimeError('only an environment-injected .test HTTPS fixture is accepted')
        self.hostname, self.port = parsed.hostname, parsed.port or 443
        self.id = uuid4().hex
        self.network, self.name = ['lantern-c3-qa-'+x+'-'+self.id[:12] for x in ('network','fixture')]
        self.recorder_names = []
        self.private = tempfile.TemporaryDirectory(prefix='lantern-c3-qa-fixture-')
        self.root = Path(self.private.name)
        self.public = self.root/'public'
        self.public.mkdir()
        self.ca = create_certificates(self.root, self.hostname)
        (self.public/'ca.pem').write_bytes((self.root/'ca.pem').read_bytes())
        self.server = SERVER.replace('PORT', str(self.port))
        (self.root/'server.py').write_text(self.server)
        self.recorder_image = docker('image','inspect',os.environ['QA_PROOF_RECORDER_IMAGE'],'--format','{{.Id}}').stdout.strip()
        self.fixture_image = docker('image','inspect',os.environ['QA_PROOF_BASE_IMAGE'],'--format','{{.Id}}').stdout.strip()
        self.started = False
        self.cleanup = {}

    async def start(self):
        docker('network','create','--internal',self.network)
        docker('run','-d','--name',self.name,'--network',self.network,'--network-alias',self.hostname,
               '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--user','1000:1000',
               '--mount',f'type=bind,source={self.root.as_posix()},target=/fixture,readonly',
               '--entrypoint','/opt/lantern/venv/bin/python',self.fixture_image,'/fixture/server.py')
        inspect = json.loads(docker('inspect',self.name).stdout)[0]
        self.ip = inspect['NetworkSettings']['Networks'][self.network]['IPAddress']
        for _ in range(30):
            ready = docker('exec',self.name,'/opt/lantern/venv/bin/python','-c',
                           f"import socket; socket.create_connection(('127.0.0.1',{self.port}),1).close()",check=False)
            if ready.returncode == 0:
                self.started = True
                return self
            await asyncio.sleep(.2)
        raise RuntimeError('designated disposable TLS fixture did not become ready')

    async def observe(self):
        row = json.loads(docker('inspect',self.name).stdout)[0]
        if row['State']['Running'] is not True or row['Image'] != self.fixture_image:
            raise RuntimeError('controller fixture deployment changed')
        revision = hashlib.sha256((self.root/'server.py').read_bytes()).hexdigest()
        return dict(deployment_id=self.name, revision=revision, origin=self.origin, descriptor_id='controller:'+self.id)

    def actions(self):
        self.sentinel = 'DO-NOT-PERSIST-'+uuid4().hex
        return [dict(id='navigate',requirement='AC-10',kind='navigate',url=self.origin+'/ready'),
                dict(id='heading',requirement='AC-10',kind='assert_text',selector='h1',text='Lantern fleet capture fixture'),
                dict(id='secret',requirement='AC-11',kind='fill',selector='#secret',value=self.sentinel),
                dict(id='status',requirement='AC-11',kind='assert_text',selector='#status',text='Controller fixture ready'),
                dict(id='complete',requirement='AC-11',kind='assert_text',selector='#complete',text='Recorded steps completed')]

    async def record(self, plan, media):
        plan_dir = self.root/('plan-'+plan['recording_id'])
        plan_dir.mkdir()
        (plan_dir/'recording.json').write_text(json.dumps(plan))
        media = Path(media)
        media.mkdir(parents=True,exist_ok=False)
        name = 'lantern-c3-qa-recorder-'+plan['recording_id'][:12]
        self.recorder_names.append(name)
        argv = [os.environ['QA_PROOF_DOCKER'],'run','--name',name,'--network',self.network,
                '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--user','1000:1000',
                '--tmpfs','/tmp:rw,nosuid,nodev,size=256m','--tmpfs','/home/worker:rw,nosuid,nodev,size=64m,uid=1000,gid=1000',
                '--mount',f'type=bind,source={self.public.as_posix()},target=/trust,readonly',
                '--mount',f'type=bind,source={plan_dir.as_posix()},target=/plan,readonly',
                '--mount',f'type=bind,source={media.as_posix()},target=/recordings',self.recorder_image]
        process = await asyncio.create_subprocess_exec(*argv,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        completed = asyncio.create_task(process.communicate())
        try:
            stdout, _ = await asyncio.shield(completed)
        except asyncio.CancelledError:
            docker('rm','-f',name,check=False)
            while not completed.done():
                try:
                    await asyncio.shield(completed)
                except asyncio.CancelledError:
                    continue
            raise
        if process.returncode:
            raise RuntimeError('owned recorder failed (detail redacted)')
        result = json.loads(stdout)
        result['files'] = dict(video=plan['recording_id']+'.webm',trace=plan['recording_id']+'.trace.json')
        assert self.sentinel not in (media/result['files']['trace']).read_text()
        assert self.sentinel.encode() not in stdout
        state = json.loads(docker('inspect',name).stdout)[0]['State']
        assert state['Running'] is False and state['ExitCode'] == 0
        return result

    def close(self):
        for name in [*self.recorder_names,self.name]:
            docker('rm','-f',name,check=False)
        docker('network','rm',self.network,check=False)
        self.cleanup['containers_removed'] = all(docker('inspect',name,check=False).returncode != 0
                                                  for name in [*self.recorder_names,self.name])
        self.cleanup['network_removed'] = docker('network','inspect',self.network,check=False).returncode != 0
        self.private.cleanup()
        self.cleanup['temporary_private_trust_removed'] = not self.root.exists()
        return self.cleanup
