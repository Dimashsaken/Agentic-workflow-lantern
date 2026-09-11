"""Opt-in native Linux/Docker firewall acceptance with disposable socket fixtures.

Run as root on an authorized native Linux host. Images must be exact local IDs.
This never enables external QA, deploys an application, or edits host firewall rules.
Every mutated Docker object belongs to this invocation; nft/ip changes enter only
its containers' network namespaces. Browser/TLS/deployment acceptance is separate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time
import uuid

from qa_network import LinuxNamespaceFirewall
from qa_transport import Destination, Policy, TransportHeld, digest


CLIENT = r'''
import json,socket,sys
address,port,protocol=sys.argv[1:]
s=socket.socket(socket.AF_INET6 if ':' in address else socket.AF_INET,
                socket.SOCK_DGRAM if protocol=='udp' else socket.SOCK_STREAM)
s.settimeout(.6)
try:
 s.connect((address,int(port)));s.sendall(b'lantern-owned-probe');ok=s.recv(100)==b'ok'
except OSError:ok=False
finally:s.close()
print(json.dumps(ok))
'''

SERVER = r'''
import json,socket,sys,threading,time
log,bindings=sys.argv[1],json.loads(sys.argv[2]);lock=threading.Lock()
def serve(address,port,protocol):
 s=socket.socket(socket.AF_INET6 if ':' in address else socket.AF_INET,
                 socket.SOCK_DGRAM if protocol=='udp' else socket.SOCK_STREAM)
 s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind((address,port))
 if protocol!='udp':s.listen()
 while True:
  if protocol=='udp':data,peer=s.recvfrom(1024);s.sendto(b'ok',peer)
  else:
   c,peer=s.accept();c.settimeout(2)
   try:data=c.recv(1024);c.sendall(b'ok')
   except OSError:data=b''
   finally:c.close()
  with lock:
   with open(log,'a') as f:f.write(json.dumps({'port':port,'protocol':protocol,'bytes':len(data)})+'\n')
threads=[]
for binding in bindings:
 t=threading.Thread(target=serve,args=binding,daemon=True);t.start();threads.append(t)
time.sleep(.25)
assert all(t.is_alive() for t in threads)
print('ready',flush=True)
time.sleep(1800)
'''

# Destination-side packet observer is independent of nftables and the clients.
# A stop file gives it a bounded lifetime without AppArmor signal transitions
# between the SSM snap profile and the distro tcpdump executable profile.
PACKETS = r'''
import json,select,socket,struct,sys,time
from pathlib import Path
output,stop,ports=sys.argv[1:];ports=set(json.loads(ports));observed=[]
s=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3));s.setblocking(False)
print('ready',flush=True);deadline=time.monotonic()+180
while not Path(stop).exists() and time.monotonic()<deadline:
 if not select.select([s],[],[],.1)[0]:continue
 packet,source=s.recvfrom(65535)
 # Observe inbound frames only. Outbound attempts dropped in the sender are
 # not evidence that a destination received them.
 if source[2]==socket.PACKET_OUTGOING or len(packet)<14:continue
 kind=struct.unpack('!H',packet[12:14])[0]
 if kind==0x0800 and len(packet)>=34:
  protocol=packet[23];offset=14+(packet[14]&15)*4
 elif kind==0x86dd and len(packet)>=54:
  protocol=packet[20];offset=54
 else:continue
 if protocol not in (6,17) or len(packet)<offset+4:continue
 port=struct.unpack('!H',packet[offset+2:offset+4])[0]
 if port in ports:observed.append({'family':4 if kind==0x0800 else 6,'protocol':protocol,'port':port,'bytes':len(packet)})
s.close();Path(output).write_text(json.dumps(observed))
'''


def command(*args, data=None, check=True):
    result = subprocess.run(args, input=data, capture_output=True, text=True,
                            timeout=45, check=check)
    return result.stdout


class Resources:
    """Exact IDs and unique labels gate cleanup; shared host state is untouched."""
    def __init__(self):
        self.key = 'native-acceptance:' + uuid.uuid4().hex
        self.prefix = 'lantern-external-qa-' + uuid.uuid4().hex[:12]
        self.root = Path(tempfile.mkdtemp(prefix=self.prefix + '-', dir='/tmp'))
        self.containers, self.networks, self.processes = [], [], []

    def docker(self, *args, **kwargs):
        return command('docker', '--host', 'unix:///var/run/docker.sock', *args, **kwargs)

    def network(self, suffix, ipv6=False):
        args = ['network', 'create', '--internal', '--label', 'lantern.qa.execution=' + digest(self.key)]
        if ipv6:
            group = uuid.uuid4().hex[:8]
            args += ['--ipv6', '--subnet', 'fd' + group[:2] + ':' + group[2:6] + ':' + group[6:] + '::/64']
        identity = self.docker(*args, self.prefix + '-' + suffix).strip()
        self.networks.append(identity)
        return json.loads(self.docker('network', 'inspect', identity))[0]

    def container(self, suffix, image, network, *, execution_key=None):
        identity = self.docker('run', '-d', '--name', self.prefix + '-' + suffix,
            '--label', 'lantern.qa.execution=' + digest(execution_key or self.key),
            '--label', 'lantern.qa.owner=' + digest(self.key), '--network', network,
            '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--entrypoint', 'python3', image, '-c', 'import time;time.sleep(1800)').strip()
        self.containers.append(identity)
        return identity

    def packets(self, label, identity, ports):
        path = self.root / (label + '.packets.json')
        stop = self.root / (label + '.stop')
        args = [sys.executable, '-u', '-c', PACKETS, str(path), str(stop), json.dumps(ports)]
        if identity:
            args = self.ns(identity, *args)
        log = (self.root / (label + '.packets.log')).open('w')
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=log, text=True)
        log.close()
        self.processes.append(process)
        if process.stdout.readline().strip() != 'ready':
            raise RuntimeError('packet observer failed')
        return process, path, stop

    def inspect(self, identity):
        return json.loads(self.docker('inspect', identity))[0]

    def ns(self, identity, *args):
        pid = self.inspect(identity)['State']['Pid']
        return ['nsenter', '--net=/proc/' + str(pid) + '/ns/net', '--', *args]

    def observer(self, label, identity, bindings):
        path = self.root / (label + '.jsonl')
        path.touch()
        args = [sys.executable, '-u', '-c', SERVER, str(path), json.dumps(bindings)]
        if identity:
            args = self.ns(identity, *args)
        stderr = (self.root / (label + '.stderr')).open('w')
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=stderr, text=True)
        stderr.close()
        self.processes.append(process)
        if process.stdout.readline().strip() != 'ready':
            raise RuntimeError('observer failed: ' + label)
        return path

    def probe(self, identity, address, port, protocol='tcp'):
        return json.loads(self.docker('exec', identity, 'python3', '-c', CLIENT,
                                      address, str(port), protocol))

    def cleanup(self):
        errors, stopped, removed, networks = [], [], [], []
        for process in reversed(self.processes):
            try:
                if process.poll() is None:
                    try:
                        process.terminate()
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                stopped.append(process.pid)
            except (OSError, subprocess.TimeoutExpired) as exc:
                errors.append({'resource': 'observer', 'pid': process.pid,
                               'error': type(exc).__name__ + ': ' + str(exc)})
        for identity in reversed(self.containers):
            try:
                row = self.inspect(identity)
                if row['Config']['Labels'].get('lantern.qa.owner') != digest(self.key):
                    raise RuntimeError('cleanup ownership differs')
                self.docker('rm', '-f', identity)
                removed.append(identity)
            except Exception as exc:
                errors.append({'resource': 'container', 'id': identity,
                               'error': type(exc).__name__ + ': ' + str(exc)})
        for identity in reversed(self.networks):
            try:
                row = json.loads(self.docker('network', 'inspect', identity))[0]
                if row['Labels'].get('lantern.qa.execution') != digest(self.key) or row['Containers']:
                    raise RuntimeError('cleanup network ownership differs')
                self.docker('network', 'rm', identity)
                networks.append(identity)
            except Exception as exc:
                errors.append({'resource': 'network', 'id': identity,
                               'error': type(exc).__name__ + ': ' + str(exc)})
        return {'complete': not errors, 'errors': errors, 'observers_stopped': stopped,
                'containers_removed': removed, 'networks_removed': networks,
                'evidence_retained': str(self.root)}


def execute(recorder_image, gateway_image):
    if platform.system() != 'Linux' or os.geteuid() != 0:
        raise RuntimeError('requires root on an authorized native Linux host')
    for image in (recorder_image, gateway_image):
        if not re.fullmatch('sha256:[0-9a-f]{64}', image):
            raise RuntimeError('exact local image SHA-256 required')
    owned = Resources()
    result = {'passed': False, 'scope': 'native Docker adapter with test-only socket fixtures',
              'external_transport_verified': False, 'trusted_deployment_verified': False,
              'kernel': platform.release(), 'images': {'recorder': recorder_image, 'gateway': gateway_image},
              'source_sha256': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                               for name in ('qa_native_acceptance.py', 'qa_network.py', 'qa_transport.py')},
              'calibration': {}, 'denials': {}}
    try:
        private = owned.network('private', ipv6=True)
        upstream = owned.network('upstream', ipv6=True)
        recorder = owned.container('recorder', recorder_image, private['Id'])
        gateway = owned.container('gateway', gateway_image, private['Id'])
        owned.docker('network', 'connect', upstream['Id'], gateway)
        endpoint = owned.container('endpoint', gateway_image, upstream['Id'])
        peer = owned.container('other-execution', gateway_image, upstream['Id'], execution_key=owned.key+':peer')
        def network_address(identity, net, ipv6=False):
            return owned.inspect(identity)['NetworkSettings']['Networks'][net['Name']][
                'GlobalIPv6Address' if ipv6 else 'IPAddress']
        rec_ip, proxy = network_address(recorder, private), network_address(gateway, private)
        target, target6 = network_address(endpoint, upstream), network_address(endpoint, upstream, True)
        peer_ip = network_address(peer, upstream)
        proxy6 = network_address(gateway, private, True)
        # Simulated metadata is bound only inside this owned gateway namespace.
        command(*owned.ns(gateway, 'ip', 'addr', 'add', '169.254.169.254/32', 'dev', 'lo'))
        command(*owned.ns(recorder, 'ip', 'route', 'add', '169.254.169.254/32', 'via', proxy))
        host_ip = next(x['Gateway'] for x in private['IPAM']['Config'] if ':' not in x['Gateway'])
        gate_log = owned.observer('gateway-observer', gateway,
            [('0.0.0.0', 8080, 'tcp'), ('0.0.0.0', 8444, 'tcp'),
             ('0.0.0.0', 53, 'udp'), ('0.0.0.0', 443, 'udp'),
             ('169.254.169.254', 18080, 'tcp'), (proxy6, 8444, 'tcp')])
        end_log = owned.observer('endpoint-observer', endpoint,
            [('0.0.0.0', 8443, 'tcp'), ('0.0.0.0', 8444, 'tcp'),
             ('0.0.0.0', 53, 'udp'), ('0.0.0.0', 443, 'udp'), (target6, 8444, 'tcp')])
        peer_log = owned.observer('other-execution-observer', peer, [('0.0.0.0', 8444, 'tcp')])
        host_log = owned.observer('host-observer', None, [(host_ip, 19091, 'tcp')])
        cases = [
            ('recorder_alternate_tcp', recorder, proxy, 8444, 'tcp'),
            ('recorder_direct_dns', recorder, proxy, 53, 'udp'),
            ('recorder_quic_udp', recorder, proxy, 443, 'udp'),
            ('recorder_ipv6', recorder, proxy6, 8444, 'tcp'),
            ('recorder_simulated_metadata', recorder, '169.254.169.254', 18080, 'tcp'),
            ('recorder_host_listener', recorder, host_ip, 19091, 'tcp'),
            ('gateway_forbidden_tcp', gateway, target, 8444, 'tcp'),
            ('gateway_direct_dns', gateway, target, 53, 'udp'),
            ('gateway_quic_udp', gateway, target, 443, 'udp'),
            ('gateway_ipv6', gateway, target6, 8444, 'tcp'),
            ('gateway_cross_execution', gateway, peer_ip, 8444, 'tcp'),
            ('gateway_simulated_metadata', gateway, '169.254.169.254', 18080, 'tcp'),
            ('gateway_host_listener', gateway, host_ip, 19091, 'tcp')]
        observers = [('gateway', gateway, [8444, 53, 443, 18080]),
                     ('endpoint', endpoint, [8444, 53, 443]),
                     ('peer', peer, [8444]), ('host', None, [19091])]
        def finish_packets(observers):
            counts = {}
            for process, path, stop in observers:
                stop.touch()
                process.wait(timeout=10)
                counts[path.name] = len(json.loads(path.read_text()))
            return counts
        permissive_packets = [owned.packets(label+'-permissive', identity, ports)
                              for label, identity, ports in observers]
        for label, identity, address, port, protocol in cases:
            result['calibration'][label] = owned.probe(identity, address, port, protocol)
        dns = "import socket;print(socket.gethostbyname('" + owned.prefix + "-gateway'))"
        result['calibration']['docker_embedded_dns'] = owned.docker('exec', recorder, 'python3', '-c', dns).strip() == proxy
        result['permissive_observer_packets'] = finish_packets(permissive_packets)
        if not all(result['calibration'].values()):
            raise AssertionError('permissive calibration failed')
        if not all(result['permissive_observer_packets'].values()):
            raise AssertionError('permissive packet observer calibration failed')
        policy = Policy(owned.key, [Destination('https://allowed.test:8443', (target,), time.time()+600)], test_only=True)
        firewall = LinuxNamespaceFirewall()
        result['adapter'] = firewall.install(recorder, gateway, owned.key, policy.document(), proxy, 8080, rec_ip)
        for label, identity in [('recorder', recorder), ('gateway', gateway)]:
            row, namespace = firewall.inspect(identity, owned.key)
            result[label + '_identity'] = {'id': identity, 'namespace': namespace,
                'cgroup': Path('/proc/' + str(row['State']['Pid']) + '/cgroup').read_text().strip()}
        result['positive'] = {'recorder_proxy': owned.probe(recorder, proxy, 8080),
                              'gateway_pinned_endpoint': owned.probe(gateway, target, 8443)}
        if not all(result['positive'].values()):
            raise AssertionError('positive allowlist path failed')
        logs = [gate_log, end_log, peer_log, host_log]
        before = {p.name: p.read_text() for p in logs}
        packet_observers = [owned.packets(label+'-forbidden', identity, ports)
                            for label, identity, ports in observers]
        for label, identity, address, port, protocol in cases:
            result['denials'][label] = not owned.probe(identity, address, port, protocol)
        dns_denied = "import socket;socket.setdefaulttimeout(.5)\ntry:socket.gethostbyname('" + owned.prefix + "-gateway');print('resolved')\nexcept OSError:print('denied')"
        result['denials']['docker_embedded_dns'] = owned.docker('exec', recorder,
            'python3', '-c', dns_denied).strip() == 'denied'
        after = {p.name: p.read_text() for p in logs}
        result['zero_forbidden_observer_bytes'] = before == after
        result['forbidden_observer_packets'] = finish_packets(packet_observers)
        result['observer_counts'] = {p.name: len(p.read_text().splitlines()) for p in logs}
        # Wrong execution is rejected before replacing or opening namespaces.
        try:
            firewall.install(recorder, gateway, owned.key + ':wrong', policy.document(), proxy, 8080, rec_ip)
        except TransportHeld:
            result['wrong_execution_refused'] = True
        else:
            result['wrong_execution_refused'] = False
        try:
            firewall.inspect(peer, owned.key)
        except TransportHeld:
            result['peer_execution_refused'] = True
        else:
            result['peer_execution_refused'] = False
        result['passed'] = (all(result['denials'].values()) and before == after
            and not any(result['forbidden_observer_packets'].values())
            and result['wrong_execution_refused'] and result['peer_execution_refused'])
    except Exception as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        try:
            result['cleanup'] = owned.cleanup()
            result['passed'] = result['passed'] and result['cleanup']['complete']
        except Exception as exc:
            result['passed'] = False
            result['cleanup_error'] = type(exc).__name__ + ': ' + str(exc)
        (owned.root / 'result.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recorder-image', required=True)
    parser.add_argument('--gateway-image', required=True)
    options = parser.parse_args()
    evidence = execute(options.recorder_image, options.gateway_image)
    print(json.dumps(evidence, indent=2))
    sys.exit(0 if evidence['passed'] else 1)
