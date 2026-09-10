"""Actual-image isolation controls on disposable synthetic files, never a fleet gate.

Run: python integration_isolated_tools.py --image lantern-sandbox:agentic-infrastructure
Prints JSON evidence; nonzero exit on any failed assertion. Requires local Docker.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import uuid

from isolated_tools import IsolatedToolWorker
import tool_execution


def file_race_probe(worker, product, authority):
    """Deterministically swap a symlink after the policy check, before real IO."""
    from tool_policy import StageAccess
    policy = StageAccess(authority, product, "feat-isolation", "coding", "03-coding",
                         "03-coding", product_write=True)
    token = tool_execution.CURRENT.set(worker)
    sentinel = authority / "controller-sentinel.txt"
    sentinel.write_text("synthetic host controller authority")
    try:
        safe = product / "race-safe.txt"
        safe.write_text("safe initial file")
        validated = policy.read("product/race-safe.txt")
        script = "import os; os.unlink('/work/product/race-safe.txt'); os.symlink(" + repr(
            sentinel.as_posix()) + ", '/work/product/race-safe.txt')"
        result = worker.run("python -I -c " + shlex.quote(script), 30)
        assert result.returncode == 0, result.stderr
        denied = []
        for operation in ("read", "write", "append"):
            try:
                tool_execution.file_io(operation, validated, content="forged" if operation != "read" else None)
            except OSError:
                denied.append(operation)
            else:
                raise AssertionError("post-policy symlink was followed: " + operation)
        assert sentinel.read_text() == "synthetic host controller authority"
        good = product / "nested" / "normal.txt"
        tool_execution.file_io("write", good, content="normal")
        tool_execution.file_io("append", good, content=" append")
        assert tool_execution.file_io("read", good) == "normal append"
        assert {item["name"] for item in tool_execution.file_io("list", product / "nested")} == {"normal.txt"}
        directory = product / "race-directory"
        directory.mkdir()
        checked_directory = policy.read("product/race-directory")
        result = worker.run("python -I -c " + shlex.quote("import os; os.rmdir('/work/product/race-directory'); "
            "os.symlink(" + repr(authority.as_posix()) + ", '/work/product/race-directory')"), 30)
        assert result.returncode == 0, result.stderr
        try:
            tool_execution.file_io("list", checked_directory)
        except OSError:
            denied.append("list")
        else:
            raise AssertionError("post-policy directory symlink was followed")
        return {"control": "deterministic symlink swap after StageAccess validation",
                "denied_operations": denied, "controller_sentinel_unchanged": True,
                "normal_read_write_append_list": True}
    finally:
        # Remove only the two synthetic symlinks through the worker namespace.
        worker.run("rm -f /work/product/race-safe.txt /work/product/race-directory", 30)
        tool_execution.CURRENT.reset(token)


def binary_git_probe(worker, product):
    token = tool_execution.CURRENT.set(worker)
    shadow = product / "json.py"
    shadow.write_text("raise RuntimeError('worker product shadowed trusted transport')\n")
    try:
        def git(*args, **kwargs):
            return tool_execution.run(["git", *args], cwd=product, capture_output=True, check=True, **kwargs)
        git("init", text=True)
        binary = bytes(range(256)) + b"\x00\r\n\xff"
        original = git("hash-object", "-w", "--stdin", input=binary).stdout.strip().decode()
        substitute = git("hash-object", "-w", "--stdin", input=b"replacement").stdout.strip().decode()
        git("replace", original, substitute, text=True)
        read = git("cat-file", "blob", original).stdout
        assert read == binary
        return {"binary_roundtrip_bytes": len(read), "sha256": hashlib.sha256(read).hexdigest(),
                "replacement_ref_ignored": True, "product_module_shadow_ignored": True,
                "safe_directory": "/work/product"}
    finally:
        shadow.unlink()
        tool_execution.CURRENT.reset(token)


async def browser_probe(worker, media):
    """Use the actual pinned Playwright MCP through the real SDK stdio client."""
    from agents.mcp import MCPServerStdio
    config = {"browser": {"contextOptions": {"recordVideo": {
        "dir": "/work/media", "size": {"width": 1280, "height": 720}},
        "viewport": {"width": 1280, "height": 720}}}}
    (media / "browser-config.json").write_text(json.dumps(config))
    command = worker.mcp_command(["playwright-mcp", "--headless", "--isolated",
        "--browser", "chromium", "--config", "/work/media/browser-config.json",
        "--output-dir", "/work/media"])
    async with MCPServerStdio(params={"command": command[0], "args": command[1:]},
                             client_session_timeout_seconds=45) as mcp:
        tools = await mcp.list_tools()
        names = [tool.name for tool in tools]
        assert "browser_navigate" in names and "browser_evaluate" in names
        fixture = "data:text/html,<html><title>Isolated worker proof</title><body>" + \
                  "<h1>Offline browser fixture</h1><button onclick=\"this.textContent='Verified'\">" + \
                  "Verify isolation</button></body></html>"
        navigation = await mcp.call_tool("browser_navigate", {"url": fixture})
        assert not navigation.is_error, str(navigation)
        action = await mcp.call_tool("browser_evaluate", {"function":
            "() => { document.querySelector('button').click(); return {title: document.title, "
            "button: document.querySelector('button').textContent}; }"})
        assert not action.is_error and "Verified" in str(action), str(action)
        # Give the renderer multiple frames before closing/flushing the recording.
        await asyncio.sleep(1)
        closed = await mcp.call_tool("browser_close", {})
        assert not closed.is_error, str(closed)
    videos = sorted(media.glob("*.webm"))
    assert len(videos) == 1, videos
    video = videos[0]
    decoded = json.loads(subprocess.check_output(["ffprobe", "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,codec_name,width,height",
        "-of", "json", str(video)], text=True))
    assert float(decoded["format"]["duration"]) > 0
    assert any(stream["codec_type"] == "video" for stream in decoded["streams"])
    return {"transport": "Agents SDK MCPServerStdio via worker.mcp_command",
            "fixture": "container-local data URL; no network", "tools_available": len(names),
            "button_result": "Verified", "video": str(video), "decoded": decoded,
            "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
            "capture_container_id": worker.container_id}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--browser", action="store_true", help="Requires Agents SDK and ffprobe")
    parser.add_argument("--media-output", type=Path, help="Keep recordings in a fresh directory")
    args = parser.parse_args()
    evidence = {"kind": "actual-docker-isolation-controls", "fleet_execution": False,
                "recorded_at": datetime.now(timezone.utc).isoformat(), "controls": {}}
    key = "isolation-integration-" + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="lantern-isolation-") as temporary:
        root = Path(temporary)
        product, media, authority = [root / name for name in ("product", "media", "authority")]
        if args.media_output:
            media = args.media_output.resolve()
        for path in (product, media, authority):
            path.mkdir(parents=True)
        sentinel = authority / "gate.json"
        sentinel.write_text("controller authority sentinel")
        (authority / "controller.env").write_text("SYNTHETIC_CONTROLLER_SECRET=not-a-real-secret")
        script = '''import json, os, pathlib, socket
p = pathlib.Path('/work/product/allowed.txt'); p.write_text('scoped work')
pathlib.Path('/work/media/capture.txt').write_text('scoped media')
blocked = {}
reads_blocked = {}
for name in ('/authority/gate.json', '/repo-src/AGENTS.md', '/var/run/docker.sock',
             '/work/run/gate.json', '/opt/lantern/controller.env', '/outside-write'):
    try:
        pathlib.Path(name).read_bytes()
        reads_blocked[name] = False
    except OSError:
        reads_blocked[name] = True
    try:
        pathlib.Path(name).write_text('forged')
        blocked[name] = False
    except OSError:
        blocked[name] = True
try:
    socket.create_connection(('1.1.1.1', 443), timeout=1).close()
    network_blocked = False
except OSError:
    network_blocked = True
env_names = set(os.environ)
secrets_absent = not (env_names & {'AZURE_OPENAI_API_KEY','OPENAI_API_KEY',
                                 'LANTERN_DATABASE_URL','DATABASE_URL','AWS_SECRET_ACCESS_KEY'})
assert all(blocked.values()) and all(reads_blocked.values()) and network_blocked and secrets_absent
assert os.getuid() == 1000
print(json.dumps({'writes_blocked': blocked, 'reads_blocked': reads_blocked, 'egress_blocked': network_blocked,
                  'controller_credentials_absent': secrets_absent, 'uid': os.getuid()}))
'''
        worker = IsolatedToolWorker(product, media, key, args.image, protected_roots=[authority])
        with worker:
            evidence["image_id"] = worker.image_id
            inspect = json.loads(subprocess.check_output(["docker", "inspect", worker.container_id]))[0]
            mounts = inspect["Mounts"]
            assert len(mounts) == 2
            assert {item["Destination"] for item in mounts} == {"/work/product", "/work/media"}
            assert inspect["HostConfig"]["NetworkMode"] == "none"
            evidence["controls"]["mounts"] = [{"destination": item["Destination"], "rw": item["RW"]}
                                                for item in mounts]
            result = worker.run("python -c " + shlex.quote(script), 30)
            assert result.returncode == 0, result.stderr
            evidence["controls"]["shell"] = json.loads(result.stdout)
            result = subprocess.run(worker.mcp_command(["python", "-c", script]),
                                    capture_output=True, text=True, timeout=30, check=True)
            evidence["controls"]["mcp_stdio_command"] = json.loads(result.stdout)
            assert sentinel.read_text() == "controller authority sentinel"
            assert (product / "allowed.txt").read_text() == "scoped work"
            evidence["controls"]["normal_product_and_media_writes"] = True
            evidence["controls"]["binary_git_routing"] = binary_git_probe(worker, product)
            evidence["controls"]["file_policy_race"] = file_race_probe(worker, product, authority)
            if args.browser:
                evidence["controls"]["browser_protocol_recording"] = asyncio.run(browser_probe(worker, media))
            try:
                worker.run("(sleep 3; echo escaped > /work/product/late.txt) & wait", 0.5)
            except subprocess.TimeoutExpired:
                evidence["controls"]["timeout_raised"] = True
            else:
                raise AssertionError("Expected tool timeout")
            worker.run("(sleep 3; echo escaped > /work/product/background.txt) & exit 0", 10)
            time.sleep(3.5)
            assert not (product / "late.txt").exists()
            assert not (product / "background.txt").exists()
            evidence["controls"]["timeout_and_success_background_children_reaped"] = True
        with IsolatedToolWorker(product, media, key, args.image, writable_product=False) as readonly:
            result = readonly.run("echo forbidden > /work/product/forbidden.txt", 10)
            assert result.returncode != 0 and not (product / "forbidden.txt").exists()
            evidence["controls"]["read_only_product"] = True
        remaining = subprocess.check_output(["docker", "ps", "-aq", "--filter",
            "label=lantern.execution-key=" + hashlib.sha256(key.encode()).hexdigest()], text=True)
        assert not remaining.strip(), remaining
        evidence["controls"]["all_execution_containers_removed"] = True
    evidence["source_sha256"] = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                 for name in ("isolated_tools.py", "integration_isolated_tools.py", "tool_execution.py")}
    evidence["limitations"] = ["Synthetic sentinel credentials only; no fleet stage or approval",
        "Browser recording proves the offline synthetic fixture only, not deployed Mission Control QA"
            if args.browser else "MCP stdio executable only; protocol browser probe not requested",
        "External browser egress intentionally unavailable; allowlisted proxy remains unsupported",
        "Controller hard death needs dispatcher reconciliation of execution-labelled containers"]
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
