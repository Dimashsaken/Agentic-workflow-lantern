"""Actual disposable Postgres + process-death control; GitHub is simulated.

Never connects to the configured database or sends a GitHub mutation. The provider
fixture is an fsynced local file. This is not exactly-once GitHub proof.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/azure-runner"))
import asyncpg
import execution_leases as leases
import github_publication as github

RUN = "feat-20260910-publication-crash-proof"
REQUEST = {"run_id": RUN, "repo": "https://github.com/fixture/product", "base": "main", "work": "feat/proof", "branch": "feat/proof", "head_sha": "a" * 40, "version": 2, "repository_id": 123, "base_sha": "c" * 40, "expected_remote_sha": None}
KEY = "publish-v2:" + RUN + ":" + REQUEST["head_sha"]


async def connect(database):
    return await asyncpg.connect(host="127.0.0.1", port=55432, user="lantern", database=database,
        password=(ROOT / "tools/azure-runner/.venv/integration-db-password").read_text().strip(), timeout=10)


async def child(conn, parent):
    execution = await conn.fetchval("INSERT INTO stage_executions(run_id,stage,input) VALUES($1,'03-coding.publish','{}') RETURNING id", RUN)
    return await leases.acquire_execution(conn, parent, execution)


async def worker(database, provider):
    conn = await connect(database)
    parent = await leases.acquire_run(conn, RUN, "controller-before-kill")
    execution = await child(conn, parent)
    await leases.begin_effect(conn, execution, KEY, "publish_branch", REQUEST,
                              initial_result={"publication_request": REQUEST})
    with Path(provider).open("x", encoding="utf-8") as out:
        json.dump({"head": REQUEST["head_sha"], "writes": 1}, out)
        out.flush()
        os.fsync(out.fileno())
    print(json.dumps({"parent_fence": parent.fence, "child_fence": execution.fence, "execution": execution.execution_id}), flush=True)
    await asyncio.sleep(3600)


def provider_api(path, calls):
    def api(method, url, data=None):
        calls.append(method)
        assert method == "GET", "Reconciliation attempted a provider mutation"
        value = json.loads(path.read_text())
        if url == "/repos/fixture/product":
            return 200, {"id": 123, "full_name": "fixture/product"}
        if url.endswith("/git/ref/heads/main"):
            return 200, {"ref": "refs/heads/main", "object": {"type": "commit", "sha": REQUEST["base_sha"]}}
        if "/git/ref/" in url:
            return 200, {"ref": "refs/heads/feat/proof", "object": {"type": "commit", "sha": value["head"]}}
        return 200, [{"number": 7, "state": "open", "html_url": "https://github.com/fixture/product/pull/7", "head": {"ref": "feat/proof", "sha": value["head"], "repo": {"id": 123, "full_name": "fixture/product"}}, "base": {"ref": "main", "sha": REQUEST["base_sha"], "repo": {"id": 123, "full_name": "fixture/product"}}}]
    return api


async def main():
    database = "lantern_publication_proof_" + uuid4().hex[:12]
    admin = await connect("lantern_validation")
    conn = None
    created = False
    record = {"environment": "actual disposable PostgreSQL16 at loopback55432; actual controller subprocess kill; simulated GitHub GET responses from durable local file", "live_github": False, "database": database, "controls": []}
    try:
        before = await admin.fetchval("SELECT md5(coalesce(jsonb_agg(to_jsonb(a) ORDER BY id)::text,'')) FROM approvals a")
        await admin.execute('CREATE DATABASE "' + database + '"')
        created = True
        conn = await connect(database)
        await conn.execute((ROOT / "tools/azure-runner/schema.sql").read_text(encoding="utf-8"))
        await conn.execute("INSERT INTO runs(id,brief,pipeline_version,current_stage,created_by) VALUES($1,'disposable publication crash fixture','test','03-coding','integration-test')", RUN)
        with tempfile.TemporaryDirectory(prefix="lantern-publication-proof-") as directory:
            provider = Path(directory) / "provider.json"
            process = await asyncio.create_subprocess_exec(sys.executable, __file__, "--worker", database, str(provider), stdout=asyncio.subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                ready = json.loads(await asyncio.wait_for(process.stdout.readline(), 25))
            finally:
                if process.returncode is None:
                    process.kill()
                await process.wait()
            original_bytes = provider.read_bytes()
            await conn.execute("UPDATE runs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=$1", RUN)
            recovered = await leases.recover_expired(conn)
            assert recovered[0]["status"] == "failed" and recovered[0]["ambiguous_effects"]
            assert await conn.fetchval("SELECT status FROM execution_effects WHERE operation_key=$1", KEY) == "uncertain"
            record["controls"].append("actual killed controller left effect uncertain; run held; no gate created")
            # Explicit test-operator retry on disposable data, not a fleet decision.
            await conn.execute("UPDATE runs SET status='running' WHERE id=$1", RUN)
            parent = await leases.acquire_run(conn, RUN, "controller-after-kill")
            execution = await child(conn, parent)
            duplicate = await leases.begin_effect(conn, execution, KEY, "publish_branch", REQUEST)
            assert not duplicate.created and duplicate.status == "uncertain"
            assert duplicate.result["publication_request"] == REQUEST
            calls = []
            result = github.reconcile(provider_api(provider, calls), REQUEST)
            await leases.reconcile_effect(conn, execution, KEY, REQUEST, result["pr_url"], result)
            confirmed = await leases.begin_effect(conn, execution, KEY, "publish_branch", REQUEST)
            github.reconcile(provider_api(provider, calls), REQUEST, confirmed.result)
            assert confirmed.status == "confirmed" and not confirmed.created
            assert provider.read_bytes() == original_bytes and set(calls) == {"GET"}
            record["controls"].append("uncertain then confirmed duplicates re-observed; one durable simulated provider effect; zero replay writes")
            try:
                await leases.begin_effect(conn, execution, KEY, "publish_branch", dict(REQUEST, base="other"))
            except leases.EffectConflict:
                record["controls"].append("changed destination rejected by persisted request hash")
            else:
                raise AssertionError("changed destination accepted")
            stale = leases.Lease(RUN, "controller-before-kill", ready["child_fence"], ready["execution"], ready["parent_fence"])
            try:
                await leases.confirm_effect(conn, stale, KEY, result["pr_url"], result)
            except leases.LeaseLost:
                record["controls"].append("stale pre-kill owner cannot confirm effects")
            else:
                raise AssertionError("stale confirmation accepted")
            provider.write_text(json.dumps({"head": "b" * 40, "writes": 1}))
            try:
                github.reconcile(provider_api(provider, calls), REQUEST, confirmed.result)
            except github.PublicationHeld:
                record["controls"].append("moved provider revision invalidates confirmed receipt reuse")
            else:
                raise AssertionError("stale revision accepted")
            record["provider_get_calls"] = len(calls)
        after = await admin.fetchval("SELECT md5(coalesce(jsonb_agg(to_jsonb(a) ORDER BY id)::text,'')) FROM approvals a")
        assert before == after
        assert await conn.fetchval("SELECT count(*) FROM approvals") == 0
        record["validation_approvals_unchanged"] = True
        record["controls"].append("existing validation approval rows unchanged; fixture created no approvals")
        record["source_sha256"] = {name: hashlib.sha256((ROOT / "tools/azure-runner" / name).read_bytes()).hexdigest() for name in ("github_publication.py", "execution_leases.py", "pipeline.py")}
        record["passed"] = True
    finally:
        if conn:
            await conn.close()
        if created:
            await admin.execute('DROP DATABASE "' + database + '"')
        await admin.close()
    Path(__file__).with_name("publication-postgres-proof.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    asyncio.run(worker(sys.argv[2], sys.argv[3]) if len(sys.argv) > 1 else main())
