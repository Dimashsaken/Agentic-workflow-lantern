"""Credential-free Docker workers for untrusted product commands and MCP servers.

The SDK/controller remains on the host. Only a disposable product checkout and
this execution's media directory enter a worker. This deliberately supports
offline tools only; external browser targets require a separately reviewed proxy.
Docker and the administrator-supplied image remain trusted infrastructure.
"""

from __future__ import annotations

from collections import deque
from contextvars import ContextVar
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import uuid

from execution_retention import worker_mount


CURRENT_CANCELLATION = ContextVar('lantern_worker_cancellation', default=None)


class WorkerCancellation:
    """Controller lifecycle registry shared with copied to_thread contexts."""
    def __init__(self):
        self.cancelled = threading.Event()
        self.workers = []
        self.lock = threading.RLock()

    def register(self, worker):
        with self.lock:
            if self.cancelled.is_set():
                raise IsolationError('execution was cancelled before worker allocation')
            self.workers.append(worker)

    def stop(self):
        with self.lock:
            self.cancelled.set()
            workers = tuple(self.workers)
        errors = []
        for worker in workers:
            try:
                worker.stop()
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise IsolationError('cancelled execution has unreaped workers') from errors[0]


class IsolationError(RuntimeError):
    """A worker could not establish or preserve its declared boundary."""


def cleanup_execution(execution_key: str) -> list[str]:
    """Reap only workers labelled for one fenced, interrupted execution.

    The dispatcher must fence/stop its old controller before calling this. This
    reconciles containers already created; it cannot stop future dispatcher work.
    Both labels and full IDs are checked again before any removal.
    """
    if not isinstance(execution_key, str) or not execution_key:
        raise ValueError("Cleanup requires an exact execution key")
    digest = hashlib.sha256(execution_key.encode()).hexdigest()
    result = subprocess.run(["docker", "ps", "-aq", "--no-trunc", "--filter",
        "label=lantern.tool-worker=true", "--filter", "label=lantern.execution-key=" + digest],
        capture_output=True, text=True, timeout=30, check=True)
    candidates = result.stdout.split()
    if any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in candidates):
        raise IsolationError("Cleanup received an invalid Docker container ID")
    verified = []
    for container_id in candidates:
        result = subprocess.run(["docker", "inspect", container_id], capture_output=True,
                                text=True, timeout=30)
        if result.returncode and "No such" in result.stderr:
            continue  # Another cleanup already completed this exact container.
        if result.returncode:
            raise IsolationError("Could not verify an interrupted worker's identity")
        records = json.loads(result.stdout)
        if len(records) != 1 or records[0].get("Id") != container_id:
            raise IsolationError("Interrupted worker identity changed")
        labels = records[0].get("Config", {}).get("Labels", {}) or {}
        if labels.get("lantern.tool-worker") != "true" or labels.get("lantern.execution-key") != digest:
            raise IsolationError("Refusing cleanup outside the exact execution labels")
        verified.append(container_id)
    for container_id in verified:
        result = subprocess.run(["docker", "rm", "--force", container_id], capture_output=True,
                                text=True, timeout=30)
        if result.returncode and "No such container" not in result.stderr:
            raise IsolationError("Interrupted worker could not be removed")
    return verified


_IMAGE_ENV = frozenset({"PATH", "HOME", "DEBIAN_FRONTEND", "PIP_ROOT_USER_ACTION",
                        "PLAYWRIGHT_BROWSERS_PATH", "LANTERN_PLAYWRIGHT_MCP",
                        "LANTERN_EXPORT_DIR"})
_TARGET_ENV = frozenset({"QA_USER", "QA_PASS"})
_ENV = {"HOME": "/home/worker", "TMPDIR": "/tmp", "LANG": "C.UTF-8",
        "PATH": "/opt/lantern/venv/bin:/usr/local/bin:/usr/bin:/bin",
        "PLAYWRIGHT_BROWSERS_PATH": "/ms-playwright",
        "LANTERN_PYTHON": "/opt/lantern/venv/bin/python",
        "LANTERN_EXPORT_DIR": "/work/media"}


def _bounded_run(argv: list[str], timeout_s: float, limit: int = 128_000):
    """Drain both pipes without allowing tool output to exhaust controller RAM."""
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    tails = [deque(), deque()]

    def drain(stream, tail):
        size = 0
        try:
            while chunk := stream.read(8192):
                tail.append(chunk)
                size += len(chunk)
                while len(tail) > 1 and size - len(tail[0]) >= limit:
                    size -= len(tail.popleft())
        finally:
            stream.close()

    threads = [threading.Thread(target=drain, args=(stream, tail), daemon=True)
               for stream, tail in zip((process.stdout, process.stderr), tails)]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()  # Caller force-removes the container in its finally block.
        process.wait(timeout=10)
    except BaseException:
        process.kill()
        process.wait(timeout=10)
        raise
    finally:
        for thread in threads:
            thread.join(timeout=10)
    stdout, stderr = (b"".join(tail)[-limit:].decode("utf-8", errors="replace")
                      for tail in tails)
    if timed_out:
        raise subprocess.TimeoutExpired(argv, timeout_s, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


class IsolatedToolWorker:
    """Execution-scoped MCP worker plus fresh, fully reaped shell containers.

    Roots must already exist and be private to the execution. The caller owns
    credential-free checkout preparation and authoritative output collection.
    Never point output_root at a stage/run directory containing gate authority.
    """

    def __init__(self, product_root: Path, output_root: Path, execution_key: str,
                 image: str, *, writable_product: bool = True,
                 target_env: dict[str, str] | None = None, network: str = "none",
                 protected_roots=()):
        if network != "none":
            raise IsolationError("Isolated tools support --network none only; external "
                                 "browser targets need an approved allowlisted proxy.")
        if not execution_key or not image or image.startswith("-"):
            raise ValueError("An execution key and explicit worker image are required")
        self.product_root = self._root(product_root)
        self.output_root = self._root(output_root)
        roots = [self.product_root, self.output_root]
        if self._overlap(*roots):
            raise IsolationError("Product and media directories must be disjoint")
        for protected in protected_roots:
            protected = Path(protected).resolve()
            if any(self._overlap(root, protected) for root in roots):
                raise IsolationError("Worker mount overlaps controller authority")
        self.target_env = dict(target_env or {})
        if set(self.target_env) - _TARGET_ENV:
            raise IsolationError("Only explicit target QA_USER/QA_PASS credentials are allowed")
        if any(not isinstance(value, str) or "\0" in value
               for value in self.target_env.values()):
            raise ValueError("Target environment values must be strings without NUL")
        self.execution_key = execution_key
        self.image = image
        self.image_id = None
        self.container_id = None
        self.writable_product = writable_product
        self._names = set()
        self._lock = threading.RLock()
        self._stopped = False
        self.cancellation = CURRENT_CANCELLATION.get()
        if self.cancellation:
            self.cancellation.register(self)

    @staticmethod
    def _root(value):
        root = Path(value).resolve(strict=True)
        if not root.is_dir() or root == Path(root.anchor) or "," in str(root):
            raise IsolationError("Worker mounts must be non-root directories without commas")
        return root

    @staticmethod
    def _overlap(a, b):
        return a == b or a in b.parents or b in a.parents

    def _pin_image(self):
        if self.image_id:
            return
        import json
        result = subprocess.run(["docker", "image", "inspect", self.image],
                                capture_output=True, text=True, timeout=30, check=True)
        spec = json.loads(result.stdout)[0]
        image_id = spec["Id"]
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
            raise IsolationError("Docker did not return a content-addressed image ID")
        names = {entry.partition("=")[0] for entry in spec["Config"].get("Env", [])}
        if names - _IMAGE_ENV:
            raise IsolationError("Worker image contains unapproved environment keys")
        if spec["Config"].get("Volumes"):
            raise IsolationError("Worker image may not declare implicit volumes")
        self.image_id = image_id

    def _new_name(self):
        with self._lock:
            if self._stopped or (self.cancellation and self.cancellation.cancelled.is_set()):
                raise IsolationError("Worker has already stopped")
            name = "lantern-tool-" + uuid.uuid4().hex
            self._names.add(name)
            return name

    def _args(self, name):
        args = ["docker", "run", "--rm", "--name", name,
                "--label", "lantern.tool-worker=true", "--network", "none",
                "--label", "lantern.execution-key=" + hashlib.sha256(
                    self.execution_key.encode()).hexdigest(),
                "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                "--user", "1000:1000", "--pids-limit", "128", "--memory", "2g",
                "--memory-swap", "2g", "--cpus", "2", "--log-driver", "none",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
                "--tmpfs", "/home/worker:rw,nosuid,nodev,size=64m,uid=1000,gid=1000",
                "--mount", f"type=bind,source={self.product_root},target=/work/product" +
                ("" if self.writable_product else ",readonly"),
                "--mount", f"type=bind,source={self.output_root},target=/work/media",
                "--workdir", "/work/product", "--entrypoint", "/usr/bin/env"]
        return args

    def _env_args(self):
        return ["-i", *(f"{key}={value}" for key, value in (_ENV | self.target_env).items())]

    def _remove(self, name):
        result = subprocess.run(["docker", "rm", "--force", name], capture_output=True,
                                text=True, timeout=30)
        if result.returncode and "No such container" not in result.stderr:
            raise IsolationError("Docker could not remove an isolated tool container")
        with self._lock:
            self._names.discard(name)

    def start(self):
        """Start the MCP lifetime container, pinning the image before execution."""
        with self._lock, worker_mount(self.product_root, self.execution_key):
            if self.container_id:
                return self
            self._pin_image()
            name = self._new_name()
            try:
                result = subprocess.run(self._args(name) + ["--detach", self.image_id,
                                        *self._env_args(), "sleep", "infinity"],
                                        capture_output=True, text=True, timeout=30, check=True)
                container_id = result.stdout.strip()
                if not re.fullmatch(r"[a-f0-9]{64}", container_id):
                    raise IsolationError("Docker returned an invalid tool container ID")
                self.container_id = container_id
            except BaseException:
                self._remove(name)
                raise
        return self

    def run(self, command: str, timeout_s: float = 600):
        """Run a shell command; no background process survives this call."""
        if not isinstance(command, str) or not command.strip() or "\0" in command:
            raise ValueError("A nonempty shell command without NUL is required")
        if isinstance(timeout_s, bool) or not 0 < timeout_s <= 3600:
            raise ValueError("Tool timeout must be between 0 and 3600 seconds")
        # Create under the lifecycle lock. stop() must not remove a still-absent
        # name just before Docker creates it and leave a late-starting orphan.
        with self._lock, worker_mount(self.product_root, self.execution_key):
            self._pin_image()
            name = self._new_name()
            args = self._args(name)
            args[1] = "create"
            try:
                subprocess.run(args + [self.image_id, *self._env_args(),
                               "/bin/bash", "-c", command], capture_output=True,
                               text=True, timeout=30, check=True)
            except BaseException:
                self._remove(name)
                raise
        try:
            return _bounded_run(["docker", "start", "--attach", name], timeout_s)
        finally:
            self._remove(name)

    def mcp_command(self, argv: list[str]):
        """Build a stdio transport command; the server executes inside the worker."""
        if not argv or any(not isinstance(arg, str) or "\0" in arg for arg in argv):
            raise ValueError("MCP command must be a nonempty string argument list")
        if not self.container_id or self._stopped:
            raise IsolationError("Start the isolated worker before connecting MCP")
        return ["docker", "exec", "-i", self.container_id, "/usr/bin/env",
                *self._env_args(), *argv]

    def stop(self):
        """Fail visibly if any worker cannot be reaped; safe to retry cleanup."""
        with self._lock:
            self._stopped = True
            errors = []
            for name in tuple(self._names):
                try:
                    self._remove(name)
                except (IsolationError, subprocess.SubprocessError) as exc:
                    errors.append(exc)
            self.container_id = None
            if errors:
                raise IsolationError("Failed to clean up isolated tool workers") from errors[0]

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stop()
