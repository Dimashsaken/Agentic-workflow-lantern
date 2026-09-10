"""V3 production split-effect algorithm, actual Postgres/process death, fake GitHub.

Provider GET/POST and Git push are explicit durable local-file simulations. No
external provider write, configured DB connection, approval or migration occurs.
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


async def connect(database):
    return await asyncpg.connect(host="127.0.0.1", port=55432, user="lantern", database=database,
        password=(ROOT / "tools/azure-runner/.venv/integration-db-password").read_text().strip(), timeout=10)


def request_for(scenario):
    return {"run_id": "feat-20260910-split-crash-" + scenario, "repo": "https://github.com/fixture/product",
            "base": "main", "work": "feat/proof", "branch": "feat/proof", "head_sha": "a" * 40,
            "version": 3, "repository_id": 123, "base_sha": "c" * 40, "expected_remote_sha": None}


async def make_child(conn, parent):
    execution_id = await conn.fetchval("INSERT INTO stage_executions(run_id,stage,input) VALUES($1,'03-coding.publish','{}') RETURNING id", parent.run_id)
    return await leases.acquire_execution(conn, parent, execution_id)


class Provider:
    def __init__(self, path, request, stop_after=None, lease=None):
        self.path, self.request, self.stop_after, self.lease = Path(path), request, stop_after, lease
        self.gets = 0

    def load(self):
        return json.loads(self.path.read_text())

    def write(self, state, action):
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as out:
            json.dump(state, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, self.path)
        if self.stop_after == action:
            print(json.dumps({"checkpoint": action, "execution": self.lease.execution_id, "child_fence": self.lease.fence, "parent_fence": self.lease.parent_fence, "owner": self.lease.owner}), flush=True)
            import time
            time.sleep(3600)  # Test controller is actually killed at this boundary.

    def api(self, method, path, data=None):
        state = self.load()
        if method == "POST":
            assert path == "/repos/fixture/product/pulls"
            state["pr"] = True
            state["pr_writes"] += 1
            self.write(state, "pr")
            return 201, self.pr(state)
        assert method == "GET"
        self.gets += 1
        if path == "/repos/fixture/product":
            return 200, {"id": 123, "full_name": "fixture/product"}
        if path.endswith("/git/ref/heads/main"):
            return 200, {"ref": "refs/heads/main", "object": {"type": "commit", "sha": self.request["base_sha"]}}
        if "/git/ref/" in path:
            return (200, {"ref": "refs/heads/feat/proof", "object": {"type": "commit", "sha": state["head"]}}) if state["head"] else (404, {})
        return 200, [self.pr(state)] if state["pr"] else []

    def pr(self, state):
        return {"number": 7, "state": "open", "merged_at": None, "html_url": "https://github.com/fixture/product/pull/7",
                "head": {"ref": "feat/proof", "sha": state["head"], "repo": {"id": 123, "full_name": "fixture/product"}},
                "base": {"ref": "main", "sha": self.request["base_sha"], "repo": {"id": 123, "full_name": "fixture/product"}}}

    def git(self, *args, cwd=None):
        state = self.load()
        state["head"] = self.request["head_sha"]
        state["branch_writes"] += 1
        self.write(state, "branch")
        return subprocess.CompletedProcess(args, 0)


async def invoke(conn, lease, provider, request):
    loop = asyncio.get_running_loop()
    key = f"publish-v3:{request['run_id']}:{request['head_sha']}"

    def wait(coro):
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=15)

    async def current():
        async with leases.fenced_transaction(conn, lease):
            pass

    def begin(action):
        return wait(leases.begin_effect(conn, lease, key + ":" + action, "publish_" + action,
                    {"publication_request": request, "action": action}, initial_result={"publication_request": request}))

    def complete(action, effect, external_ref, result):
        action_request = {"publication_request": request, "action": action}
        if effect.created:
            return wait(leases.confirm_effect(conn, lease, key + ":" + action, external_ref, result))
        return wait(leases.reconcile_effect(conn, lease, key + ":" + action, action_request, external_ref, result))

    return await asyncio.to_thread(github.publish_split, provider.api, provider.git, "simulated-remote", Path.cwd(), request,
                                  "disposable fixture", "not a real PR", check_current=lambda: wait(current()), begin_effect=begin, complete_effect=complete)


async def worker(database, scenario, path):
    request = request_for(scenario)
    conn = await connect(database)
    parent = await leases.acquire_run(conn, request["run_id"], "killed-" + scenario)
    lease = await make_child(conn, parent)
    await invoke(conn, lease, Provider(path, request, scenario, lease), request)


async def scenario(conn, database, name, directory):
    request = request_for(name)
    run_id = request["run_id"]
    key = f"publish-v3:{run_id}:{request['head_sha']}"
    await conn.execute("INSERT INTO runs(id,brief,pipeline_version,current_stage,created_by) VALUES($1,'disposable split-effect crash fixture','test','03-coding','integration-test')", run_id)
    path = Path(directory) / (name + ".json")
    path.write_text(json.dumps({"head": None, "pr": False, "branch_writes": 0, "pr_writes": 0}))
    process = await asyncio.create_subprocess_exec(sys.executable, __file__, "--worker", database, name, str(path), stdout=asyncio.subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        ready = json.loads(await asyncio.wait_for(process.stdout.readline(), 30))
        assert ready["checkpoint"] == name
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
    before = await conn.fetch("SELECT operation_key,status FROM execution_effects WHERE run_id=$1 ORDER BY operation_key", run_id)
    assert len(before) == (1 if name == "branch" else 2)
    assert before[-1]["status"] == "intended"
    await conn.execute("UPDATE runs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=$1", run_id)
    recovered = await leases.recover_expired(conn)
    assert any(r["run_id"] == run_id and r["status"] == "failed" for r in recovered)
    await conn.execute("UPDATE runs SET status='running' WHERE id=$1", run_id)  # Explicit disposable test-operator retry.
    parent = await leases.acquire_run(conn, run_id, "recovered-" + name)
    lease = await make_child(conn, parent)
    provider = Provider(path, request)
    result = await invoke(conn, lease, provider, request)
    assert result["pr_number"] == 7
    state = provider.load()
    assert state["branch_writes"] == state["pr_writes"] == 1
    await invoke(conn, lease, provider, request)
    assert provider.load() == state
    stale = leases.Lease(run_id, ready["owner"], ready["child_fence"], ready["execution"], ready["parent_fence"])
    try:
        await leases.begin_effect(conn, stale, key + ":stale", "publish_pr", {"publication_request": request, "action": "pr"})
    except leases.LeaseLost:
        pass
    else:
        raise AssertionError("old owner could initiate another provider action")
    after = await conn.fetch("SELECT operation_key,status FROM execution_effects WHERE run_id=$1 ORDER BY operation_key", run_id)
    assert len(after) == 2 and all(row["status"] == "confirmed" for row in after)
    await leases.release(conn, lease, "succeeded")
    await leases.release(conn, parent, "waiting_gate")
    return {"killed_after": name + " durable simulated provider write; before receipt", "effects_at_kill": [dict(r) for r in before], "effects_after_retry": [dict(r) for r in after], "provider_writes": state, "duplicate_replayed": False, "stale_owner_refused": True, "gets_during_recovery": provider.gets}


async def main():
    database = "lantern_split_proof_" + uuid4().hex[:12]
    admin = await connect("lantern_validation")
    conn = None
    created = False
    record = {"environment": "actual disposable PostgreSQL and two controller subprocess kills; GitHub/Git provider operations are durable local-file simulations", "actual_github": False, "database": database}
    try:
        before = await admin.fetchval("SELECT md5(coalesce(jsonb_agg(to_jsonb(a) ORDER BY id)::text,'')) FROM approvals a")
        await admin.execute('CREATE DATABASE "' + database + '"')
        created = True
        conn = await connect(database)
        await conn.execute((ROOT / "tools/azure-runner/schema.sql").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="lantern-split-provider-") as directory:
            record["scenarios"] = [await scenario(conn, database, name, directory) for name in ("branch", "pr")]
        assert await conn.fetchval("SELECT count(*) FROM approvals") == 0
        after = await admin.fetchval("SELECT md5(coalesce(jsonb_agg(to_jsonb(a) ORDER BY id)::text,'')) FROM approvals a")
        assert before == after
        record["validation_approvals_unchanged"] = True
        record["source_sha256"] = {name: hashlib.sha256((ROOT / "tools/azure-runner" / name).read_bytes()).hexdigest() for name in ("github_publication.py", "execution_leases.py", "pipeline.py")}
        record["passed"] = True
    finally:
        if conn:
            await conn.close()
        if created:
            await admin.execute('DROP DATABASE "' + database + '"')
        await admin.close()
    Path(__file__).with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    asyncio.run(worker(sys.argv[2], sys.argv[3], sys.argv[4]) if len(sys.argv) > 1 else main())
