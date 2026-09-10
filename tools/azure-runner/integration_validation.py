"""Opt-in live stage validation on a disposable database and isolated checkout.

Requires LANTERN_VALIDATION_DATABASE_URL (never defaults to the fleet database).
Azure credentials are read from the caller's environment or local .env. No gate
is approved: the sequence ends at the real story_signoff request. Results are
labelled integration evidence, not approval of the infrastructure engineering run.
"""
import argparse
import asyncio
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


async def validate(args):
    source = Path(__file__).resolve().parents[2]
    load_dotenv(source / "tools/azure-runner/.env")
    database = os.environ.get("LANTERN_VALIDATION_DATABASE_URL")
    if not database:
        raise SystemExit("Set LANTERN_VALIDATION_DATABASE_URL to a disposable database")
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    harness = workspace / "harness"
    harness.mkdir()
    # Copy only tracked source, including the working changes under review. Never
    # copy .env, unrelated untracked files, or another run's artifacts.
    source_hashes = {}
    for rel in git(source, "ls-files").splitlines():
        if rel.startswith("workflow/runs/"):
            continue
        p = source / rel
        if not p.is_file():
            continue
        target = harness / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
        source_hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    product = workspace / "product"
    product.mkdir()
    (product / "README.md").write_text("# Greeting library\nA tiny Python greeting function.\n")
    (product / "greeting.py").write_text('def greet(name):\n    return "Hello, " + name\n')
    git(product, "init", "-b", "main")
    git(product, "add", ".")
    git(product, "-c", "user.name=validation", "-c", "user.email=validation@localhost",
        "-c", "commit.gpgsign=false", "commit", "-m", "Disposable validation product")
    os.environ["LANTERN_DATABASE_URL"] = database
    os.environ["LANTERN_EXECUTOR"] = args.executor
    os.environ["LANTERN_PRODUCT_MIRROR_DIR"] = str(workspace / "mirrors")
    os.environ["LANTERN_ARTIFACT_BUCKET"] = ""
    os.environ["LANTERN_MAX_TURNS"] = str(args.max_turns)
    os.environ["LANTERN_EFFORT_REASONING"] = "low"
    os.environ["LANTERN_SANDBOX_IMAGE"] = args.image
    sys.path.insert(0, str(harness / "tools/azure-runner"))
    p = importlib.import_module("pipeline")
    o = importlib.import_module("orchestrator")
    # Import origin is itself a control: never point a test run at the caller's
    # real runboard or rendered memory.
    assert p.REPO == harness and o.REPO == harness
    conn = await p.connect()
    if not (await conn.fetchval("SELECT current_database()")).startswith("lantern_validation"):
        await conn.close()
        raise RuntimeError("Refusing a database outside the lantern_validation name prefix")
    if await conn.fetchval("SELECT to_regclass('public.runs')"):
        foreign = await conn.fetchval("SELECT count(*) FROM runs WHERE id NOT LIKE 'feat-20260910-live-%'")
        if foreign:
            await conn.close()
            raise RuntimeError("Refusing a database containing non-validation runs")
    await conn.execute((harness / "tools/azure-runner/schema.sql").read_text())
    o.set_default_openai_client(o.azure_v1_client())
    o.set_default_openai_api(os.environ.get("LANTERN_OPENAI_API", "responses"))
    o.set_tracing_disabled(True)
    run_id = f"feat-20260910-live-{args.executor}-{args.tag}"
    brief = workspace / "brief.md"
    brief.write_text("# Greeting fallback\n\nAdd a default greeting for an empty name. "
                     "Keep this change tiny: greet('') returns 'Hello, friend', "
                     "and all nonempty names retain current behavior.\n")
    record = {"kind": "live_azure_postgres_stage_validation", "executor": args.executor,
              "engineering_run_approval": False, "started_at": datetime.now(timezone.utc).isoformat(),
              "source_head": git(source, "rev-parse", "HEAD"), "source_sha256": source_hashes,
              "product_revision": git(product, "rev-parse", "HEAD"), "run_id": run_id}
    record["execution_leases"] = os.environ.get("LANTERN_EXECUTION_LEASES") == "1"
    record["isolated_tools"] = os.environ.get("LANTERN_ISOLATED_TOOLS") == "1"
    if args.executor == "docker" or record["isolated_tools"]:
        record["image_id"] = subprocess.check_output(
            ["docker", "image", "inspect", args.image, "--format", "{{.Id}}"], text=True).strip()
    async def kill_control():
        name = f"lantern-{run_id}-00-story-scout-1"
        for _ in range(240):
            listing = await asyncio.to_thread(subprocess.check_output,
                ["docker", "ps", "--format", "{{.Names}}"], text=True)
            if name in listing.splitlines():
                await asyncio.sleep(args.kill_after_seconds)
                await asyncio.to_thread(subprocess.check_call, ["docker", "kill", name],
                                        stdout=subprocess.DEVNULL)
                record["kill_delivered"] = True
                return
            await asyncio.sleep(.25)
        raise RuntimeError("Kill-control did not observe the expected test container")
    killer = None
    try:
        await p.cmd_run(str(brief), run_id, "integration-validation", False,
                        product_repo=str(product), product_branch="main")
        if args.kill_after_seconds:
            if args.executor != "docker":
                raise ValueError("Kill-control requires Docker")
            killer = asyncio.create_task(kill_control())
        for stage in ("00-story.scout", "00-story.write"):
            claimed = await p.claim_run(conn, "ec2")
            if claimed != run_id:
                raise RuntimeError("Disposable database claimed unexpected run; refusing execution")
            await p.step_run(conn, run_id)
            row = await conn.fetchrow("SELECT status, current_stage FROM runs WHERE id=$1", run_id)
            if row["status"] == "failed":
                break
        record["run"] = dict(await conn.fetchrow("SELECT status,current_stage FROM runs WHERE id=$1", run_id))
        record["executions"] = [dict(r) for r in await conn.fetch(
            "SELECT id,stage,attempt,status,idempotency_key,error_class,model,requests,input_tokens,output_tokens,total_tokens FROM stage_executions WHERE run_id=$1 ORDER BY id", run_id)]
        record["gates"] = [dict(r) for r in await conn.fetch(
            "SELECT gate,status,decided_by FROM approvals WHERE run_id=$1", run_id)]
        record["memory_count"] = await conn.fetchval("SELECT count(*) FROM role_memory WHERE run_id=$1", run_id)
        record["traces"] = [
            {"execution_key": value.get("execution_key"), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in (harness / "workflow/runs" / run_id / "00-story/trace").glob("*.json")
            if isinstance((value := json.loads(path.read_text(encoding="utf-8"))), dict)]
        record["passed"] = (record["run"]["status"] == "waiting_gate" and
            record["gates"] == [{"gate": "story_signoff", "status": "pending", "decided_by": None}] and
            len(record["executions"]) == 2 and all(r["status"] == "succeeded" for r in record["executions"]))
        if args.expect_turn_limit:
            record["expected_failure"] = "turn_limit"
            traces = list((harness / "workflow/runs" / run_id / "00-story/trace").glob("*.json"))
            trace = json.loads(traces[0].read_text()) if traces else {}
            record["failure_trace"] = {k: trace.get(k) for k in ("usage", "usage_incomplete", "failure")}
            record["passed"] = (record["run"]["status"] == "failed" and not record["gates"] and
                len(record["executions"]) == 1 and record["executions"][0]["status"] == "failed" and
                record["executions"][0]["total_tokens"] is not None and bool(trace.get("failure")) and
                "MaxTurnsExceeded" in json.dumps(trace.get("failure")))
        if args.kill_after_seconds:
            record["expected_failure"] = "container_killed"
            record["passed"] = (record.get("kill_delivered") is True and
                record["run"]["status"] == "failed" and not record["gates"] and
                len(record["executions"]) == 1 and record["executions"][0]["status"] == "failed")
            record["usage_note"] = "Null counters remain unknown after hard kill; no zero-usage inference"
    finally:
        if killer is not None:
            killer.cancel()
            await asyncio.gather(killer, return_exceptions=True)
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        record["artifact_directory"] = str(harness / "workflow/runs" / run_id)
        Path(args.output).write_text(json.dumps(record, indent=2) + "\n")
        await conn.close()
    print(json.dumps({k:v for k,v in record.items() if k != "source_sha256"}, indent=2))
    return record["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executor", choices=("inprocess", "docker"), required=True)
    parser.add_argument("--workspace", required=True, help="New disposable workspace path")
    parser.add_argument("--output", required=True)
    parser.add_argument("--tag", default="1")
    parser.add_argument("--image", default="lantern-sandbox:agentic-infrastructure")
    parser.add_argument("--max-turns", type=int, default=45)
    parser.add_argument("--expect-turn-limit", action="store_true")
    parser.add_argument("--kill-after-seconds", type=float, default=0)
    raise SystemExit(0 if asyncio.run(validate(parser.parse_args())) else 1)
