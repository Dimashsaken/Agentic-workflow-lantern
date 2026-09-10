import time
import unittest
from qa_transport import Policy, Destination, TransportHeld, canonical_origin, launch_external


class PolicyTests(unittest.TestCase):
    def policy(self, address='93.184.216.34', **kwargs):
        return Policy('run:qa:1', [Destination('https://example.org', (address,), 1100)], created_at=1000, **kwargs)

    def test_valid_policy_permits_exact_origin_and_roundtrips(self):
        policy = self.policy()
        self.assertEqual(policy.permit('example.org', 443, 'example.org', 'example.org', now=1001).addresses, ('93.184.216.34',))
        self.assertEqual(Policy.load(policy.document()).document(), policy.document())

    def test_ambiguous_and_non_https_origins_rejected(self):
        for origin in ('http://example.org', 'https://example.org/', 'https://example.org:443',
                       'https://Example.org', 'https://example.org.', 'https://user@example.org',
                       'https://example.org?x', 'https://example.org#x', 'https://127.0.0.1',
                       'https://[::1]', 'https://example.org%2f', 'https://x..org'):
            with self.subTest(origin=origin), self.assertRaises(TransportHeld):
                canonical_origin(origin)

    def test_private_special_mapped_addresses_rejected(self):
        for address in ('127.0.0.1', '169.254.169.254', '10.0.0.1', '::1', '::ffff:8.8.8.8', '224.0.0.1', '0.0.0.0', 'fec0::1', '240.0.0.1'):
            with self.subTest(address=address), self.assertRaises(TransportHeld):
                self.policy(address)

    def test_test_only_does_not_silently_become_external(self):
        policy = self.policy('127.0.0.1', test_only=True)
        self.assertTrue(policy.document()['test_only'])
        document = policy.document()
        document['test_only'] = False
        with self.assertRaises(TransportHeld):
            Policy.load(document)

    def test_host_sni_port_reuse_and_expiry_hold(self):
        for args in [('example.org', 443, 'other.org', 'example.org', 1001),
                     ('example.org', 443, 'example.org', 'other.org', 1001),
                     ('example.org', 444, 'example.org', 'example.org', 1001),
                     ('example.org', 443, 'example.org', 'example.org', 1100),
                     ('example.org', 443, 'example.org', 'example.org', 999)]:
            with self.subTest(args=args), self.assertRaises(TransportHeld):
                self.policy().permit(*args[:4], now=args[4])

    def test_external_launch_cannot_be_enabled_by_worker_claim(self):
        with self.assertRaisesRegex(TransportHeld, 'firewall'):
            launch_external(verified=True, policy=self.policy())


if __name__ == '__main__':
    unittest.main()
