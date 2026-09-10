"""Controller-only capture receipts, separate from legacy quality manifests.

The caller owns the recorder process/commands and observes a trusted deployment
descriptor independently of the browser. This API is never a worker file tool.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import time
from uuid import uuid4

import evidence_manifest
import execution_leases as leases
from execution_retention import atomic_json
from tool_policy import confined
from qa_transport import canonical_origin, digest


class CaptureHeld(RuntimeError):
    pass


def transport(mode, test_only, images):
    if type(test_only) is not bool or mode not in {'gateway', 'direct_fixture'} or not isinstance(images, dict):
        raise CaptureHeld('unknown capture transport contract')
    if set(images) != {'gateway', 'recorder'}:
        raise CaptureHeld('unknown capture images')
    if mode == 'direct_fixture' and (test_only is not True or images['gateway'] is not None):
        raise CaptureHeld('direct fixture capture must remain test-only without a gateway')
    for value in (images.values() if mode == 'gateway' else (images['recorder'],)):
        if not isinstance(value, str) or not re.fullmatch('sha256:[0-9a-f]{64}', value):
            raise CaptureHeld('images must be resolved immutable identities')


def deployment(value, origins):
    if (not isinstance(value, dict) or set(value) != {'deployment_id', 'revision', 'origin', 'descriptor_id'}
            or any(not isinstance(v, str) or not v for v in value.values())
            or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', value['revision'])
            or value['origin'] not in origins):
        raise CaptureHeld('trusted deployment descriptor is missing or disagrees with target')
    canonical_origin(value['origin'])
    return deepcopy(value)


@dataclass(frozen=True)
class Identity:
    run_id: str
    execution_key: str
    execution_id: int
    attempt: int
    fence: int

    def document(self):
        if (not self.run_id or not self.execution_key
                or any(type(v) is not int or v <= 0 for v in (self.execution_id, self.attempt, self.fence))):
            raise CaptureHeld('invalid execution identity')
        return dict(vars(self))


class Capture:
    def __init__(self, identity, authority, media, policy, deployment_start, requirements,
                 *, gateway_image, recorder_image, ca_fingerprint, recording_id=None,
                 transport_mode='gateway'):
        self.identity = identity.document()
        self.authority, self.media = Path(authority).resolve(), Path(media).resolve()
        if self.authority.is_relative_to(self.media) or self.media.is_relative_to(self.authority):
            raise CaptureHeld('recording and authority directories overlap')
        if policy.get('execution_key') != identity.execution_key:
            raise CaptureHeld('policy belongs to another execution')
        self.origins = [d['origin'] for d in policy['destinations']]
        self.deployment = deployment(deployment_start, self.origins)
        self.policy = deepcopy(policy)
        transport(transport_mode, policy.get('test_only'), {'gateway': gateway_image, 'recorder': recorder_image})
        if not re.fullmatch('[0-9a-f]{64}', ca_fingerprint):
            raise CaptureHeld('missing public CA fingerprint')
        if not requirements or any(not re.fullmatch(r'AC-[1-9][0-9]*', r) for r in requirements) or len(set(requirements)) != len(requirements):
            raise CaptureHeld('capture needs exact unique requirement IDs')
        self.recording_id = recording_id or uuid4().hex
        if not re.fullmatch('[0-9a-f]{32}', self.recording_id):
            raise CaptureHeld('invalid recording identity')
        self.images = {'gateway': gateway_image, 'recorder': recorder_image}
        self.transport_mode = transport_mode
        self.ca = ca_fingerprint
        self.requirements = list(requirements)
        self.outcomes = []
        self.started_at, self.started_clock = time.time(), time.monotonic()
        self.closed = False

    def outcome(self, command_id, requirement, passed):
        if (self.closed or type(passed) is not bool or requirement not in self.requirements
                or not isinstance(command_id, str) or not re.fullmatch('[A-Za-z0-9_-]{1,80}', command_id)
                or any(o['command_id'] == command_id for o in self.outcomes)):
            raise CaptureHeld('invalid or duplicate controller outcome')
        self.outcomes.append({'command_id': command_id, 'requirement': requirement, 'passed': passed,
                              'controller_elapsed_seconds': time.monotonic()-self.started_clock})

    def seal(self, deployment_end, files, *, writers_closed, probe=evidence_manifest.probe_video):
        if self.closed or writers_closed is not True:
            raise CaptureHeld('recording writers must close exactly once before sealing')
        self.closed = True
        transport(self.transport_mode, self.policy.get('test_only'), self.images)
        if deployment(deployment_end, self.origins) != self.deployment:
            raise CaptureHeld('deployment changed during capture')
        if ({o['requirement'] for o in self.outcomes} != set(self.requirements)
                or any(o['passed'] is not True for o in self.outcomes)):
            raise CaptureHeld('requirements are missing or failed')
        if not files or set(files) != {'video', 'trace'}:
            raise CaptureHeld('capture requires one video and one trace')
        media = {}
        for kind, name in files.items():
            if not isinstance(name, str) or Path(name).name != name:
                raise CaptureHeld('media filename must be a confined basename')
            path = confined(self.media, (name,))
            before = path.stat()
            if before.st_nlink != 1 or not 0 < before.st_size <= 256*1024*1024:
                raise CaptureHeld('invalid media file')
            encoded = hashlib.sha256(path.read_bytes()).hexdigest()
            metadata = probe(path) if kind == 'video' else {}
            if kind == 'video' and metadata.get('decoded') is not True:
                raise CaptureHeld('video did not fully decode')
            after = path.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                raise CaptureHeld('media changed while sealing')
            media[kind] = {'name': name, 'sha256': encoded, 'bytes': after.st_size, **metadata}
        record = {'kind': 'qa_capture', 'version': 2, **self.identity,
                  'recording_id': self.recording_id, 'images': self.images, 'ca_fingerprint': self.ca,
                  'policy_sha256': digest(self.policy), 'test_only': self.policy.get('test_only', True),
                  'transport_mode': self.transport_mode,
                  'deployment': self.deployment, 'deployment_sha256': digest(self.deployment),
                  'started_at': self.started_at, 'finished_at': time.time(),
                  'requirements': self.requirements, 'outcomes': self.outcomes, 'media': media}
        self.authority.mkdir(parents=True, exist_ok=True)
        path = confined(self.authority, (self.recording_id + '.json',))
        if path.exists():
            raise CaptureHeld('recording identity already sealed')
        atomic_json(path, record)
        return deepcopy(record)


def verify(authority, media, recording_id, expected_identity, expected_deployment, *, probe=evidence_manifest.probe_video):
    if not re.fullmatch('[0-9a-f]{32}', recording_id):
        raise CaptureHeld('invalid recording identity')
    location = confined(Path(authority), (recording_id + '.json',))
    if location.stat().st_size > 1000000:
        raise CaptureHeld('oversized capture receipt')
    record = json.loads(location.read_text())
    transport(record.get('transport_mode'), record.get('test_only'), record.get('images'))
    if (record.get('kind') != 'qa_capture' or record.get('version') != 2
            or any(record.get(k) != v for k, v in expected_identity.document().items())
            or record.get('recording_id') != recording_id or record.get('deployment') != expected_deployment
            or digest(expected_deployment) != record.get('deployment_sha256')
            or not record.get('requirements') or not record.get('outcomes')
            or {o['requirement'] for o in record['outcomes']} != set(record['requirements'])
            or any(o['passed'] is not True for o in record['outcomes'])):
        raise CaptureHeld('capture identity, deployment or requirement outcomes differ')
    for kind in ('video', 'trace'):
        item = record['media'][kind]
        path = confined(Path(media), (item['name'],))
        if path.stat().st_size != item['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise CaptureHeld('media bytes differ from controller capture')
        if kind == 'video' and probe(path).get('decoded') is not True:
            raise CaptureHeld('video cannot be decoded')
    return record


async def persist(conn, lease, record):
    transport(record.get('transport_mode'), record.get('test_only'), record.get('images'))
    if record['execution_id'] != lease.execution_id or record['fence'] != lease.fence or record['run_id'] != lease.run_id:
        raise CaptureHeld('receipt differs from execution lease')
    async with leases.fenced_transaction(conn, lease):
        attempt = await conn.fetchrow('SELECT attempt, idempotency_key FROM stage_executions WHERE id=$1', lease.execution_id)
        if not attempt or attempt['attempt'] != record['attempt'] or attempt['idempotency_key'] != record['execution_key']:
            raise CaptureHeld('receipt differs from durable attempt identity')
        await conn.execute("UPDATE stage_executions SET output=coalesce(output,'{}'::jsonb)||jsonb_build_object('qa_capture',$2::jsonb) WHERE id=$1", lease.execution_id, json.dumps(record, allow_nan=False))
