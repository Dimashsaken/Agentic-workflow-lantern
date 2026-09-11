"""Candidate TLS-inspecting gateway addon; external activation remains held.

Each hook aborts the whole isolated gateway on unexpected exceptions. Mitmproxy's
normal addon exception logging is not a deny mechanism. No traffic is persisted.
"""
import asyncio
import functools
import json
import os
from pathlib import Path
import time

from mitmproxy import ctx, http
from qa_transport import Policy, TransportHeld


def fail_closed(function):
    @functools.wraps(function)
    def wrapped(self, value=None):
        try:
            return function(self) if value is None else function(self, value)
        except BaseException:
            os._exit(70)  # Never log a request, credentials, headers or response.
    return wrapped


class Gateway:
    def __init__(self):
        self.policy = Policy.load(json.loads(Path('/policy/policy.json').read_text()))
        self.tunnels = {}
        self.permits = {}
        self.total = 0
        self.clients = set()
        self.deadlines = {}
        self.connect_deadlines = {}

    @fail_closed
    def running(self):
        required = {'connection_strategy': 'lazy', 'upstream_cert': False, 'ssl_insecure': False,
                    'http2': False, 'http3': False, 'websocket': False, 'rawtcp': False,
                    'validate_inbound_headers': True, 'onboarding': False,
                    'stream_large_bodies': None, 'body_size_limit': '8m'}
        if any(getattr(ctx.options, key) != value for key, value in required.items()):
            raise TransportHeld('unsafe effective gateway options')
        deadline = min(d.expires_at for d in self.policy.destinations.values())
        asyncio.get_running_loop().call_later(max(0, min(1800, deadline-time.time())), os._exit, 71)

    @fail_closed
    def client_connected(self, client):
        if len(self.clients) >= 32:
            client.error = 'session connection limit'
        else:
            self.clients.add(client.id)

    @fail_closed
    def client_disconnected(self, client):
        self.clients.discard(client.id)
        self.tunnels.pop(client.id, None)
        self.permits.pop(client.id, None)

    @fail_closed
    def http_connect(self, flow):
        host, port = flow.request.host, flow.request.port
        if (flow.request.http_version != 'HTTP/1.1' or (host, port) not in self.policy.destinations
                or flow.client_conn.id in self.tunnels):
            flow.response = http.Response.make(403, b'QA destination refused')
            return
        self.tunnels[flow.client_conn.id] = (host, port)

    @fail_closed
    def tls_clienthello(self, data):
        tunnel = self.tunnels.get(data.context.client.id)
        sni = data.client_hello.sni
        if (not tunnel or sni != tunnel[0] or any(p != b'http/1.1' for p in data.client_hello.alpn_protocols)
                or any(kind == 0xfe0d for kind, _ in data.client_hello.extensions)):
            raise TransportHeld('QA TLS identity refused')
        data.establish_server_tls_first = False

    @fail_closed
    def requestheaders(self, flow):
        host, port = self.tunnels[flow.client_conn.id]
        self.deadlines[flow.id] = asyncio.get_running_loop().call_later(30, os._exit, 72)
        headers = flow.request.headers
        self.total += sum(len(k)+len(v) for k, v in headers.fields)
        if self.total > 256*1024*1024:
            raise TransportHeld('session traffic limit')
        names = headers.get_all('host')
        if (len(names) != 1 or flow.request.http_version != 'HTTP/1.1'
                or flow.request.scheme != 'https' or flow.request.host != host or flow.request.port != port
                or flow.request.authority
                or headers.get('upgrade') or headers.get('transfer-encoding')
                or headers.get('content-encoding') or len(headers.get_all('content-length')) > 1
                or sum(len(k)+len(v) for k, v in headers.fields) > 65536):
            flow.kill()
            return
        target = self.policy.permit(host, port, flow.client_conn.sni, names[0])
        # Keep the tunnel context hostname unchanged. The actual replacement
        # server socket is pinned by server_connect after this mandatory permit.
        self.permits[flow.client_conn.id] = (host, port, target.addresses[0], target.expires_at)
        flow.request.stream = False

    @fail_closed
    def server_connect(self, data):
        permit = self.permits.get(data.client.id)
        if (not permit or time.time() >= permit[3]
                or data.server.address not in ((permit[0], permit[1]), (permit[2], permit[1]))
                or data.server.sni != permit[0]):
            data.server.error = 'missing QA connection permit'
            return
        # HttpLayer may replace flow.server_conn after requestheaders. Pin the
        # actual socket here, after checking its original name and live permit.
        data.server.address = (permit[2], permit[1])
        data.server.sni = permit[0]
        self.connect_deadlines[data.server.id] = asyncio.get_running_loop().call_later(10, os._exit, 73)

    @fail_closed
    def server_connected(self, data):
        timer = self.connect_deadlines.pop(data.server.id, None)
        if timer:
            timer.cancel()
        permit = self.permits[data.client.id]
        if not data.server.peername or data.server.peername[:2] != (permit[2], permit[1]):
            data.server.error = 'QA peer identity differs'
            raise TransportHeld('peer mismatch')

    @fail_closed
    def server_connect_error(self, data):
        timer = self.connect_deadlines.pop(data.server.id, None)
        if timer:
            timer.cancel()

    @fail_closed
    def request(self, flow):
        permit = self.permits.get(flow.client_conn.id)
        if not permit or time.time() >= permit[3] or len(flow.request.raw_content or b'') > 8*1024*1024:
            flow.kill()
            return
        self.total += len(flow.request.raw_content or b'')
        if self.total > 256*1024*1024:
            raise TransportHeld('session traffic limit')

    @fail_closed
    def responseheaders(self, flow):
        # Reject compression in this initial pilot rather than decompressing an
        # attacker-controlled expansion before enforcing the decoded-byte limit.
        if (flow.response.status_code == 101 or flow.response.headers.get('content-encoding')
                or flow.response.headers.get('transfer-encoding')
                or sum(len(k)+len(v) for k, v in flow.response.headers.fields) > 65536):
            flow.kill()
        flow.response.stream = False

    @fail_closed
    def response(self, flow):
        timer = self.deadlines.pop(flow.id, None)
        if timer:
            timer.cancel()
        self.total += sum(len(k)+len(v) for k, v in flow.response.headers.fields)
        self.total += len(flow.response.raw_content or b'')
        if self.total > 256*1024*1024:
            raise TransportHeld('session traffic limit')

    @fail_closed
    def error(self, flow):
        timer = self.deadlines.pop(flow.id, None)
        if timer:
            timer.cancel()


addons = [Gateway()]
