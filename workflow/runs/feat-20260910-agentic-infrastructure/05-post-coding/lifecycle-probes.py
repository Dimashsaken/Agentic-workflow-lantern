"""Independent local lifecycle probes; no Azure, database, or fleet execution."""
import asyncio
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/azure-runner"))
import pipeline as p
import orchestrator as o
import factory as f
from agents.mcp import MCPServerStdio


async def mcp_cleanup(parallel):
    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "server.py"
        script.write_text("import asyncio\nfrom mcp.server import Server\nfrom mcp.server.stdio import stdio_server\n"
                          "m = Server('local-probe')\nasync def main():\n"
                          "    async with stdio_server() as streams:\n"
                          "        await m.run(*streams, m.create_initialization_options())\n"
                          "asyncio.run(main())\n", encoding="utf-8")
        server = MCPServerStdio(params={"command": sys.executable, "args": [str(script)]})
        await server.connect()
        errors = []
        close = server.exit_stack.aclose

        async def observed_close():
            try:
                await close()
            except BaseException as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                raise

        server.exit_stack.aclose = observed_close
        if parallel:
            await asyncio.gather(server.cleanup())
        else:
            await server.cleanup()
        return errors


async def setup_failure():
    conn = AsyncMock()
    conn.fetchval.side_effect = [1, 42]
    with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
        replacements = {
            "render_role_memory": AsyncMock(),
            "product_target": AsyncMock(return_value=("local-disposable-product", "main")),
            "product_work_branch": AsyncMock(return_value="feat/probe"),
            "product_checkout": lambda *a: Path(td),
            "prepare_coding_checkout": lambda *a: "a" * 40,
            "db_urls": lambda: ("unused", "unused"),
            "check_stage_inputs": lambda *a: "injected missing approved plan",
        }
        stack.enter_context(patch.dict(os.environ))
        stack.enter_context(patch.object(f, "REPO", Path(td)))
        stack.enter_context(patch.object(p, "record_usage", AsyncMock()))
        for name, value in replacements.items():
            stack.enter_context(patch.object(p, name, value))
        stack.enter_context(patch.object(p.SQLAlchemySession, "from_url", return_value=None))
        try:
            await p.run_agent_stage(conn, "local-probe", "03-coding", "local")
        except RuntimeError as exc:
            return {"error": str(exc), "writable_env_after_failure": os.environ.get("LANTERN_PRODUCT_WRITABLE"),
                    "branch_env_after_failure": os.environ.get("LANTERN_CODING_BRANCH")}
        raise AssertionError("setup probe did not fail")


async def container_setup_failure():
    conn = AsyncMock()
    server = AsyncMock()
    server.connect.side_effect = RuntimeError("injected MCP connect failure")
    with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
        stack.enter_context(patch.object(f, "REPO", Path(td)))
        for name, value in {
            "db_connect": AsyncMock(return_value=conn), "azure_v1_client": lambda: None,
            "set_default_openai_client": lambda *a: None, "render_role_memory": AsyncMock(),
            "playwright_mcp_server": lambda *a: server,
        }.items():
            stack.enter_context(patch.object(o, name, value))
        stack.enter_context(patch.object(sys, "argv", ["orchestrator.py", "local-probe", "04-qa-dev"]))
        try:
            await o.main()
        except RuntimeError as exc:
            return {"error": str(exc), "database_close_calls": conn.close.await_count,
                    "mcp_cleanup_calls": server.cleanup.await_count}
        raise AssertionError("container setup probe did not fail")


if __name__ == "__main__":
    # Independent event loops prevent the faulty cleanup's lingering cancel scope
    # from contaminating the sequential control or later lifecycle probes.
    results = {"sdk_sequential_cleanup_errors": asyncio.run(mcp_cleanup(False)),
               "sdk_parallel_cleanup_errors": asyncio.run(mcp_cleanup(True)),
               "inprocess_setup_failure": asyncio.run(setup_failure()),
               "container_setup_failure": asyncio.run(container_setup_failure())}
    print(json.dumps(results, indent=2))
