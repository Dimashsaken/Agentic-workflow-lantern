"""Dedicated maintenance authority; never impersonates the stage dispatcher.

This opt-in controller path shares the run-row lock with dispatch. A maintenance
lease binds the complete human approval, target and run position. Expired attempts
remain held until explicit recovery; they are never stolen or automatically replayed.
"""
from contextlib import asynccontextmanager
import asyncio
import json
import os
from uuid import uuid4

import execution_leases as leases
import github_publication as publication

STAGE = '03-coding.babysit'


async def joined_thread(function, *args):
    """Cancel registered workers and join the actual thread before returning."""
    from isolated_tools import WorkerCancellation, CURRENT_CANCELLATION
    cancellation = WorkerCancellation()
    token = CURRENT_CANCELLATION.set(cancellation)
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        async def drain(pending):
            while not pending.done():
                try:
                    await asyncio.shield(pending)
                except asyncio.CancelledError:
                    continue  # Repeated cancellation cannot orphan the worker thread.
                except Exception:
                    break
            return pending.result()
        stopping = asyncio.create_task(asyncio.to_thread(cancellation.stop))
        try:
            await drain(stopping)
        finally:
            try:
                await drain(task)
            except Exception:
                pass
        raise
    finally:
        CURRENT_CANCELLATION.reset(token)


def enabled():
    return os.environ.get('LANTERN_FENCED_BABYSIT') == '1'


def decoded(value):
    return json.loads(value) if isinstance(value, str) else value


async def legacy_claim(conn, run_id):
    """Even flag-disabled dispatch must serialize with a maintenance claimant.

    A NOT EXISTS predicate in the locking UPDATE uses its earlier MVCC snapshot;
    it can miss maintenance inserted while waiting for the row lock. Read again
    in a separate statement after acquiring that lock.
    """
    async with conn.transaction():
        row = await conn.fetchrow('SELECT status FROM runs WHERE id=$1 FOR UPDATE', run_id)
        if not row or row['status'] != 'running':
            return 'UPDATE 0'
        if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM stage_executions WHERE run_id=$1 AND stage=$2 AND status='running')", run_id, STAGE):
            return 'UPDATE 0'
        return await conn.execute("UPDATE runs SET status='executing',updated_at=clock_timestamp() WHERE id=$1", run_id)


async def binding(conn, run):
    """Called under the run lock. Reject legacy approvals without a bound target."""
    if (not run or run['coding_mode'] != 'auto'
            or run['status'] not in {'running', 'waiting_gate', 'done'}
            or run['current_stage'].split('.', 1)[0] not in
            {'04-qa-dev', '05-post-coding', '06-security', '07-qa-staging'}
            or run['lease_owner'] is not None):
        raise leases.LeaseLost('run is not eligible for maintenance')
    approval = await conn.fetchrow("SELECT * FROM approvals WHERE run_id=$1 AND gate='code_complete' ORDER BY id DESC LIMIT 1 FOR UPDATE", run['id'])
    if (not approval or approval['status'] != 'approved' or not approval['decided_by']
            or approval['decided_at'] is None):
        raise leases.LeaseLost('latest code_complete decision is not human-approved')
    payload = decoded(approval['payload']) or {}
    request = payload.get('publication_request')
    if not isinstance(request, dict) or request.get('version') != 3:
        raise leases.LeaseLost('approval lacks a v3 publication target')
    owner, name = publication.destination(request)
    if (type(payload.get('pr_number')) is not int or payload['pr_number'] <= 0
            or payload.get('pr_url') != f"https://github.com/{owner}/{name}/pull/{payload['pr_number']}"):
        raise leases.LeaseLost('approval lacks an exact PR identity')
    if (request.get('run_id') != run['id'] or request.get('repo') != run['product_repo']
            or request.get('base') != run['product_branch']
            or request.get('branch') != run['product_working_branch']):
        raise leases.LeaseLost('approved publication target differs from run')
    rework = await conn.fetchrow("SELECT id, at FROM events WHERE run_id=$1 AND type IN ('run_reworked','run_retried') ORDER BY id DESC LIMIT 1 FOR UPDATE", run['id'])
    if rework and rework['at'] >= approval['decided_at']:
        raise leases.LeaseLost('rework/retry superseded the approval')
    if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM approvals WHERE run_id=$1 AND id>$2 AND status IN ('pending','rejected'))", run['id'], approval['id']):
        raise leases.LeaseLost('a later human decision is pending or rejected')
    # Include decision identity, not just an approved flag. No approval is updated.
    decision = {k: (v.isoformat() if hasattr(v, 'isoformat') else decoded(v) if k == 'payload' else v)
                for k, v in dict(approval).items()}
    return {'version': 1, 'approval_id': approval['id'],
            'approval_sha256': leases.request_hash(decision), 'publication_request': request,
            'pr_number': payload['pr_number'], 'pr_url': payload['pr_url'],
            'run_stage': run['current_stage'], 'run_status': run['status'],
            'run_fence': run['lease_fence'], 'rework_event': rework['id'] if rework else None}


async def acquire(conn, run_id, owner, runner='ec2', ttl=120):
    if not owner:
        raise ValueError('maintenance owner must be nonempty')
    ttl = leases._ttl(ttl)
    async with conn.transaction():
        run = await conn.fetchrow('SELECT * FROM runs WHERE id=$1 FOR UPDATE', run_id)
        snapshot = await binding(conn, run)
        if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM stage_executions WHERE run_id=$1 AND status='running')", run_id):
            raise leases.LeaseLost('another execution owns the run; recover expired work first')
        if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM execution_effects WHERE run_id=$1 AND status<>'confirmed')", run_id):
            raise leases.LeaseLost('publication effects require reconciliation')
        attempt = await conn.fetchval('SELECT coalesce(max(attempt),0)+1 FROM stage_executions WHERE run_id=$1 AND stage=$2', run_id, STAGE)
        execution_id = await conn.fetchval("""INSERT INTO stage_executions
          (run_id,stage,runner,attempt,idempotency_key,input,lease_owner,lease_fence,lease_expires_at,heartbeat_at)
          VALUES($1,$2,$3,$4,$5,$6::jsonb,$7,1,clock_timestamp()+$8 * interval '1 second',clock_timestamp()) RETURNING id""",
          run_id, STAGE, runner, attempt, f'{run_id}:{STAGE}:{attempt}', json.dumps(snapshot), owner, ttl)
        return leases.Lease(run_id, owner, 1, execution_id, None, True)


async def assert_current(conn, lease):
    run = await conn.fetchrow('SELECT * FROM runs WHERE id=$1 FOR UPDATE', lease.run_id)
    current = await binding(conn, run)
    child = await conn.fetchrow('SELECT * FROM stage_executions WHERE id=$1 FOR UPDATE', lease.execution_id)
    now = await conn.fetchval('SELECT clock_timestamp()')
    if (not child or child['run_id'] != lease.run_id or child['stage'] != STAGE
            or child['status'] != 'running' or child['lease_owner'] != lease.owner
            or child['lease_fence'] != lease.fence or child['lease_expires_at'] is None
            or child['lease_expires_at'] <= now or decoded(child['input']) != current):
        raise leases.LeaseLost('maintenance ownership or approval binding changed')


async def recover(conn):
    """Fence expired or invalidated maintenance only; preserve run/gate position."""
    recovered = []
    async with conn.transaction():
        runs = await conn.fetch("SELECT * FROM runs r WHERE EXISTS(SELECT 1 FROM stage_executions e WHERE e.run_id=r.id AND e.stage=$1 AND e.status='running') ORDER BY id FOR UPDATE SKIP LOCKED", STAGE)
        for run in runs:
            rows = await conn.fetch("SELECT * FROM stage_executions WHERE run_id=$1 AND stage=$2 AND status='running' ORDER BY id FOR UPDATE", run['id'], STAGE)
            for row in rows:
                lease = leases.Lease(run['id'], row['lease_owner'], row['lease_fence'], row['id'], None, True)
                try:
                    await assert_current(conn, lease)
                    continue
                except (leases.LeaseLost, publication.PublicationHeld, ValueError, TypeError):
                    pass
                await conn.execute("UPDATE execution_effects SET status='uncertain',updated_at=clock_timestamp() WHERE stage_execution_id=$1 AND status='intended'", row['id'])
                await conn.execute("UPDATE stage_executions SET status='failed',error='Maintenance interrupted; reconcile effects before retry',error_class='terminal',lease_owner=NULL,lease_expires_at=NULL,lease_fence=lease_fence+1,finished_at=clock_timestamp() WHERE id=$1", row['id'])
                await conn.execute("INSERT INTO events(run_id,actor,type,data) VALUES($1,'orchestrator','maintenance_recovered',$2::jsonb)", run['id'], json.dumps({'execution_id': row['id']}))
                recovered.append(row['id'])
    return recovered


async def finish(conn, lease, result):
    async with leases.fenced_transaction(conn, lease):
        await conn.execute("UPDATE stage_executions SET output=$2::jsonb WHERE id=$1", lease.execution_id, json.dumps(result, allow_nan=False))
        await leases.release(conn, lease, 'succeeded' if result.get('outcome') in {'updated', 'up_to_date'} else 'failed')


async def babysit(conn, run_id, runner, force=False):
    """Both entry points use this gate. Red regates hold before publication."""
    if not enabled():
        raise RuntimeError('babysitting is held: fenced mode is disabled; set LANTERN_FENCED_BABYSIT only for reviewed pilots')
    import pipeline
    import tool_execution
    if not tool_execution.enabled():
        raise RuntimeError('fenced babysitting requires isolated tools')
    lease = await acquire(conn, run_id, 'maintenance:' + uuid4().hex, runner)
    async with leases.lease_guard(pipeline.connect, lease) as guard:
        result = await run_pass(conn, lease, pipeline, force=force)
        await guard.stop()
        await finish(conn, lease, result)
        return result


async def run_pass(conn, lease, controller, force=False):
    """Observe an existing PR, trial merge, immutable regate, then conditional push.

    Force affects backoff only. No review, PR creation, notification or agent fix
    executes here. Red needs a human until inherited fix authority is implemented.
    """
    import review
    import tempfile
    from pathlib import Path
    from isolated_tools import IsolatedToolWorker
    import tool_execution
    import trusted_evidence
    import factory

    async with leases.fenced_transaction(conn, lease):
        row = await conn.fetchrow('SELECT input FROM stage_executions WHERE id=$1', lease.execution_id)
        snapshot = decoded(row['input'])
        approved = snapshot['publication_request']
    # Freeze fresh base but require the approved head (or a previously accepted
    # maintenance receipt) so a third-party branch edit cannot inherit approval.
    previous = await conn.fetchrow("SELECT output FROM stage_executions WHERE run_id=$1 AND stage=$2 AND status='succeeded' ORDER BY id DESC LIMIT 1", lease.run_id, STAGE)
    expected = approved['head_sha']
    if previous:
        prior = decoded(previous['output']) or {}
        if prior.get('approval_request_sha256') == leases.request_hash(approved):
            expected = prior.get('head_sha', expected)
    probe = {k: v for k, v in approved.items() if k != 'base_sha'}
    probe.update(version=1, head_sha=expected)
    observation = await asyncio.to_thread(publication.observe, controller._gh_api, probe)
    if not observation.complete(probe) or observation.pr['number'] != snapshot['pr_number']:
        raise publication.PublicationHeld('approved branch/PR moved or is no longer open')
    repository_id, base_sha = await asyncio.to_thread(publication._repository_and_base, controller._gh_api, approved)
    if repository_id != approved['repository_id']:
        raise publication.PublicationHeld('repository identity changed')
    mirror = await asyncio.to_thread(controller.sync_product_mirror, approved['repo'])
    if review._sha('refs/heads/' + approved['base'], mirror) != base_sha or review._sha('refs/heads/' + approved['branch'], mirror) != expected:
        raise publication.PublicationHeld('mirror differs from observed provider refs')
    if review._is_ancestor(base_sha, expected, mirror):
        current = {**approved, 'base_sha': base_sha, 'head_sha': expected}
        observed = await asyncio.to_thread(publication.observe, controller._gh_api, current)
        if not observed.complete(current) or observed.pr['number'] != snapshot['pr_number']:
            raise publication.PublicationHeld('provider moved before up-to-date acceptance')
        return {'outcome': 'up_to_date', 'head_sha': expected, 'base_sha': base_sha,
                'approval_request_sha256': leases.request_hash(approved)}
    trial = await asyncio.to_thread(review.trial_merge, mirror, approved['base'], approved['branch'], lease.run_id, (controller.GIT_AUTHOR_NAME, controller.GIT_AUTHOR_EMAIL))
    clone = Path(trial['clone'])
    if trial.get('base_sha') != base_sha:
        raise publication.PublicationHeld('trial base moved during mirror clone')
    if trial['clean']:
        parents = review._git('rev-list', '--parents', '-n', '1', trial['merge_sha'], cwd=clone).stdout.split()
        if parents != [trial['merge_sha'], expected, base_sha]:
            raise publication.PublicationHeld('trial merge ancestry differs from approved head and observed base')
    # A cancelled to_thread operation may still own files. Retain this checkout;
    # only the retention protocol may retire it after worker quiescence.
    if not trial['clean']:
        return {'outcome': 'conflict', 'files': trial['files']}
    def regate():
        with tempfile.TemporaryDirectory(prefix='lantern-maintenance-output-') as media:
            worker = IsolatedToolWorker(clone, Path(media), f'{lease.run_id}:{STAGE}:{lease.execution_id}', controller.SANDBOX_IMAGE)
            token = tool_execution.CURRENT.set(worker)
            try:
                worker._pin_image()
                with trusted_evidence.quality_snapshot(clone) as snapshot, snapshot.bind():
                    return review.regate_local(snapshot.root, lease.run_id, f'{lease.run_id}:{STAGE}:{lease.execution_id}')
            finally:
                worker.stop()
                tool_execution.CURRENT.reset(token)
    gate = await joined_thread(regate)
    if gate.get('passed') is not True:
        return {'outcome': 'regate_red', 'fix': 'held: inherited maintenance fix authority is not enabled'}
    request = {**approved, 'base_sha': base_sha, 'head_sha': trial['merge_sha'], 'expected_remote_sha': expected}
    key = 'maintenance:' + leases.request_hash(request)
    effect = await leases.begin_effect(conn, lease, key, 'maintenance_branch', request, {'publication_request': request})
    observed = await asyncio.to_thread(publication.observe, controller._gh_api, request)
    if observed.pr is None or observed.pr['number'] != snapshot['pr_number'] or observed.pr['state'] != 'open':
        raise publication.PublicationHeld('approved PR identity or state changed')
    if observed.head != request['head_sha']:
        if not effect.created or observed.head != expected:
            raise publication.PublicationHeld('maintenance publication is uncertain or remote changed')
        async with leases.fenced_transaction(conn, lease):
            pass
        await asyncio.to_thread(publication.push_cas, controller._git, controller._authed(approved['repo']), approved['branch'], request['head_sha'], expected, clone)
        observed = await asyncio.to_thread(publication.observe, controller._gh_api, request)
    result = publication.receipt(request, observed)
    if result['pr_number'] != snapshot['pr_number']:
        raise publication.PublicationHeld('PR identity changed after maintenance publication')
    await leases.confirm_effect(conn, lease, key, result['pr_url'], result)
    return {**result, 'outcome': 'updated', 'approval_request_sha256': leases.request_hash(approved)}
