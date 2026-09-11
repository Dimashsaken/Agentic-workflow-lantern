"""Linux host adapter for per-container QA network namespace restrictions.

Rules execute before output DNAT, including Docker embedded DNS. This is a
candidate adapter, not acceptance: external launch remains held independently.
Docker Desktop needs an explicitly verified VM adapter; Windows refuses here.
"""
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import stat

from qa_transport import TransportHeld, Policy, digest

TABLE = 'lantern_qa'


def rule_plan(role, proxy_ip, proxy_port, recorder_ip, policy):
    policy = Policy.load(policy)
    if role not in {'recorder', 'gateway'} or type(proxy_port) is not int or not 1 <= proxy_port <= 65535:
        raise TransportHeld('invalid QA network role/port')
    for value in (proxy_ip, recorder_ip):
        ip = ipaddress.ip_address(value)
        if str(ip) != value or ip.is_multicast or ip.is_unspecified or getattr(ip, 'ipv4_mapped', None):
            raise TransportHeld('invalid QA network address')
    commands = [{'add': {'table': {'family': 'inet', 'name': TABLE}}}]
    for chain in ('input', 'output', 'forward'):
        commands.append({'add': {'chain': {'family': 'inet', 'table': TABLE, 'name': chain,
                          'type': 'filter', 'hook': chain, 'prio': -150, 'policy': 'drop'}}})
    def allow(chain, address, port, direction, *, response=False):
        protocol = 'ip6' if ':' in address else 'ip'
        expr = [{'match': {'op': '==', 'left': {'payload': {'protocol': protocol,
                'field': 'saddr' if direction == 'source' else 'daddr'}}, 'right': address}},
                {'match': {'op': '==', 'left': {'payload': {'protocol': 'tcp',
                'field': 'sport' if response else 'dport'}}, 'right': port}}]
        if response:
            expr.append({'match': {'op': '==', 'left': {'ct': {'key': 'state'}},
                                  'right': {'set': ['established', 'related']}}})
        expr.append({'counter': None})
        expr.append({'accept': None})
        commands.append({'add': {'rule': {'family': 'inet', 'table': TABLE, 'chain': chain, 'expr': expr}}})
    if role == 'recorder':
        allow('output', proxy_ip, proxy_port, 'destination')
        allow('input', proxy_ip, proxy_port, 'source', response=True)
    else:
        allow('input', recorder_ip, proxy_port, 'source')
        # Reply source port is proxy_port, destination is the recorder only.
        allow('output', recorder_ip, proxy_port, 'destination', response=True)
        for destination in policy.destinations.values():
            from qa_transport import canonical_origin
            _, port = canonical_origin(destination.origin)
            for address in destination.addresses:
                allow('output', address, port, 'destination')
                allow('input', address, port, 'source', response=True)
    return {'nftables': commands}


def normalize_rules(document, *, planned=False):
    def clean(value):
        if isinstance(value, list):
            return [clean(item) for item in value]
        if not isinstance(value, dict):
            return value
        return {k: None if k == 'counter' else clean(v) for k, v in value.items()
                if k not in {'handle', 'index', 'position'}}
    items = [clean(item['add'] if planned else item) for item in document['nftables']
             if 'metainfo' not in item]
    # nft emits rules grouped by chain, irrespective of insertion interleaving.
    # Stable sorting preserves the security-significant order within each chain.
    def location(item):
        kind, value = next(iter(item.items()))
        return (kind, value.get('family', ''), value.get('table', ''),
                value.get('chain', '') if kind == 'rule' else value.get('name', ''))
    return sorted(items, key=location)


def local_container_cgroup(container, text):
    if not re.fullmatch('[0-9a-f]{64}', container):
        return False
    for line in text.splitlines():
        fields = line.split(':', 2)
        if len(fields) == 3 and fields[0].isdigit() and fields[2].startswith('/'):
            if any(part in {container, 'docker-' + container + '.scope'}
                   for part in fields[2].split('/')):
                return True
    return False


class LinuxNamespaceFirewall:
    def __init__(self, run=None, *, docker_socket='/var/run/docker.sock'):
        if os.name != 'posix' or not Path('/proc/self/ns/net').exists():
            raise TransportHeld('QA host firewall requires verified native Linux network namespaces; Desktop unsupported')
        # Resolve once and always override Docker context/DOCKER_HOST. A remote
        # daemon's PID is not evidence about any local process or namespace.
        self.socket = Path(docker_socket).resolve(strict=True)
        self.socket_identity = self.check_socket()
        self.run = run or subprocess.run
        self.installed = []
        info = json.loads(self.command(['docker', 'info', '--format', '{{json .}}']))
        if info.get('OSType') != 'linux' or 'docker desktop' in info.get('OperatingSystem', '').lower():
            raise TransportHeld('QA firewall requires the native local Linux Docker daemon')

    def check_socket(self):
        entry = self.socket.stat()
        if not stat.S_ISSOCK(entry.st_mode) or entry.st_uid != 0:
            raise TransportHeld('QA firewall requires a root-owned local Docker Unix socket')
        return entry.st_dev, entry.st_ino

    def command(self, args, data=None):
        if args[0] == 'docker':
            if self.check_socket() != self.socket_identity:
                raise TransportHeld('local Docker socket changed')
            args = [args[0], '--host', 'unix://' + str(self.socket), *args[1:]]
        result = self.run(args, input=data, capture_output=True, text=True, timeout=30, check=True)
        return result.stdout

    def inspect(self, container, execution_key):
        if not isinstance(container, str) or not re.fullmatch('[0-9a-f]{64}', container):
            raise TransportHeld('QA network setup requires an exact container ID')
        rows = json.loads(self.command(['docker', 'inspect', container]))
        if len(rows) != 1 or rows[0].get('Id') != container:
            raise TransportHeld('container identity changed')
        row = rows[0]
        host, state = row['HostConfig'], row['State']
        if (not state.get('Running') or type(state.get('Pid')) is not int or state['Pid'] <= 1
                or host.get('Privileged') or host.get('NetworkMode') in {'host', 'none'}
                or not host.get('ReadonlyRootfs') or host.get('CapAdd')
                or 'ALL' not in (host.get('CapDrop') or [])
                or row.get('Config', {}).get('Labels', {}).get('lantern.qa.execution') != digest(execution_key)):
            raise TransportHeld('untrusted QA container configuration')
        # Native host /proc must expose the full immutable container ID as a
        # cgroup path component, including Docker's systemd scope spelling.
        # Private cgroup views and remote Docker PID collisions fail closed.
        try:
            cgroups = Path(f"/proc/{state['Pid']}/cgroup").read_text()
        except OSError as exc:
            raise TransportHeld('cannot prove local QA container process identity') from exc
        if not local_container_cgroup(container, cgroups):
            raise TransportHeld('Docker PID does not belong to the exact local QA container')
        namespace = Path(f"/proc/{state['Pid']}/ns/net")
        token = namespace.stat().st_ino
        if token == Path('/proc/self/ns/net').stat().st_ino:
            raise TransportHeld('QA container shares the host namespace')
        return row, token

    def install(self, recorder, gateway, execution_key, policy, proxy_ip, proxy_port, recorder_ip):
        policy = Policy.load(policy)
        if policy.execution_key != execution_key:
            raise TransportHeld('network policy belongs to another execution')
        rec, rec_ns = self.inspect(recorder, execution_key)
        gate, gate_ns = self.inspect(gateway, execution_key)
        if rec_ns == gate_ns:
            raise TransportHeld('recorder and gateway share a network namespace')
        rec_nets, gate_nets = rec['NetworkSettings']['Networks'], gate['NetworkSettings']['Networks']
        if len(rec_nets) != 1 or not set(rec_nets).issubset(gate_nets):
            raise TransportHeld('recorder is not confined to one gateway network')
        shared = next(iter(rec_nets))
        network_id = rec_nets[shared]['NetworkID']
        network = json.loads(self.command(['docker', 'network', 'inspect', network_id]))[0]
        if (network.get('Id') != network_id or not network.get('Internal')
                or set(network.get('Containers', {})) != {recorder, gateway}
                or network.get('Labels', {}).get('lantern.qa.execution') != digest(execution_key)
                or rec_nets[shared].get('IPAddress') != recorder_ip
                or gate_nets[shared].get('IPAddress') != proxy_ip):
            raise TransportHeld('QA private network identity differs')
        # Both containers must be idle controller-owned processes until install
        # and the separate actual-host acceptance checks have completed.
        for role, row, token in (('recorder', rec, rec_ns), ('gateway', gate, gate_ns)):
            pid = row['State']['Pid']
            # Keep the original namespace alive across PID exit/reuse. nsenter
            # opens the controller's pinned FD, never a newly reused target PID.
            fd = os.open(f'/proc/{pid}/ns/net', os.O_RDONLY)
            try:
                if os.fstat(fd).st_ino != token or self.inspect(row['Id'], execution_key)[1] != token:
                    raise TransportHeld('QA namespace changed during installation')
                plan = rule_plan(role, proxy_ip, proxy_port, recorder_ip, policy.document())
                prefix = ['nsenter', '--net=' + f'/proc/{os.getpid()}/fd/{fd}', '--']
                self.command(prefix + ['nft', '--check', '--json', '--file', '-'], json.dumps(plan))
                self.command(prefix + ['nft', '--json', '--file', '-'], json.dumps(plan))
                observed = json.loads(self.command(prefix + ['nft', '--json', 'list', 'table', 'inet', TABLE]))
                if normalize_rules(observed) != normalize_rules(plan, planned=True):
                    raise TransportHeld('installed QA rules differ from the frozen plan')
                if self.inspect(row['Id'], execution_key)[1] != token:
                    raise TransportHeld('QA container restarted during installation')
                self.installed.append({'container': row['Id'], 'namespace': token,
                                       'rules_sha256': digest(plan), 'role': role})
            finally:
                os.close(fd)
        return {'candidate_only': True, 'external_transport_verified': False, 'installed': self.installed}

    # No rule removal while containers are alive: on any error the caller stops
    # the two owned containers; destroying their namespaces removes these rules.
