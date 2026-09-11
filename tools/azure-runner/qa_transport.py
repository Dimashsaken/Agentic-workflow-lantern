"""Frozen controller QA destination policy. External activation fails closed.

No flag, proxy environment variable or worker claim proves host egress isolation.
The production launcher is intentionally unavailable until the candidate image
and a host firewall adapter pass the actual transport acceptance charter.
"""
from dataclasses import dataclass
import hashlib
import ipaddress
import json
import math
import re
import time
from urllib.parse import urlsplit


class TransportHeld(RuntimeError):
    pass


def canonical_origin(value):
    if not isinstance(value, str) or not value.isascii() or any(c in value for c in '\\%\r\n\t '):
        raise TransportHeld('origin is not canonical ASCII HTTPS')
    try:
        parts = urlsplit(value)
        port = parts.port or 443
    except ValueError:
        raise TransportHeld('invalid origin') from None
    name = parts.hostname or ''
    if (parts.scheme != 'https' or parts.username is not None or parts.password is not None
            or parts.path or parts.query or parts.fragment or name != name.lower()
            or len(name) > 253 or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', name)
            or any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-') for label in name.split('.'))
            or not 1 <= port <= 65535 or parts.netloc != name + (f':{port}' if port != 443 else '')):
        raise TransportHeld('origin is not canonical ASCII HTTPS')
    try:
        ipaddress.ip_address(name)
    except ValueError:
        pass
    else:
        raise TransportHeld('IP-literal origins are forbidden')
    return name, port


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Destination:
    origin: str
    addresses: tuple[str, ...]
    expires_at: float


class Policy:
    def __init__(self, execution_key, destinations, *, created_at=None, test_only=False):
        now = time.time() if created_at is None else created_at
        if not execution_key or not isinstance(execution_key, str) or not destinations or len(destinations) > 32:
            raise TransportHeld('invalid execution or destination count')
        self.execution_key, self.created_at, self.test_only = execution_key, now, test_only
        self.destinations = {}
        for destination in destinations:
            name, port = canonical_origin(destination.origin)
            if (not math.isfinite(destination.expires_at) or not now < destination.expires_at <= now+1800
                    or not destination.addresses or len(destination.addresses) > 32):
                raise TransportHeld('invalid DNS validity or address count')
            for address in destination.addresses:
                ip = ipaddress.ip_address(address)
                if (str(ip) != address or getattr(ip, 'ipv4_mapped', None)
                        or (not test_only and not ip.is_global)
                        or ip.is_multicast or ip.is_unspecified or ip.is_reserved
                        or getattr(ip, 'is_site_local', False)):
                    raise TransportHeld('unapproved destination address')
            if (name, port) in self.destinations:
                raise TransportHeld('duplicate origin')
            self.destinations[(name, port)] = destination

    def permit(self, connect_host, connect_port, sni, host_header, *, now=None):
        now = time.time() if now is None else now
        target = self.destinations.get((connect_host, connect_port))
        authority = connect_host + (f':{connect_port}' if connect_port != 443 else '')
        if (not target or now < self.created_at or now >= target.expires_at
                or sni != connect_host or host_header != authority):
            raise TransportHeld('CONNECT, SNI, Host or live policy differs')
        return target

    def document(self):
        return {'version': 1, 'execution_key': self.execution_key, 'created_at': self.created_at,
                'test_only': self.test_only, 'destinations': [
                    {'origin': d.origin, 'addresses': list(d.addresses), 'expires_at': d.expires_at}
                    for _, d in sorted(self.destinations.items())]}

    @classmethod
    def load(cls, document):
        if document.get('version') != 1 or type(document.get('test_only')) is not bool:
            raise TransportHeld('unknown policy version')
        return cls(document['execution_key'], [Destination(d['origin'], tuple(d['addresses']), d['expires_at'])
                   for d in document['destinations']], created_at=document['created_at'], test_only=document['test_only'])


def check_external_acceptance(*args, **kwargs):
    """Pure acceptance check: it must never allocate a gateway or recorder."""
    raise TransportHeld('external QA is held: no accepted host firewall adapter and actual-image denial proof; proxy variables alone are insufficient')


def launch_external(*args, **kwargs):
    check_external_acceptance(*args, **kwargs)
    raise TransportHeld('external QA has no accepted lifecycle adapter')
