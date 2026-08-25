"""Lantern stage orchestrator — runs ONE pipeline stage with an Azure OpenAI brain.

    python orchestrator.py <run-id> <stage-dir>
    python orchestrator.py feat-20260824-bulk-export 04-qa-dev

SCAFFOLD: reviewed, not yet exercised on EC2. Deterministic pipeline control lives
here; the model only has autonomy inside a stage. After the run, the three AGENTS.md
postconditions are enforced mechanically — a stage that skipped one fails loudly.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import (Agent, Runner, function_tool, set_default_openai_api,
                    set_default_openai_client, set_tracing_disabled)
from agents.mcp import MCPServerStdio

REPO = Path(__file__).resolve().parents[2]
load_dotenv(Path(__file__).parent / ".env")


def azure_v1_client() -> AsyncOpenAI:
    """Client for Azure OpenAI's v1 API surface (endpoint ends in /openai/v1)."""
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    if not endpoint.endswith("/openai/v1"):
        endpoint += "/openai/v1"
    return AsyncOpenAI(base_url=endpoint, api_key=os.environ["AZURE_OPENAI_API_KEY"])

ROLE_FOR_STAGE = {
    "01-ui-ux": "ui-ux",
    "02-pre-coding": "pre-coding",
    "04-qa-dev": "qa-dev",
    "05-post-coding": "post-coding",
    "06-security": "security",
    "07-qa-staging": "qa-staging",
    # debug lifecycle stages all map to the debug role:
    "01-triage": "debug", "02-repro": "debug", "03-root-cause": "debug",
    "04-fix": "debug", "05-regression": "qa-dev", "06-postmortem": "debug",
}

# Roles that drive a browser get the Playwright MCP server.
BROWSER_ROLES = {"ui-ux", "qa-dev", "qa-staging", "debug"}

# Deployment routing: strong model for judgement-heavy roles, fast one for execution.
FAST_ROLES = {"qa-dev", "qa-staging"}


def model_for(role: str) -> str:
    var = "LANTERN_MODEL_FAST" if role in FAST_ROLES else "LANTERN_MODEL_REASONING"
    deployment = os.environ.get(var)
    if not deployment:
        sys.exit(f"Missing env var {var} (Azure deployment name, e.g. sol/terra)")
    return deployment


def build_instructions(role: str, run_id: str, stage: str) -> str:
    parts = [
        (REPO / "AGENTS.md").read_text(encoding="utf-8"),
        f"\n\n# Your assignment\nYou are the **{role}** agent. Run ID: `{run_id}`. "
        f"Stage directory: `workflow/runs/{run_id}/{stage}/`.\n"
        "Follow your charter and skills exactly. Before finishing you MUST: "
        "(1) write the stage report, (2) append learnings to your memory.md, "
        "(3) update workflow/RUNBOARD.md. These are verified mechanically.",
    ]
    for name in ("charter.md", "skills.md", "memory.md"):
        f = REPO / "agents" / role / name
        parts.append(f"\n\n# {role}/{name}\n" + f.read_text(encoding="utf-8"))
    return "".join(parts)


def _safe(rel: str) -> Path:
    p = (REPO / rel).resolve()
    if not p.is_relative_to(REPO):
        raise ValueError(f"path escapes repo: {rel}")
    return p


@function_tool
def read_file(path: str) -> str:
    """Read a file. Path is relative to the Lantern repo root."""
    return _safe(path).read_text(encoding="utf-8")


@function_tool
def write_file(path: str, content: str) -> str:
    """Create or overwrite a file. Path is relative to the Lantern repo root."""
    p = _safe(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {path}"


@function_tool
def append_file(path: str, content: str) -> str:
    """Append to a file (memory entries, runboard rows). Path relative to repo root."""
    with _safe(path).open("a", encoding="utf-8") as f:
        f.write(content)
    return f"appended to {path}"


@function_tool
def list_dir(path: str) -> str:
    """List a directory. Path is relative to the Lantern repo root."""
    return "\n".join(sorted(x.name + ("/" if x.is_dir() else "") for x in _safe(path).iterdir()))


def check_postconditions(role: str, run_id: str, stage: str, memory_before: str) -> list[str]:
    missing = []
    if not (REPO / "workflow/runs" / run_id / stage / "report.md").exists():
        missing.append(f"stage report workflow/runs/{run_id}/{stage}/report.md not written")
    memory_now = (REPO / "agents" / role / "memory.md").read_text(encoding="utf-8")
    if memory_now == memory_before:
        missing.append(f"agents/{role}/memory.md not appended (an explicit 'nothing learned' note also counts)")
    if run_id not in (REPO / "workflow/RUNBOARD.md").read_text(encoding="utf-8"):
        missing.append(f"workflow/RUNBOARD.md has no row for {run_id}")
    return missing


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("stage")
    args = ap.parse_args()

    role = ROLE_FOR_STAGE.get(args.stage) or sys.exit(f"unknown stage: {args.stage}")

    set_default_openai_client(azure_v1_client())
    # The v1 surface supports the Responses API; flip here if a deployment lacks it.
    set_default_openai_api("chat_completions")
    set_tracing_disabled(True)  # no OpenAI-platform key on the Azure credential set

    memory_before = (REPO / "agents" / role / "memory.md").read_text(encoding="utf-8")

    mcp_servers = []
    if role in BROWSER_ROLES:
        mcp_servers.append(MCPServerStdio(
            params={"command": "npx", "args": ["-y", "@playwright/mcp@latest"]},
            name="playwright",
        ))

    for s in mcp_servers:
        await s.connect()
    try:
        agent = Agent(
            name=role,
            model=model_for(role),
            instructions=build_instructions(role, args.run_id, args.stage),
            tools=[read_file, write_file, append_file, list_dir],
            mcp_servers=mcp_servers,
        )
        result = await Runner.run(
            agent,
            input=f"Begin your {args.stage} session for run {args.run_id}. "
                  f"Orient per AGENTS.md, do the work, satisfy all three postconditions.",
            max_turns=120,
        )
        print(result.final_output)
    finally:
        for s in mcp_servers:
            await s.cleanup()

    missing = check_postconditions(role, args.run_id, args.stage, memory_before)
    if missing:
        print("POSTCONDITIONS FAILED:\n- " + "\n- ".join(missing), file=sys.stderr)
        sys.exit(1)
    print("postconditions ok")


if __name__ == "__main__":
    asyncio.run(main())
