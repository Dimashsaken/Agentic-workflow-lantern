"""Real candidate-image TLS regression; disposable --network=none container only.

Run as root in a throwaway container so its certifi bundle can gain a fixture CA.
The gateway child itself runs as UID/GID 1000 with the actual entrypoint/options.
Loopback TLS is test-only: this does not certify Docker egress or external launch.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import http.server
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import threading
import time

import certifi
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path('/tmp/image-hook-test')
ROOT.mkdir(mode=0o755)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Test upstream CA')])
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
now = datetime.now(timezone.utc)
ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
      .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
      .not_valid_after(now+timedelta(hours=1)).add_extension(x509.BasicConstraints(ca=True,path_length=0),True)
      .sign(key,hashes.SHA256()))
public = ca.public_bytes(serialization.Encoding.PEM)
# Disposable test bundle; never change host/image/recorder trust.
with open(certifi.where(), 'ab') as bundle:
    bundle.write(public)

def server_cert(host, *, expired=False, untrusted=False):
    leafkey = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,host)]))
            .issuer_name(name).public_key(leafkey.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-timedelta(hours=2))
            .not_valid_after(now-timedelta(minutes=1) if expired else now+timedelta(minutes=30))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]),False).sign(rsa.generate_private_key(public_exponent=65537,key_size=2048) if untrusted else key,hashes.SHA256()))
    pem = ROOT / (host + ('-expired' if expired else '') + '.pem')
    pem.write_bytes(leafkey.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()) + leaf.public_bytes(serialization.Encoding.PEM))
    return pem

class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, pem):
        super().__init__(('127.0.0.1',0), Handler)
        self.connections = self.requests = 0
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(pem)
    def get_request(self):
        sock, addr = self.socket.accept()
        self.connections += 1
        try:
            return self.ctx.wrap_socket(sock,server_side=True),addr
        except Exception:
            sock.close(); raise

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def do_GET(self):
        self.server.requests += 1
        self.send_response(200); self.send_header('Content-Length','2'); self.end_headers(); self.wfile.write(b'OK')
    def log_message(self,*args): pass

servers=[]
for host,expired in [('allowed.example',False),('wrong.example',False),('allowed.example',True),('untrusted.example',False)]:
    server=Server(server_cert('allowed.example' if host=='untrusted.example' else host,expired=expired,untrusted=host=='untrusted.example')); servers.append(server)
    threading.Thread(target=server.serve_forever,daemon=True).start()

sequence=0
@contextmanager
def gateway(server, *, ttl=30):
    global sequence
    sequence += 1
    ca_path=Path('/tmp/qa-ca')
    if ca_path.exists(): ca_path.rename(ROOT / ('retired-ca-'+str(sequence)))
    policy=Path('/policy'); policy.mkdir(exist_ok=True)
    port=server.server_port
    created=time.time()
    (policy/'policy.json').write_text(json.dumps({'version':1,'execution_key':'image-test-'+str(sequence),
        'created_at':created,'test_only':True,'destinations':[{'origin':f'https://allowed.example:{port}',
        'addresses':['127.0.0.1'],'expires_at':created+ttl}]}))
    (policy/'policy.json').chmod(0o644)
    def identity(): os.setgid(1000); os.setuid(1000)
    process=subprocess.Popen([sys.executable,'/opt/gateway/entrypoint.py'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             preexec_fn=identity,env={'PATH':'/opt/gateway/bin:/usr/bin:/bin','HOME':'/tmp'})
    try:
        for _ in range(120):
            if process.poll() is not None:
                raise AssertionError('gateway startup failed: '+process.communicate()[1].decode()[:2000])
            if (ca_path/'mitmproxy-ca-cert.pem').exists():
                try:
                    with socket.create_connection(('127.0.0.1',8080),timeout=.2): break
                except OSError: pass
            time.sleep(.05)
        else: raise AssertionError('gateway startup deadline')
        yield process,ca_path/'mitmproxy-ca-cert.pem',port
    finally:
        if process.poll() is None: process.terminate()
        try: process.communicate(timeout=3)
        except subprocess.TimeoutExpired: process.kill(); process.communicate()


def connect(cafile, port, *, connect_host='allowed.example', sni='allowed.example', alpn=('http/1.1',), trust=True):
    sock=socket.create_connection(('127.0.0.1',8080),timeout=2)
    sock.sendall(f'CONNECT {connect_host}:{port} HTTP/1.1\r\nHost: {connect_host}:{port}\r\n\r\n'.encode())
    response=b''
    while not response.endswith(b'\r\n\r\n'):
        chunk=sock.recv(4096)
        if not chunk: raise OSError('CONNECT closed')
        response+=chunk
    if not response.startswith(b'HTTP/1.1 200'): sock.close(); return None
    context=ssl.create_default_context(cafile=str(cafile) if trust else None)
    context.set_alpn_protocols(list(alpn))
    if sni is None: context.check_hostname=False  # negative no-SNI; verification stays required
    return context.wrap_socket(sock,server_hostname=sni)


def request(sock, port, *, host=None, extra='', target='/'):
    if sock is None: return b''
    host=host or f'allowed.example:{port}'
    sock.sendall(f'GET {target} HTTP/1.1\r\nHost: {host}\r\n{extra}\r\n'.encode())
    result=b''
    while b'\r\n\r\n' not in result:
        data=sock.recv(8192)
        if not data: break
        result+=data
    if b'200 OK' in result:
        while len(result.split(b'\r\n\r\n',1)[1])<2: result+=sock.recv(8192)
    return result

def plain_request(port):
    with socket.create_connection(('127.0.0.1',8080),timeout=2) as sock:
        sock.sendall(f'GET https://allowed.example:{port}/ HTTP/1.1\r\nHost: allowed.example:{port}\r\n\r\n'.encode())
        return sock.recv(4096)

def expired_request(ca,port):
    time.sleep(2.2)
    return request(connect(ca,port),port)

def reuse(ca,port,changed=False):
    sock=connect(ca,port)
    first=request(sock,port)
    assert b'200 OK' in first
    try: second=request(sock,port,host='forbidden.example' if changed else None)
    except OSError: second=b''
    if changed:
        assert b'200 OK' not in second
        return first
    return second


def save_session_ca(process, ca, port):
    (ROOT/'prior-session-ca.pem').write_bytes(ca.read_bytes())
    return request(connect(ca,port),port)


def prior_ca_refused(process, ca, port):
    previous = ROOT/'prior-session-ca.pem'
    assert previous.read_bytes() != ca.read_bytes(), 'CA was reused between sessions'
    return request(connect(previous,port),port)


def interrupted_keepalive(process, ca, port, *, expire=False):
    sock = connect(ca,port)
    first = request(sock,port)
    assert b'200 OK' in first
    if expire:
        process.wait(timeout=5)
        assert process.returncode == 71, 'policy expiry did not stop gateway'
    else:
        process.terminate()
        process.wait(timeout=3)
    try:
        second = request(sock,port)
    except OSError:
        second = b''
    finally:
        sock.close()
    assert b'200 OK' not in second, 'interrupted gateway continued forwarding'
    return first

results=[]
def case(name, action, server=servers[0], *, positive=False, tcp_deny=True, ttl=30, expected_requests=1):
    before=(server.connections,server.requests)
    with gateway(server,ttl=ttl) as info:
        try: response=action(*info)
        except (OSError,ssl.SSLError): response=b''
        if positive: assert b'200 OK' in response and response.endswith(b'OK'), (name,response)
        time.sleep(.08)
    after=(server.connections,server.requests)
    if positive: assert after[1]-before[1]==expected_requests,(name,before,after)
    else:
        assert after[1]==before[1],(name,'upstream application reached',before,after)
        if tcp_deny: assert after[0]==before[0],(name,'upstream connected',before,after)
    results.append({'name':name,'passed':True,'upstream_connections':after[0]-before[0],
                    'upstream_requests':after[1]-before[1]})

try:
    case('positive_both_tls_legs',lambda p,ca,port: request(connect(ca,port),port),positive=True)
    case('keepalive_positive',lambda p,ca,port: reuse(ca,port),positive=True,expected_requests=2)
    case('keepalive_host_changed',lambda p,ca,port: reuse(ca,port,True),positive=True)
    case('connect_denied',lambda p,ca,port: connect(ca,port,connect_host='forbidden.example'))
    case('sni_mismatch',lambda p,ca,port: connect(ca,port,sni='forbidden.example'))
    case('no_sni',lambda p,ca,port: connect(ca,port,sni=None))
    case('http2_alpn',lambda p,ca,port: connect(ca,port,alpn=('h2',)))
    case('untrusted_gateway_ca',lambda p,ca,port: connect(ca,port,trust=False))
    case('host_mismatch',lambda p,ca,port: request(connect(ca,port),port,host='forbidden.example'))
    case('duplicate_host',lambda p,ca,port: request(connect(ca,port),port,extra='Host: forbidden.example\r\n'))
    case('absolute_target_mismatch',lambda p,ca,port: request(connect(ca,port),port,target='https://forbidden.example/'))
    case('websocket_upgrade',lambda p,ca,port: request(connect(ca,port),port,extra='Upgrade: websocket\r\nConnection: upgrade\r\n'))
    case('ambiguous_content_length',lambda p,ca,port: request(connect(ca,port),port,extra='Content-Length: 0\r\nContent-Length: 1\r\n'))
    case('upstream_hostname_mismatch',lambda p,ca,port: request(connect(ca,port),port),server=servers[1],tcp_deny=False)
    case('unpermitted_plain_http',lambda p,ca,port: plain_request(port))
    case('expired_policy',lambda p,ca,port: expired_request(ca,port),ttl=2)
    case('oversized_content_length',lambda p,ca,port: request(connect(ca,port),port,extra='Content-Length: 8388609\r\n'))
    case('compressed_request',lambda p,ca,port: request(connect(ca,port),port,extra='Content-Encoding: gzip\r\n'))
    case('upstream_untrusted_signature',lambda p,ca,port: request(connect(ca,port),port),server=servers[3],tcp_deny=False)
    case('upstream_expired_certificate',lambda p,ca,port: request(connect(ca,port),port),server=servers[2],tcp_deny=False)
    case('session_ca_positive',save_session_ca,positive=True)
    case('previous_session_ca_refused',prior_ca_refused)
    case('gateway_death_closes_active_connection',interrupted_keepalive,positive=True)
    case('policy_expiry_closes_active_connection',lambda p,ca,port: interrupted_keepalive(p,ca,port,expire=True),positive=True,ttl=3)
    print(json.dumps({'scope':'actual candidate image; loopback TLS, test-only upstream CA; no host egress acceptance',
                      'results':results,'passed':len(results)},indent=2))
finally:
    for server in servers: server.shutdown(); server.server_close()
