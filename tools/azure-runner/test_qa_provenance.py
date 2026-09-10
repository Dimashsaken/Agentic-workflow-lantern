from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from qa_provenance import Capture, CaptureHeld, Identity, verify


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.authority, self.media = self.root/'authority', self.root/'media'
        self.media.mkdir()
        (self.media/'session.webm').write_bytes(b'unit video bytes; actual decode tested separately')
        (self.media/'trace.zip').write_bytes(b'unit trace')
        self.identity = Identity('run', 'run:04-qa-dev:1', 3, 1, 4)
        self.deployment = {'deployment_id': 'deploy1', 'revision': 'a'*40,
                           'origin': 'https://example.org', 'descriptor_id': 'controller:fixture'}
        self.policy = {'execution_key': self.identity.execution_key, 'test_only': True,
                       'destinations': [{'origin': 'https://example.org'}]}
        self.files = {'video': 'session.webm', 'trace': 'trace.zip'}
        self.probe = lambda p: {'decoded': True, 'duration_seconds': 2, 'streams': []}

    def tearDown(self):
        self.tmp.cleanup()

    def capture(self):
        return Capture(self.identity, self.authority, self.media, self.policy, self.deployment,
                       ['AC-1', 'AC-2'], gateway_image='sha256:'+'b'*64,
                       recorder_image='sha256:'+'c'*64, ca_fingerprint='d'*64)

    def seal(self):
        capture = self.capture()
        capture.outcome('test1', 'AC-1', True)
        capture.outcome('test2', 'AC-2', True)
        result = capture.seal(self.deployment, self.files, writers_closed=True, probe=self.probe)
        return capture, result

    def test_positive_authority_receipt(self):
        capture, result = self.seal()
        self.assertEqual(verify(self.authority, self.media, capture.recording_id, self.identity,
                                self.deployment, probe=self.probe), result)

    def test_direct_fixture_cannot_claim_external_transport(self):
        options = dict(gateway_image=None, recorder_image='sha256:'+'c'*64,
                       ca_fingerprint='d'*64, transport_mode='direct_fixture')
        capture = Capture(self.identity, self.authority, self.media, self.policy,
                          self.deployment, ['AC-1'], **options)
        self.assertEqual(capture.transport_mode, 'direct_fixture')
        for policy, gateway in (({**self.policy, 'test_only': False}, None),
                                (self.policy, 'sha256:'+'b'*64)):
            with self.assertRaises(CaptureHeld):
                Capture(self.identity, self.authority, self.media, policy, self.deployment,
                        ['AC-1'], **{**options, 'gateway_image': gateway})

    def test_verifier_refuses_unknown_or_contradictory_transport(self):
        capture, record = self.seal()
        for change in ({'transport_mode': None}, {'transport_mode': 'unknown'},
                       {'transport_mode': 'direct_fixture'},
                       {'transport_mode': 'direct_fixture', 'images': {**record['images'], 'gateway': None}, 'test_only': False}):
            (self.authority/(capture.recording_id+'.json')).write_text(json.dumps({**record, **change}))
            with self.assertRaises(CaptureHeld):
                verify(self.authority, self.media, capture.recording_id, self.identity,
                       self.deployment, probe=self.probe)

    def test_wrong_execution_fence_and_revision_rejected(self):
        capture, _ = self.seal()
        for identity in (Identity('other', self.identity.execution_key, 3, 1, 4),
                         Identity('run', self.identity.execution_key, 3, 2, 4),
                         Identity('run', self.identity.execution_key, 3, 1, 5)):
            with self.assertRaises(CaptureHeld):
                verify(self.authority, self.media, capture.recording_id, identity, self.deployment, probe=self.probe)
        with self.assertRaises(CaptureHeld):
            verify(self.authority, self.media, capture.recording_id, self.identity,
                   {**self.deployment, 'revision': 'b'*40}, probe=self.probe)

    def test_missing_failed_or_duplicate_requirement_holds(self):
        for passed in (True, False):
            capture = self.capture()
            capture.outcome('test1', 'AC-1', passed)
            with self.assertRaises(CaptureHeld):
                capture.outcome('test1', 'AC-2', True)
            with self.assertRaises(CaptureHeld):
                capture.seal(self.deployment, self.files, writers_closed=True, probe=self.probe)

    def test_media_swap_tampering_and_unclosed_writer_holds(self):
        capture = self.capture()
        with self.assertRaises(CaptureHeld):
            capture.seal(self.deployment, self.files, writers_closed=False, probe=self.probe)
        capture, _ = self.seal()
        (self.media/'session.webm').write_bytes(b'tampered')
        with self.assertRaises(CaptureHeld):
            verify(self.authority, self.media, capture.recording_id, self.identity, self.deployment, probe=self.probe)

    def test_deployment_drift_holds(self):
        capture = self.capture()
        capture.outcome('test1', 'AC-1', True)
        capture.outcome('test2', 'AC-2', True)
        with self.assertRaises(CaptureHeld):
            capture.seal({**self.deployment, 'deployment_id': 'new'}, self.files, writers_closed=True, probe=self.probe)

    def test_fake_mirror_does_not_supply_receipt(self):
        (self.media / ('e'*32+'.json')).write_text('{}')
        with self.assertRaises((OSError, ValueError)):
            verify(self.authority, self.media, 'e'*32, self.identity, self.deployment, probe=self.probe)

    def test_video_decoder_failure_holds(self):
        capture = self.capture()
        capture.outcome('test1', 'AC-1', True)
        capture.outcome('test2', 'AC-2', True)
        def fail(_):
            raise ValueError('actual decoder failure')
        with self.assertRaises(ValueError):
            capture.seal(self.deployment, self.files, writers_closed=True, probe=fail)


if __name__ == '__main__':
    unittest.main()
