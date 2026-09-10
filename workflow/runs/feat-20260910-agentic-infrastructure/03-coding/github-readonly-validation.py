"""Actual configured bot credentials, GET only, no provider mutation or new rows."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/azure-runner"))
import pipeline
import github_publication as github

origin = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=ROOT, text=True).strip()
owner, name = pipeline._github_repo(origin)
root = f"/repos/{owner}/{name}"
calls = []


def read_api(method, path, data=None):
    if method != "GET" or data is not None:
        raise RuntimeError("Live validation only permits GET")
    status, value = pipeline._gh_api(method, path)
    item = {"method": method, "path": path, "status": status}
    if status >= 400 and isinstance(value, dict):
        item["message"] = pipeline._scrub(str(value.get("message", "")))[:400]
    calls.append(item)
    return status, value


record = {"recorded_at": datetime.now(timezone.utc).isoformat(), "environment": "actual GitHub REST with existing configured Lantern bot credential; read only", "repository": f"{owner}/{name}", "calls": calls, "provider_mutations": 0}
status, repo = read_api("GET", root)
if status == 200:
    record["repository_id"] = repo["id"]
    base = repo["default_branch"]
    status, ref = read_api("GET", root + "/git/ref/heads/" + base)
    if status == 200:
        record["base"] = base
        record["base_sha"] = ref["object"]["sha"]
        request = {"run_id": "manual-readonly-publication-probe", "repo": origin, "base": base,
                   "work": "feat/20260910-agentic-infrastructure", "branch": "feat/20260910-agentic-infrastructure", "head_sha": ref["object"]["sha"]}
        try:
            github.prepare_request(read_api, request, 3)
        except github.PublicationHeld as error:
            record["observer_result"] = "held"
            record["observer_reason"] = str(error)
        else:
            record["observer_result"] = "observation prepared; no publication attempted"
record["source_sha256"] = {name: hashlib.sha256((ROOT / "tools/azure-runner" / name).read_bytes()).hexdigest() for name in ("github_publication.py", "pipeline.py")}
Path(__file__).with_name("github-v3-readonly-validation.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, indent=2))
