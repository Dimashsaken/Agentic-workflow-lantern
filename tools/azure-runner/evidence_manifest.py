"""Trusted-controller execution evidence, separate from worker-authored claims.

Only the controller calls capture/build/publish using observed process results and
recorder identities. A verifier needs a digest and identity from controller storage,
never from the manifest being verified. Hashes bind those observations to bytes;
they do not establish test quality, semantic coverage, or honest worker prose.
The authority directory must not be mounted into the worker. Source inspection
requires a controller-owned checkout with trusted Git metadata and no concurrent
writer; it covers tracked source, not ignored dependencies or the remote service.
"""

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import stat

import readonly_git
import tool_execution
from tool_policy import confined, path_parts


VERSION = 1
IDENTITY_FIELDS = ("run_id", "execution_key", "stage", "attempt", "lease_token",
                   "harness_revision", "image_digest", "quality_policy_sha256")


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(value, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _hash(value, name: str, *, git=False) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}" if git else r"[0-9a-f]{64}", value):
        raise ValueError(f"{name} must be a full digest")
    return value


def _git(product: Path, *args: str) -> bytes:
    env = readonly_git.environment()
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    result = tool_execution.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", *args],
                            cwd=product, env=env, stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError("cannot inspect the tested product revision")
    return result.stdout


def source_bytes(path: Path, limit: int = 64_000_000) -> bytes:
    """Bound hash inputs and reject swapped special files before reading them.

    Caller confines the path. A concurrent writer cannot make a FIFO block the
    controller, or make unverified bytes admissible as a committed blob.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise ValueError("source must be a bounded ordinary file with one link")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("source exceeds bounded hash input")
        return data


def capture_product_state(product: Path) -> dict:
    """Require committed, clean source; hash actual bytes without Git filters.

    Comparing blobs ourselves catches assume-unchanged/skip-worktree tricks that
    status alone misses, and never invokes product-defined clean filters. Symlinks,
    submodules, staged changes and non-ignored untracked files fail closed.
    """
    product = Path(product).resolve()
    top_text = os.fsdecode(_git(product, "rev-parse", "--show-toplevel")).strip()
    top = product if tool_execution.worker_for(product) and top_text == "/work/product" else Path(top_text).resolve()
    if top != product:
        raise ValueError("product must be the exact checkout root")
    head = _git(product, "rev-parse", "HEAD").decode().strip()
    tree = _git(product, "rev-parse", "HEAD^{tree}").decode().strip()
    _hash(head, "product head", git=True)
    entries = {}
    for entry in _git(product, "ls-tree", "-rz", "--full-tree", "HEAD").split(b"\0"):
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        mode, kind, blob = metadata.decode().split()
        name = os.fsdecode(raw_name)
        if mode not in {"100644", "100755"} or kind != "blob":
            raise ValueError("tested source cannot contain symlinks or submodules")
        entries[name] = (mode, blob)
    indexed = {}
    for entry in _git(product, "ls-files", "--stage", "-z").split(b"\0"):
        if entry:
            metadata, raw_name = entry.split(b"\t", 1)
            mode, blob, stage = metadata.decode().split()
            if stage != "0":
                raise ValueError("tested source has unresolved index entries")
            indexed[os.fsdecode(raw_name)] = (mode, blob)
    if entries != indexed or _git(product, "ls-files", "--others", "--exclude-standard", "-z"):
        raise ValueError("tested product must be clean and committed")
    autocrlf = "core.autocrlf=true" in readonly_git.repository_options(product)
    actual = []
    for name, (mode, blob) in sorted(entries.items()):
        source = confined(product, path_parts(name))
        if os.name != "nt" and bool(source.stat().st_mode & 0o111) != (mode == "100755"):
            raise ValueError(f"tested source mode differs from committed revision: {name}")
        data = source_bytes(source)
        hash_fn = hashlib.sha1 if len(blob) == 40 else hashlib.sha256
        candidates = [data]
        if autocrlf and b"\x00" not in data:
            candidates.append(data.replace(b"\r\n", b"\n"))
        if not any(hash_fn(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest() == blob
                   for content in candidates):
            raise ValueError(f"tested source differs from committed revision: {name}")
        actual.append([name, _digest(data)])
    if _git(product, "rev-parse", "HEAD").decode().strip() != head:
        raise ValueError("tested revision changed during capture")
    return {"head_sha": head, "tree_sha": tree, "worktree_sha256": _digest(_canonical(actual))}


def probe_video(path: Path, *, ffprobe: str = "ffprobe", ffmpeg: str = "ffmpeg") -> dict:
    """Inspect streams and decode every frame using controller-owned executables.

    Successful decoding proves playable bytes, not the identity of the application
    recorded. That comes from the controller's recorder session, not file metadata.
    """
    result = subprocess.run([ffprobe, "-v", "error", "-protocol_whitelist", "file",
                             "-format_whitelist", "matroska,webm,mov", "-show_entries",
                             "format=duration:stream=codec_type,codec_name,width,height",
                             "-of", "json", str(Path(path).resolve())], capture_output=True,
                            text=True, timeout=60, stdin=subprocess.DEVNULL)
    if result.returncode:
        raise ValueError("video probe failed")
    try:
        value = json.loads(result.stdout)
        duration = float(value["format"]["duration"])
        streams = [s for s in value["streams"] if s.get("codec_type") == "video"]
        if not math.isfinite(duration) or duration <= 0 or not streams:
            raise ValueError("video requires positive duration and a video stream")
        if any(type(s.get("width")) is not int or type(s.get("height")) is not int
               or s["width"] <= 0 or s["height"] <= 0 or not s.get("codec_name") for s in streams):
            raise ValueError("invalid video stream")
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid video metadata") from exc
    decoded = subprocess.run([ffmpeg, "-v", "error", "-xerror", "-protocol_whitelist", "file",
                              "-format_whitelist", "matroska,webm,mov", "-i", str(Path(path).resolve()),
                              "-map", "0:v", "-f", "null", "-"], capture_output=True,
                             timeout=120, stdin=subprocess.DEVNULL)
    if decoded.returncode:
        raise ValueError("video decode failed")
    return {"duration_seconds": duration, "streams": streams, "decoded": True}


def _check_records(manifest: dict, expected_requirements=()) -> None:
    tests = manifest.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ValueError("manifest requires controller-observed tests")
    by_id = {}
    for test in tests:
        if not isinstance(test, dict):
            raise ValueError("invalid test record")
        test_id = _text(test.get("id"), "test id")
        _text(test.get("command"), "test command")
        if test_id in by_id:
            raise ValueError("duplicate test id")
        if type(test.get("exit_code")) is not int or test.get("outcome") not in {"pass", "fail"}:
            raise ValueError("test requires observed exit_code and pass/fail outcome")
        if (test["exit_code"] == 0) != (test["outcome"] == "pass"):
            raise ValueError("test outcome contradicts observed exit_code")
        by_id[test_id] = test
    links = manifest.get("requirement_tests")
    if not isinstance(links, dict):
        raise ValueError("requirement_tests must be an explicit mapping")
    for requirement, ids in links.items():
        _text(requirement, "requirement id")
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in by_id for i in ids):
            raise ValueError("requirement links must identify executed tests")
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate requirement test link")
    for requirement in expected_requirements:
        if requirement not in links:
            raise ValueError(f"missing requirement-to-test links: {requirement}")
        if any(by_id[i]["outcome"] != "pass" for i in links[requirement]):
            raise ValueError(f"requirement has failing tests: {requirement}")


def _check_identity(manifest: dict) -> None:
    if manifest.get("version") != VERSION or type(manifest.get("version")) is not int:
        raise ValueError("unsupported evidence manifest version")
    for field in ("run_id", "execution_key", "stage"):
        _text(manifest.get(field), field)
    if type(manifest.get("attempt")) is not int or manifest["attempt"] < 0:
        raise ValueError("attempt must be a nonnegative integer")
    token = manifest.get("lease_token")
    if token is not None:
        _text(token, "lease_token")
    _hash(manifest.get("harness_revision"), "harness_revision", git=True)
    image = manifest.get("image_digest")
    if not isinstance(image, str) or not image.startswith("sha256:"):
        raise ValueError("image_digest must be a resolved sha256 image identity")
    _hash(image[7:], "image_digest")
    _hash(manifest.get("quality_policy_sha256"), "quality_policy_sha256")


def build_manifest(*, run_id: str, execution_key: str, stage: str, attempt: int,
                   product: Path, product_before: dict, harness_revision: str,
                   image_digest: str, quality_policy_sha256: str, tests: list[dict],
                   requirement_tests: dict, artifact_root: Path, artifacts: list[dict],
                   lease_token: str | None = None, video_probe=probe_video) -> dict:
    """Capture after tests; reject any source change since product_before.

    tests and video capture records MUST originate from trusted controller code.
    There is deliberately no parser importing worker JSON as authoritative facts.
    Empty requirement_tests is legal but supports no coverage claim.
    """
    after = capture_product_state(product)
    if after != product_before:
        raise ValueError("tested product changed after the pre-test snapshot")
    manifest = {"version": VERSION, "run_id": run_id, "execution_key": execution_key,
                "stage": stage, "attempt": attempt, "lease_token": lease_token,
                "harness_revision": harness_revision, "image_digest": image_digest,
                "quality_policy_sha256": quality_policy_sha256, "product": after,
                "recorded_at": datetime.now(timezone.utc).isoformat(), "tests": tests,
                "requirement_tests": requirement_tests, "artifacts": []}
    _check_identity(manifest)
    _check_records(manifest)
    seen = set()
    for spec in artifacts:
        relative = "/".join(path_parts(spec["path"]))
        if relative in seen:
            raise ValueError("duplicate artifact path")
        seen.add(relative)
        path = confined(Path(artifact_root), path_parts(relative))
        data = source_bytes(path)
        if not data:
            raise ValueError("evidence artifact is empty")
        artifact = {"path": relative, "sha256": _digest(data), "size": len(data),
                    "kind": spec.get("kind", "file")}
        if artifact["kind"] not in {"file", "video"}:
            raise ValueError("unknown artifact kind")
        if artifact["kind"] == "video":
            capture = spec.get("capture")
            if not isinstance(capture, dict) or capture.get("execution_key") != execution_key:
                raise ValueError("video requires the controller's matching recorder execution")
            for field in ("session_id", "recorder", "started_at", "ended_at"):
                _text(capture.get(field), f"capture {field}")
            if capture["recorder"] != "host-playwright":
                raise ValueError("video requires a trusted host-playwright capture")
            artifact["capture"] = capture
            artifact["video"] = video_probe(path)
            if _digest(path.read_bytes()) != artifact["sha256"]:
                raise ValueError("video changed while decoding")
        manifest["artifacts"].append(artifact)
    # Deep-copy host observations so later mutable result updates cannot alter it.
    return json.loads(_canonical(manifest))


def publish_manifest(authority_root: Path, manifest: dict, *, writable_roots: list[Path]) -> dict:
    """Exclusive immutable-by-convention file; return digest for controller storage.

    This path validation complements OS isolation; it cannot create that isolation.
    Controllers must protect the directory and persist this receipt themselves.
    """
    authority_root = Path(authority_root).resolve()
    if not writable_roots or any(authority_root.is_relative_to(Path(p).resolve())
                                 or Path(p).resolve().is_relative_to(authority_root) for p in writable_roots):
        raise ValueError("manifest authority must be separate from writable roots")
    _check_identity(manifest)
    _check_records(manifest)
    payload = _canonical(manifest)
    digest = _digest(payload)
    authority_root.mkdir(parents=True, exist_ok=True)
    target = authority_root / f"{digest}.json"
    try:
        with target.open("xb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
    except FileExistsError:
        if target.is_symlink() or target.read_bytes() != payload:
            raise ValueError("existing authoritative manifest differs")
    return {"path": str(target), "sha256": digest}


def verify_manifest(path: Path, *, expected_sha256: str, expected_identity: dict,
                    product: Path, artifact_root: Path, expected_requirements=(),
                    video_probe=probe_video) -> list[str]:
    """Fail closed; expected digest and identity must come from trusted host state."""
    try:
        _hash(expected_sha256, "expected manifest digest")
        payload = Path(path).read_bytes()
        if _digest(payload) != expected_sha256:
            raise ValueError("manifest differs from authoritative digest")
        manifest = json.loads(payload)
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
        _check_identity(manifest)
        for field in (*IDENTITY_FIELDS, "product"):
            if field not in expected_identity or manifest.get(field) != expected_identity[field]:
                raise ValueError(f"manifest does not match expected {field}")
        if capture_product_state(product) != manifest["product"]:
            raise ValueError("product differs from tested revision")
        _check_records(manifest, expected_requirements)
        if not isinstance(manifest.get("artifacts"), list):
            raise ValueError("artifacts must be a list")
        seen = set()
        for artifact in manifest["artifacts"]:
            relative = "/".join(path_parts(artifact["path"]))
            if relative in seen:
                raise ValueError("duplicate artifact path")
            seen.add(relative)
            target = confined(Path(artifact_root), path_parts(relative))
            data = target.read_bytes()
            if type(artifact["size"]) is not int or not data or len(data) != artifact["size"] or _digest(data) != artifact["sha256"]:
                raise ValueError("artifact bytes differ from recorded evidence")
            if artifact.get("kind") == "video":
                capture = artifact.get("capture", {})
                if capture.get("execution_key") != manifest["execution_key"] or capture.get("recorder") != "host-playwright":
                    raise ValueError("video capture is not bound to this execution")
                for field in ("session_id", "started_at", "ended_at"):
                    _text(capture.get(field), f"capture {field}")
                if video_probe(target) != artifact.get("video"):
                    raise ValueError("video decode differs from capture metadata")
                if _digest(target.read_bytes()) != artifact["sha256"]:
                    raise ValueError("video changed while decoding")
            elif artifact.get("kind") != "file":
                raise ValueError("unknown artifact kind")
        return []
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError) as exc:
        return [f"evidence manifest: {exc}"]
