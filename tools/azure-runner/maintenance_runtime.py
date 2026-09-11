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
FIX_STAGE = '03-coding.fix'


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


async def joined_task(coroutine):
    """Quiesce model/tool work even when cancellation arrives repeatedly."""
    from isolated_tools import WorkerCancellation, CURRENT_CANCELLATION
    cancellation = WorkerCancellation()
    token = CURRENT_CANCELLATION.set(cancellation)
    task = asyncio.create_task(coroutine)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        task.cancel()
        stopped = asyncio.create_task(asyncio.to_thread(cancellation.stop))
        for pending in (stopped, task):
            while not pending.done():
                try:
                    await asyncio.shield(pending)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            try:
                pending.result()
            except BaseException:
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
    if lease.maintenance_parent is not None:
        parent = leases.Lease(lease.run_id, lease.owner, lease.parent_fence,
                              lease.maintenance_parent, maintenance=True)
        await assert_current(conn, parent)
        row = await conn.fetchrow('SELECT * FROM stage_executions WHERE id=$1 FOR UPDATE', lease.execution_id)
        now = await conn.fetchval('SELECT clock_timestamp()')
        authority = decoded(row['input']) if row else {}
        if (not row or row['run_id'] != lease.run_id or row['stage'] != FIX_STAGE
                or row['status'] != 'running' or row['lease_owner'] != lease.owner
                or row['lease_fence'] != lease.fence or row['lease_expires_at'] is None
                or row['lease_expires_at'] <= now or not isinstance(authority, dict)
                or authority.get('maintenance_parent') != parent.execution_id
                or authority.get('maintenance_fence') != parent.fence
                or not lease.authority_sha256 or leases.request_hash(authority) != lease.authority_sha256):
            raise leases.LeaseLost('inherited maintenance fix authority changed')
        return
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
                await conn.execute("UPDATE stage_executions SET status='failed',error='Parent maintenance authority lost',error_class='terminal',lease_owner=NULL,lease_expires_at=NULL,lease_fence=lease_fence+1,finished_at=clock_timestamp() WHERE run_id=$1 AND stage=$2 AND status='running' AND input->>'maintenance_parent'=$3", run['id'], FIX_STAGE, str(row['id']))
                await conn.execute("UPDATE execution_effects SET status='uncertain',updated_at=clock_timestamp() WHERE stage_execution_id=$1 AND status='intended'", row['id'])
                await conn.execute("UPDATE stage_executions SET status='failed',error='Maintenance interrupted; reconcile effects before retry',error_class='terminal',lease_owner=NULL,lease_expires_at=NULL,lease_fence=lease_fence+1,finished_at=clock_timestamp() WHERE id=$1", row['id'])
                await conn.execute("INSERT INTO events(run_id,actor,type,data) VALUES($1,'orchestrator','maintenance_recovered',$2::jsonb)", run['id'], json.dumps({'execution_id': row['id']}))
                recovered.append(row['id'])
    return recovered


async def run_fix(conn, parent, controller, clone, gate, contract, image_id, merge_sha, base_sha):
    """One child, at most the existing fix budget; no dispatcher lease or push."""
    import factory
    import execution_runtime as ownership
    from pathlib import Path
    rounds = min(factory.fix_rounds(), 10)
    if not rounds:
        raise publication.PublicationHeld('maintenance automatic fix budget is zero')
    scope = factory.write_scope(parent.run_id)
    if not scope or contract.get('error'):
        raise publication.PublicationHeld('maintenance fix needs approved scope and immutable quality policy')
    async with leases.fenced_transaction(conn, parent):
        source = decoded(await conn.fetchval('SELECT input FROM stage_executions WHERE id=$1', parent.execution_id))
        attempt = await conn.fetchval('SELECT coalesce(max(attempt),0)+1 FROM stage_executions WHERE run_id=$1 AND stage=$2', parent.run_id, FIX_STAGE)
        execution_key = f'{parent.run_id}:{FIX_STAGE}:{attempt}'
        authority = {'version': 1, 'maintenance_parent': parent.execution_id,
                     'maintenance_fence': parent.fence, 'binding': source,
                     'merge_sha': merge_sha, 'base_sha': base_sha, 'quality_sha256': contract['sha256'],
                     'write_scope': scope, 'max_turns': rounds, 'image_id': image_id}
        child_id = await conn.fetchval("""INSERT INTO stage_executions
          (run_id,stage,runner,attempt,idempotency_key,input,lease_owner,lease_fence,lease_expires_at,heartbeat_at)
          VALUES($1,$2,'host',$3,$4,$5::jsonb,$6,1,clock_timestamp()+interval '120 seconds',clock_timestamp()) RETURNING id""",
          parent.run_id, FIX_STAGE, attempt, execution_key, json.dumps(authority), parent.owner)
    child = leases.Lease(parent.run_id, parent.owner, 1, child_id, parent.fence, True, parent.execution_id, leases.request_hash(authority))
    fix_root = Path(os.environ.get('LANTERN_MAINTENANCE_CHECKOUTS', str(Path.home()/'.lantern/maintenance-checkouts')))
    fix_clone = fix_root / uuid4().hex
    def prepare():
        import review
        from execution_retention import allocation
        with allocation(fix_clone, fix_root, execution_key, parent.run_id):
            result = review._git('clone', '--quiet', '--no-hardlinks', '--config', 'core.autocrlf=false',
                                 str(clone), str(fix_clone))
            if result.returncode:
                raise publication.PublicationHeld('maintenance fix clone failed')
            # Clone transfers local refs, not the trial's remote tracking refs.
            # Preserve the already observed merge parent for normal handoff checks.
            base_ref = 'refs/remotes/origin/' + source['publication_request']['base']
            result = review._git('update-ref', base_ref, base_sha, cwd=fix_clone)
            if result.returncode:
                raise publication.PublicationHeld('maintenance base ref could not be pinned')
    try:
        async with leases.lease_guard(controller.connect, child) as guard:
            token = ownership.STAGE.set(ownership.Ownership(child, guard))
            output_token = factory.MAINTENANCE_OUTPUT.set(leases.request_hash(execution_key)[:24])
            try:
                await joined_thread(prepare)
                async with leases.fenced_transaction(conn, child):
                    pass
                task = ('\n\n## Inherited maintenance regate fix\n'
                        'Fix only the red regate after the approved base merge. Do not add features, '
                        'change the quality policy, publish, or change gates. Commit fixes and append '
                        'a Regate fix report; use append_memory. The host independently revalidates '
                        'committed source before any publication.\n'
                        f'Write this execution report under workflow/runs/{parent.run_id}/{factory.exec_dir("03-coding")}/report.md.\n'
                        + factory.gate_failure_brief(gate))
                options = {'checkout': fix_clone, 'start_sha': merge_sha, 'image_id': image_id,
                           'task': task, 'max_rounds': rounds-1, 'authority': authority}
                async with controller.INPROCESS_STAGE_LOCK:
                    await joined_task(controller._run_agent_stage(conn, parent.run_id, FIX_STAGE, 'host',
                                                      (attempt, execution_key, child_id), maintenance_fix=options))
            finally:
                factory.MAINTENANCE_OUTPUT.reset(output_token)
                ownership.STAGE.reset(token)
    except BaseException as error:
        # Parent may already be fenced; in that case recovery owns the terminal row.
        try:
            async with leases.fenced_transaction(conn, child):
                await conn.execute("UPDATE stage_executions SET status='failed',error=$2,error_class='terminal',lease_owner=NULL,lease_expires_at=NULL,finished_at=clock_timestamp() WHERE id=$1", child_id, factory.redact(str(error) or type(error).__name__)[:4000])
        except leases.LeaseLost:
            pass
        raise
    async with leases.fenced_transaction(conn, parent):
        finished = await conn.fetchrow('SELECT status,input FROM stage_executions WHERE id=$1', child_id)
        if (not finished or finished['status'] != 'succeeded'
                or decoded(finished['input']) != authority or factory.write_scope(parent.run_id) != scope):
            raise publication.PublicationHeld('maintenance child did not complete its bound contract')
    return fix_clone, execution_key, child_id, scope


async def finish(conn, lease, result):
    async with leases.fenced_transaction(conn, lease):
        await conn.execute("UPDATE stage_executions SET output=$2::jsonb WHERE id=$1", lease.execution_id, json.dumps(result, allow_nan=False))
        await leases.release(conn, lease, 'succeeded' if result.get('outcome') in {'updated', 'up_to_date'} else 'failed')


async def babysit(conn, run_id, runner, force=False):
    """Both entry points share maintenance authority and its bounded fix path."""
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

    Force affects backoff only. Fix children inherit maintenance authority, never
    dispatcher ownership. Conflicts, exhausted fixes and stale observations hold.
    """
    import review
    import tempfile
    from pathlib import Path
    from isolated_tools import IsolatedToolWorker
    import tool_execution
    import trusted_evidence
    import factory
    from execution_retention import allocation

    async with leases.fenced_transaction(conn, lease):
        row = await conn.fetchrow('SELECT input FROM stage_executions WHERE id=$1', lease.execution_id)
        snapshot = decoded(row['input'])
        execution_key = await conn.fetchval('SELECT idempotency_key FROM stage_executions WHERE id=$1', lease.execution_id)
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
    checkout_root = Path(os.environ.get('LANTERN_MAINTENANCE_CHECKOUTS', str(Path.home()/'.lantern/maintenance-checkouts')))
    trial_path = checkout_root / uuid4().hex
    def prepare_trial():
        with allocation(trial_path, checkout_root, execution_key, lease.run_id):
            return review.trial_merge(mirror, approved['base'], approved['branch'], lease.run_id,
                                      (controller.GIT_AUTHOR_NAME, controller.GIT_AUTHOR_EMAIL), clone=trial_path)
    trial = await joined_thread(prepare_trial)
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
    image_id = None
    contract = factory.quality_config(clone)
    final_sha = trial['merge_sha']
    fixed_scope = None
    def regate():
        nonlocal image_id
        with tempfile.TemporaryDirectory(prefix='lantern-maintenance-output-') as media:
            worker = IsolatedToolWorker(clone, Path(media), execution_key, image_id or controller.SANDBOX_IMAGE)
            token = tool_execution.CURRENT.set(worker)
            try:
                worker._pin_image()
                image_id = worker.image_id
                if fixed_scope is not None:
                    changes = factory.changed_files_since(clone, trial['merge_sha'])
                    if factory.check_write_scope(lease.run_id, changes, scope=fixed_scope):
                        raise publication.PublicationHeld('maintenance fix changed scope or quality policy')
                with trusted_evidence.quality_snapshot(clone) as frozen, frozen.bind():
                    if frozen.before['head_sha'] != final_sha or factory.quality_config(frozen.root) != contract:
                        raise publication.PublicationHeld('maintenance source or quality policy changed')
                    result = review.regate_local(frozen.root, lease.run_id, execution_key)
                if trusted_evidence.capture_before(clone) != frozen.before:
                    raise publication.PublicationHeld('maintenance source changed while regating')
                return {**result, 'source': frozen.before, 'image_id': image_id}
            finally:
                worker.stop()
                tool_execution.CURRENT.reset(token)
    gate = await joined_thread(regate)
    fix_id = None
    if gate.get('passed') is not True:
        clone, execution_key, fix_id, fixed_scope = await run_fix(conn, lease, controller, clone, gate, contract, image_id, final_sha, base_sha)
        # Never trust the child's green result for publication; recheck commits,
        # the original policy/scope and a fresh immutable snapshot after quiescence.
        async with leases.fenced_transaction(conn, lease):
            pass
        final_sha = review._sha('HEAD', clone)
        if not review._is_ancestor(trial['merge_sha'], final_sha, clone) or final_sha == trial['merge_sha']:
            raise publication.PublicationHeld('maintenance fix must add commits to the trial merge')
        if factory.quality_config(clone) != contract:
            raise publication.PublicationHeld('maintenance fix changed scope or quality policy')
        gate = await joined_thread(regate)
        if gate.get('passed') is not True:
            return {'outcome': 'regate_red', 'fix_execution_id': fix_id, 'gate': gate}
    request = {**approved, 'base_sha': base_sha, 'head_sha': final_sha, 'expected_remote_sha': expected}
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
    return {**result, 'outcome': 'updated', 'approval_request_sha256': leases.request_hash(approved),
            'fix_execution_id': fix_id, 'gate': gate}
