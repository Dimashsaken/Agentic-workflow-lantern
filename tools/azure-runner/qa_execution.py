"""Controller QA-stage capture orchestration, never a model-supplied attestation.

External transport remains unaccepted. The direct TLS hook is solely for explicit
local integration tests; the fleet entry point cannot select that exception.
"""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import time

import execution_leases as leases
from qa_provenance import Capture, CaptureHeld, Identity, persist, deployment, transport
from qa_recorder_worker import validate
from qa_transport import Policy, launch_external
from tool_policy import confined

QA_STAGES = {'04-qa-dev', '07-qa-staging', '05-regression'}


async def quiesce(stop):
    """Do not return a cancelled attempt while its recorder can still write."""
    task = asyncio.create_task(stop())
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    task.result()  # cleanup failure holds; never seal it as success
    if cancelled:
        raise asyncio.CancelledError


def live_policy(document):
    policy = Policy.load(document)
    now = time.time()
    if now < policy.created_at or any(now >= d.expires_at for d in policy.destinations.values()):
        raise CaptureHeld('QA destination policy expired')
    return policy


async def execute_capture(conn, lease, spec, *, launch, stop, observe_deployment,
                          allow_direct_fixture=False):
    spec = deepcopy(spec)
    policy = live_policy(spec['policy'])
    mode = spec['transport_mode']
    transport(mode, policy.test_only, spec['images'])
    if mode == 'direct_fixture':
        if allow_direct_fixture is not True or policy.test_only is not True:
            raise CaptureHeld('direct TLS capture is available only to explicit local tests')
    else:
        # Call the same unconditionally held activation gate as the fleet. An
        # injected callback or image-shaped string cannot bypass host acceptance.
        launch_external(spec)
    async with leases.fenced_transaction(conn, lease):
        row = await conn.fetchrow('SELECT run_id,stage,attempt,idempotency_key FROM stage_executions WHERE id=$1', lease.execution_id)
        if not row or row['run_id'] != lease.run_id or row['stage'] not in QA_STAGES:
            raise CaptureHeld('capture does not belong to a QA execution')
        identity = Identity(lease.run_id, row['idempotency_key'], lease.execution_id, row['attempt'], lease.fence)
    if identity.execution_key != policy.execution_key:
        raise CaptureHeld('policy belongs to another QA attempt')
    origins = [d.origin for d in policy.destinations.values()]
    expected = deployment(spec['deployment'], origins)
    if await observe_deployment() != expected:
        raise CaptureHeld('trusted deployed revision differs before QA')
    capture = Capture(identity, spec['authority'], spec['media'], policy.document(), expected,
                      spec['requirements'], gateway_image=spec['images']['gateway'],
                      recorder_image=spec['images']['recorder'], ca_fingerprint=spec['ca_fingerprint'],
                      transport_mode=mode)
    plan = validate({'recording_id': capture.recording_id, 'origins': origins,
                     'viewport': spec['viewport'], 'actions': spec['actions']})
    if {a['requirement'] for a in plan['actions']} != set(capture.requirements):
        raise CaptureHeld('controller recording plan does not map every required criterion')
    async with leases.fenced_transaction(conn, lease):
        live_policy(spec['policy'])
    try:
        outcome = await launch(plan)
    finally:
        await quiesce(stop)
    if (not isinstance(outcome, dict) or outcome.get('recording_id') != capture.recording_id
            or outcome.get('writers_closed') is not True or not isinstance(outcome.get('outcomes'), list)):
        raise CaptureHeld('recorder did not close the commanded recording')
    results = outcome['outcomes']
    expected_actions = [(a['id'], a['requirement']) for a in plan['actions']]
    if (len(results) != len(expected_actions)
            or any(not isinstance(r, dict) or set(r) != {'command_id', 'requirement', 'passed'}
                   or type(r['passed']) is not bool for r in results)
            or [(r['command_id'], r['requirement']) for r in results] != expected_actions):
        raise CaptureHeld('recorder outcomes differ from exact controller commands')
    for result in results:
        capture.outcome(**result)
    async with leases.fenced_transaction(conn, lease):
        live_policy(spec['policy'])
    observed_end = await observe_deployment()
    # Decode/hashing may be slow. The execution heartbeat must continue throughout.
    from maintenance_runtime import joined_thread
    record = await joined_thread(lambda: capture.seal(observed_end, outcome['files'], writers_closed=True))
    async with leases.fenced_transaction(conn, lease):
        live_policy(spec['policy'])
        await persist(conn, lease, record)
    return record


async def capture_stage(conn, run_id, stage):
    """Optional fleet entry. Configuration is outside product/worker authority.

    No implicit deployment origin or revision is inferred from checkout HEAD.
    A missing config is held only when the pilot is explicitly configured.
    """
    root = os.environ.get('LANTERN_QA_CAPTURE_CONFIG_ROOT')
    if not root or stage not in QA_STAGES:
        return None
    import execution_runtime as ownership
    current = ownership.STAGE.get()
    if not current or current.lease.run_id != run_id:
        raise CaptureHeld('QA capture requires an owned stage execution')
    path = confined(Path(root).resolve(), (run_id, stage + '.json'))
    if path.stat().st_size > 64000:
        raise CaptureHeld('oversized controller QA configuration')
    spec = json.loads(path.read_text())
    if spec.get('transport_mode') != 'gateway' or spec.get('policy', {}).get('test_only') is not False:
        raise CaptureHeld('fleet QA requires verified external gateway transport')
    # No adapter is handed a browser or authority directory before it has passed
    # actual host/image acceptance. Today this raises, leaving the execution held.
    adapter = launch_external(spec)
    return await execute_capture(conn, current.lease, spec, launch=adapter.run,
                                 stop=adapter.stop, observe_deployment=adapter.observe_deployment)
