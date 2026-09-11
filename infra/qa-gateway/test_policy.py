"""Hermetic gateway-hook regressions; actual-image proof lives in test_image.py."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/azure-runner'))
from qa_transport import Destination, Policy

class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.policy = Policy('hook-test', [Destination('https://allowed.example',('93.184.216.34',),1100)],created_at=1000)
        fake = SimpleNamespace(ctx=SimpleNamespace(options=None),http=SimpleNamespace())
        spec=importlib.util.spec_from_file_location('gateway_policy_under_test',Path(__file__).with_name('policy.py'))
        self.module=importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules,mitmproxy=fake), mock.patch.object(Path,'read_text',return_value=json.dumps(self.policy.document())):
            spec.loader.exec_module(self.module)
        self.gateway=self.module.addons[0]
        self.gateway.tunnels['client']=('allowed.example',443)
        self.gateway.permits['client']=('allowed.example',443,'93.184.216.34',1100)

    def hello(self, sni='allowed.example', alpn=(b'http/1.1',), extensions=()):
        return SimpleNamespace(context=SimpleNamespace(client=SimpleNamespace(id='client')),
            client_hello=SimpleNamespace(sni=sni,alpn_protocols=alpn,extensions=extensions),establish_server_tls_first=True)

    def test_tls_denial_exits_gateway_instead_of_ignored_client_error(self):
        for data in (self.hello(sni=None),self.hello(sni='forbidden.example'),self.hello(alpn=(b'h2',)),self.hello(extensions=[(0xfe0d,b'ech')])):
            with mock.patch.object(self.module.os,'_exit',side_effect=RuntimeError('exit')) as stop:
                with self.assertRaisesRegex(RuntimeError,'exit'): self.gateway.tls_clienthello(data)
                stop.assert_called_once_with(70)

    def test_tls_positive_never_requests_early_server_tls(self):
        data=self.hello(); self.gateway.tls_clienthello(data)
        self.assertFalse(data.establish_server_tls_first)

    def test_actual_replacement_server_is_pinned_after_permit_check(self):
        async def run():
            server=SimpleNamespace(id='server',address=('allowed.example',443),sni='allowed.example',error=None)
            data=SimpleNamespace(client=SimpleNamespace(id='client'),server=server)
            with mock.patch.object(self.module.time,'time',return_value=1001): self.gateway.server_connect(data)
            self.assertEqual(server.address,('93.184.216.34',443)); self.assertEqual(server.sni,'allowed.example')
            self.assertIn('server',self.gateway.connect_deadlines)
            server.peername=('93.184.216.34',443)
            self.gateway.server_connected(data)
            self.assertNotIn('server',self.gateway.connect_deadlines)
        asyncio.run(run())

    def test_unpermitted_replacement_and_expiry_cannot_connect(self):
        for address,sni,now in [(('forbidden.example',443),'allowed.example',1001),(('allowed.example',443),'forbidden.example',1001),(('allowed.example',443),'allowed.example',1100)]:
            server=SimpleNamespace(id='server',address=address,sni=sni,error=None)
            data=SimpleNamespace(client=SimpleNamespace(id='client'),server=server)
            with mock.patch.object(self.module.time,'time',return_value=now): self.gateway.server_connect(data)
            self.assertEqual(server.error,'missing QA connection permit')
            self.assertFalse(self.gateway.connect_deadlines)

if __name__=='__main__': unittest.main()
