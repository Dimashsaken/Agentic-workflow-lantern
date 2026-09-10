"""Controller-only adapter for quality gate evidence.

The gate in a run directory is a display mirror. Acceptance loads its own record
from an authority directory that is never mounted in the isolated tool worker.
Host process observations establish command completion, not semantic test coverage.
Execution lease/fencing checks remain the caller's responsibility.
"""

from copy import deepcopy
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid
import zlib

import evidence_manifest as manifests
import readonly_git
import tool_execution
import execution_runtime
from tool_policy import confined
from isolated_tools import IsolatedToolWorker


REPO = Path(__file__).resolve().parents[2]


def enabled() -> bool:
    return os.environ.get("LANTERN_TRUSTED_EVIDENCE") == "1"


def _overlap(left: Path, right: Path) -> bool:
    left, right = left.resolve(), right.resolve()
    return left.is_relative_to(right) or right.is_relative_to(left)


def _worker(root: Path):
    worker = tool_execution.worker_for(root)
    if worker is None or not re.fullmatch(r"sha256:[0-9a-f]{64}", worker.image_id or ""):
        raise ValueError("trusted evidence requires a bound isolated worker with a resolved image digest")
    return worker


def authority_root() -> Path:
    """Resolve host policy, never a worker-provided artifact path."""
    root = Path(os.environ.get("LANTERN_AUTHORITY_DIR", str(Path.home() / ".lantern" / "authority"))).resolve()
    protected = [REPO.resolve()]
    worker = tool_execution.CURRENT.get()
    if worker is not None:
        protected.extend([worker.product_root, worker.output_root])
    if any(_overlap(root, path) for path in protected):
        raise ValueError("evidence authority overlaps a worker mount or the harness repository")
    return root


def _gate_name(run_id: str, execution_key: str) -> str:
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id):
        raise ValueError("invalid evidence run identity")
    if not isinstance(execution_key, str) or not execution_key or "\x00" in execution_key:
        raise ValueError("invalid evidence execution identity")
    return hashlib.sha256((run_id + ":" + execution_key).encode()).hexdigest() + ".json"


def _write_gate(gate: dict) -> None:
    root = authority_root()
    root.mkdir(parents=True, exist_ok=True)
    directory = confined(root, ("gates",))
    directory.mkdir(exist_ok=True)
    name = _gate_name(gate["run_id"], gate["execution_key"])
    target = confined(root, ("gates", name))
    temporary = directory / ("." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as out:
            out.write(json.dumps(gate, sort_keys=True, allow_nan=False).encode())
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def load_gate(run_id: str, execution_key: str) -> tuple[dict | None, str | None]:
    """Read authority only; return (gate, error), never fall back to the mirror."""
    try:
        root = authority_root()
        path = confined(root, ("gates", _gate_name(run_id, execution_key)))
        if path.stat().st_size > 16_000_000:
            raise ValueError("authoritative gate exceeds size limit")
        gate = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(gate, dict) or gate.get("run_id") != run_id or gate.get("execution_key") != execution_key:
            raise ValueError("authoritative gate identity differs")
        return gate, None
    except (OSError, ValueError, TypeError) as exc:
        return None, f"trusted gate unavailable: {exc}"


def capture_before(root: Path) -> dict:
    _worker(root)
    return manifests.capture_product_state(root)


@dataclass
class QualitySnapshot:
    root: Path
    before: dict
    worker: object

    @contextmanager
    def bind(self):
        token = tool_execution.CURRENT.set(self.worker)
        try:
            yield
        finally:
            tool_execution.CURRENT.reset(token)


def _snapshot_files(source: Path, destination: Path, before: dict) -> None:
    """Rebuild committed files and safe loose Git objects, never copy .git config.

    Original Git runs only inside its isolated worker. File bytes read by the host
    must hash to each committed blob before they enter the independent snapshot.
    Trees are reconstructed and hashed locally; no product hooks/filters execute.
    """
    hash_fn = hashlib.sha1 if len(before['head_sha']) == 40 else hashlib.sha256
    metadata = destination / '.git'
    (metadata / 'objects').mkdir(parents=True)
    (metadata / 'refs' / 'heads').mkdir(parents=True)

    def store(kind, data, expected=None):
        encoded = kind.encode() + b' ' + str(len(data)).encode() + b'\0' + data
        digest = hash_fn(encoded).hexdigest()
        if expected is not None and expected != digest:
            raise ValueError(f"snapshot {kind} differs from committed object")
        directory = metadata / 'objects' / digest[:2]
        directory.mkdir(exist_ok=True)
        (directory / digest[2:]).write_bytes(zlib.compress(encoded))
        return digest

    autocrlf = 'core.autocrlf=true' in readonly_git.repository_options(source)
    tree = {}
    actual = []
    entries = manifests._git(source, 'ls-tree', '-rz', '--full-tree', before['head_sha'])
    for entry in entries.split(b'\0'):
        if not entry:
            continue
        descriptor, raw_name = entry.split(b'\t', 1)
        mode, kind, blob = descriptor.decode().split()
        if mode not in {'100644', '100755'} or kind != 'blob':
            raise ValueError('snapshot forbids symlinks and submodules')
        name = os.fsdecode(raw_name)
        parts = manifests.path_parts(name)
        if any(part.lower() == '.git' for part in parts):
            raise ValueError('snapshot source cannot contain Git metadata paths')
        origin = confined(source, parts)
        data = manifests.source_bytes(origin)
        canonical = data
        candidates = [data]
        if autocrlf and b'\0' not in data:
            candidates.append(data.replace(b'\r\n', b'\n'))
        for candidate in candidates:
            encoded = b'blob ' + str(len(candidate)).encode() + b'\0' + candidate
            if hash_fn(encoded).hexdigest() == blob:
                canonical = candidate
                break
        else:
            raise ValueError(f'snapshot source differs from committed revision: {name}')
        store('blob', canonical, blob)
        target = confined(destination, parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)  # Preserve genuinely tested CRLF bytes where applicable.
        target.chmod(0o755 if mode == '100755' else 0o644)
        actual.append([name, hashlib.sha256(data).hexdigest()])
        directory = tree
        for part in raw_name.split(b'/')[:-1]:
            directory = directory.setdefault(part, {})
            if not isinstance(directory, dict):
                raise ValueError('snapshot has a file/directory collision')
        directory[raw_name.split(b'/')[-1]] = (mode, blob)

    def store_tree(directory):
        items = []
        for name, value in directory.items():
            mode, digest = ('40000', store_tree(value)) if isinstance(value, dict) else value
            sort_name = name + (b'/' if mode == '40000' else b'')
            items.append((sort_name, mode.encode() + b' ' + name + b'\0' + bytes.fromhex(digest)))
        return store('tree', b''.join(item[1] for item in sorted(items)))

    if store_tree(tree) != before['tree_sha']:
        raise ValueError('snapshot tree differs from captured revision')
    if manifests._digest(manifests._canonical(sorted(actual))) != before['worktree_sha256']:
        raise ValueError('snapshot bytes differ from pre-test capture')
    commit = manifests._git(source, 'cat-file', 'commit', before['head_sha'])
    store('commit', commit, before['head_sha'])
    if commit.split(b'\n', 1)[0] != b'tree ' + before['tree_sha'].encode():
        raise ValueError('snapshot commit does not identify the captured tree')
    (metadata / 'HEAD').write_text(before['head_sha'] + '\n', encoding='ascii')
    config = '[core]\nrepositoryformatversion = ' + ('0' if len(before['head_sha']) == 40 else '1')
    config += '\nbare = false\nfilemode = true\nautocrlf = ' + ('true' if autocrlf else 'false') + '\n'
    if len(before['head_sha']) == 64:
        config += '[extensions]\nobjectformat = sha256\n'
    (metadata / 'config').write_text(config, encoding='ascii')


@contextmanager
def quality_snapshot(root: Path):
    """Yield a tracked-only, read-only quality worker; preserve the agent checkout.

    The preparation worker runs only trusted read-tree against new safe metadata,
    and is fully stopped before any command sees the read-only source mount.
    Ignored/untracked dependency trees are never copied or mounted. Tests needing
    writable paths must use /tmp or /work/media; there is no writable fallback.
    """
    root = Path(root).resolve()
    original = _worker(root)
    before = capture_before(root)
    authority = authority_root()
    with tempfile.TemporaryDirectory(prefix='lantern-quality-') as temporary:
        base = Path(temporary).resolve()
        snapshot, output = base / 'source', base / 'output'
        snapshot.mkdir()
        output.mkdir()
        protected = (REPO, authority, original.product_root, original.output_root)
        if any(_overlap(base, path) for path in protected):
            raise ValueError('quality snapshot overlaps an existing worker or authority mount')
        _snapshot_files(root, snapshot, before)
        if capture_before(root) != before:
            raise ValueError('original source changed while preparing quality snapshot')
        preparation = IsolatedToolWorker(snapshot, output, original.execution_key,
            original.image_id, protected_roots=protected)
        try:
            result = preparation.run('git -c safe.directory=/work/product -c core.fsmonitor=false read-tree HEAD', timeout_s=30)
            if result.returncode:
                raise ValueError('cannot build clean snapshot index')
        finally:
            preparation.stop()
        worker = IsolatedToolWorker(snapshot, output, original.execution_key,
            original.image_id, writable_product=False, protected_roots=protected)
        worker.image_id = original.image_id  # Already validated content-addressed image.
        worker._frozen_source_identity = deepcopy(before)
        view = QualitySnapshot(snapshot, before, worker)
        try:
            with view.bind():
                if capture_before(snapshot) != before:
                    raise ValueError('read-only snapshot differs from original pre-test identity')
            yield view
        finally:
            worker.stop()


def _harness_revision() -> str:
    # REPO is controller configuration, never the product/worker-supplied path.
    result = subprocess.run(["git", "-c", "core.fsmonitor=false", "rev-parse", "HEAD"],
                            cwd=REPO, env=readonly_git.environment(), capture_output=True,
                            text=True, stdin=subprocess.DEVNULL, timeout=30)
    revision = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
        raise ValueError("cannot resolve controller harness revision")
    return revision


def _harness_state() -> dict:
    """Fingerprint executing source including new files; HEAD alone is insufficient."""
    files = set()
    for directory in (REPO / "tools" / "azure-runner", REPO / "infra" / "sandbox",
                      REPO / "agents", REPO / "workflow" / "templates"):
        for location, directories, names in os.walk(directory):
            directories[:] = [d for d in directories if d not in {".venv", "__pycache__"}]
            for name in names:
                path = Path(location) / name
                if path.suffix in {".py", ".sh", ".sql", ".md", ".toml", ".txt"} or name == "Dockerfile":
                    files.add(path)
    records = [[p.relative_to(REPO).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()]
               for p in sorted(files)]
    status = subprocess.run(["git", "-c", "core.fsmonitor=false", "status", "--porcelain", "--untracked-files=all"],
                            cwd=REPO, env=readonly_git.environment(), capture_output=True,
                            text=True, stdin=subprocess.DEVNULL, timeout=30)
    if status.returncode:
        raise ValueError("cannot inspect controller source state")
    return {"revision": _harness_revision(), "dirty": bool(status.stdout.strip()),
            "source_sha256": hashlib.sha256(json.dumps(records, separators=(",", ":")).encode()).hexdigest(),
            "source_scope": ["tools/azure-runner source", "infra/sandbox source", "agents", "workflow/templates"],
            "files": records}


def _attempt_and_lease(gate: dict) -> tuple[int, str | None]:
    prefix = f"{gate['run_id']}:{gate['stage']}:"
    key = gate["execution_key"]
    if not key.startswith(prefix) or not key[len(prefix):].isdigit() or int(key[len(prefix):]) < 1:
        raise ValueError("execution key must identify this run, stage and positive attempt")
    ownership = execution_runtime.STAGE.get()
    if execution_runtime.enabled() and ownership is None:
        raise ValueError("trusted execution evidence has no stage lease")
    token = None
    if ownership is not None:
        lease = ownership.lease
        if lease.run_id != gate["run_id"] or lease.execution_id is None:
            raise ValueError("stage lease differs from evidence execution")
        token = f"{lease.owner}:{lease.execution_id}:{lease.fence}:{lease.parent_fence}"
    return int(key[len(prefix):]), token


def _fail(gate: dict, error: str) -> dict:
    gate["passed"] = False
    gate["provenance"] = {"status": "unverified", "error": error}
    # Config is an existing typed gate failure, not a new unknown command name.
    results = gate.setdefault("results", [])
    prior = next((r for r in results if isinstance(r, dict) and r.get("name") == "config"), None)
    if prior is None:
        results.append({"name": "config", "command": "trusted execution evidence", "exit": 1,
                        "passed": False, "seconds": 0.0, "output_tail": error})
    else:
        prior.update(exit=1, passed=False, output_tail=str(prior.get("output_tail", "")) + "\n" + error)
    return gate


def seal_gate(gate: dict, root: Path, contract: dict, before: dict,
              requirement_tests: dict, expected_requirements: list[str], artifact_root: Path) -> dict:
    """Seal host-observed quality results; failure replaces any earlier authority.

    requirement_tests must come from the approved typed plan. No links are inferred
    from prose, filenames, stdout, or a command's success status.
    """
    gate = deepcopy(gate)
    if not enabled():
        return gate
    try:
        worker = _worker(root)
        if getattr(worker, 'writable_product', True) or getattr(worker, '_frozen_source_identity', None) != before:
            raise ValueError('quality evidence requires the controller-created read-only committed snapshot')
        if worker.execution_key != gate.get("execution_key"):
            raise ValueError("worker and quality gate executions differ")
        attempt, lease_token = _attempt_and_lease(gate)
        if not isinstance(expected_requirements, list) or not expected_requirements or any(
                not isinstance(item, str) or not item for item in expected_requirements):
            raise ValueError("trusted evidence requires explicit expected acceptance criteria")
        if not isinstance(requirement_tests, dict) or any(not requirement_tests.get(i) for i in expected_requirements):
            raise ValueError("missing explicit planned requirement-to-test links")
        commands = dict(contract.get("commands", []))
        if contract.get("error") or not commands.get("test") or contract.get("sha256") != gate.get("config_sha256"):
            raise ValueError("quality gate does not match the captured policy")
        policy = confined(Path(root), ("lantern.toml",)).read_bytes()
        if hashlib.sha256(policy).hexdigest() != contract["sha256"]:
            raise ValueError("tested quality policy differs from captured policy")
        results = gate.get("results")
        if not isinstance(results, list) or not results or any(not isinstance(r, dict) for r in results):
            raise ValueError("typed controller command results are required")
        for result in results:
            if type(result.get("exit")) is not int or type(result.get("passed")) is not bool or result["passed"] != (result["exit"] == 0):
                raise ValueError("gate command outcome contradicts observed exit status")
        if type(gate.get("passed")) is not bool or gate["passed"] != all(r["passed"] for r in results):
            raise ValueError("gate summary contradicts observed command results")
        tests = []
        for result in results:
            name = result.get("name")
            if name not in commands:
                continue
            if result.get("command") != commands[name] or type(result.get("passed")) is not bool:
                raise ValueError("observed command differs from captured policy")
            tests.append({"id": "quality:" + name, "command": result["command"],
                          "exit_code": result["exit"], "outcome": "pass" if result["passed"] else "fail",
                          "seconds": result.get("seconds"), "observed_at": gate.get("ran_at")})
        if set(test["id"] for test in tests) != {"quality:" + n for n in commands}:
            raise ValueError("not every captured quality command was observed")
        # Record red commands too, but no red test may support a covered claim.
        manifests._check_records({"tests": tests, "requirement_tests": requirement_tests},
                                 expected_requirements if gate.get("passed") is True else ())
        artifact_root = Path(artifact_root).resolve()
        if any(_overlap(artifact_root, p) for p in (worker.product_root, worker.output_root)):
            raise ValueError("controller test logs must be outside worker mounts")
        identifier = uuid.uuid4().hex
        artifact_root.mkdir(parents=True, exist_ok=True)
        directory = confined(artifact_root, ("execution-evidence", identifier))
        directory.mkdir(parents=True)
        # Use the existing harness redaction policy; import lazily to avoid the
        # factory -> trusted_evidence -> factory import cycle during startup.
        from factory import redact
        artifacts = []
        for index, result in enumerate(gate["results"]):
            relative = f"execution-evidence/{identifier}/command-{index}.txt"
            target = confined(artifact_root, tuple(relative.split("/")))
            text = (f"command: {result.get('command')}\nexit: {result.get('exit')}\n"
                    f"seconds: {result.get('seconds')}\n\n{result.get('output_tail', '')}\n")
            with target.open("x", encoding="utf-8") as out:
                out.write(redact(text))
            artifacts.append({"path": relative})
        harness_state = _harness_state()
        manifest = manifests.build_manifest(
            run_id=gate["run_id"], execution_key=gate["execution_key"], stage=gate["stage"],
            attempt=attempt, lease_token=lease_token, product=Path(root),
            product_before=before, harness_revision=harness_state["revision"], image_digest=worker.image_id,
            quality_policy_sha256=contract["sha256"], tests=tests, requirement_tests=requirement_tests,
            artifact_root=artifact_root, artifacts=artifacts)
        manifest["harness_state"] = harness_state
        manifest['tested_source'] = {'kind': 'read-only-committed-snapshot',
                                     'original_before': deepcopy(before),
                                     'ignored_dependencies_included': False,
                                     'git_metadata': 'fresh validated objects and controller configuration'}
        manifest["quality_round"] = gate["round"]
        receipt = manifests.publish_manifest(authority_root() / "manifests", manifest,
                                              writable_roots=[worker.product_root, worker.output_root, REPO])
        gate["provenance"] = {"status": "verified", "manifest": receipt,
                              "identity": {k: manifest[k] for k in (*manifests.IDENTITY_FIELDS, "product")},
                              "artifact_root": str(artifact_root), "requirements": expected_requirements,
                              "test_links": deepcopy(requirement_tests),
                              "harness_state": {k: v for k, v in harness_state.items() if k != "files"},
                              "scope": "controller-observed commands; semantic test coverage requires review"}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError) as exc:
        _fail(gate, f"trusted evidence: {exc}")
    try:
        _write_gate(gate)
    except (OSError, ValueError, TypeError) as exc:
        _fail(gate, f"trusted evidence authority could not be persisted: {exc}")
    return gate


def verify_gate(gate: dict, root: Path, expected_run: str, expected_key: str,
                expected_requirements: list[str]) -> list[str]:
    """Ignore a display mirror's provenance; use the independent host record."""
    stored, error = load_gate(expected_run, expected_key)
    if error:
        return [error]
    if stored != gate:
        return ["quality gate differs from controller authority"]
    provenance = stored.get("provenance", {})
    if provenance.get("status") != "verified":
        return ["quality gate lacks verified execution evidence: " + str(provenance.get("error", "missing"))]
    try:
        if provenance.get("requirements") != expected_requirements:
            raise ValueError("expected acceptance criteria differ from sealed gate")
        identity = provenance["identity"]
        if identity["run_id"] != expected_run or identity["execution_key"] != expected_key:
            raise ValueError("evidence identity differs from expected execution")
        worker = _worker(root)
        if worker.execution_key != expected_key or worker.image_id != identity["image_digest"]:
            raise ValueError("verifier worker differs from recorded execution or image")
        attempt, lease_token = _attempt_and_lease(stored)
        if identity["attempt"] != attempt or identity["lease_token"] != lease_token:
            raise ValueError("evidence attempt or lease fence is stale")
        receipt = provenance["manifest"]
        # The receipt is read from the protected host gate, never the run mirror.
        manifest_path = Path(receipt["path"]).resolve()
        if not manifest_path.is_relative_to(authority_root() / "manifests"):
            raise ValueError("manifest is outside controller authority")
        problems = manifests.verify_manifest(manifest_path, expected_sha256=receipt["sha256"],
                                             expected_identity=identity, product=Path(root),
                                             artifact_root=Path(provenance["artifact_root"]),
                                             expected_requirements=expected_requirements)
        if problems:
            return problems
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        source = manifest.get('tested_source', {})
        if (source.get('kind') != 'read-only-committed-snapshot'
                or source.get('original_before') != identity['product']
                or source.get('ignored_dependencies_included') is not False):
            raise ValueError('quality manifest does not prove a committed read-only source snapshot')
        return []
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return [f"trusted evidence: {exc}"]
