"""Run the complete configured policy; preserve logs and tested source identity."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
label = sys.argv[1] if len(sys.argv) > 1 else "continuation3"
if not re.fullmatch(r"[a-z0-9-]+", label):
    raise ValueError("invalid evidence label")
policy_bytes = (ROOT / "lantern.toml").read_bytes()
policy = tomllib.loads(policy_bytes.decode())["quality"]
paths = sorted(set((ROOT / "tools/azure-runner").glob("*.py")) | set((ROOT / "tools/evals").glob("*.py")) | set((ROOT / "tools/mission-control").glob("*.py")))
hashes = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
record = {"kind": "complete_configured_local_checks", "recorded_at": datetime.now(timezone.utc).isoformat(), "python": sys.version, "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(), "source_sha256": hashes, "results": []}
env = dict(os.environ)
env["LANTERN_PYTHON"] = sys.executable
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONUTF8"] = "1"
if os.name == "nt":
    git_bin = Path("C:/Program Files/Git/bin")
    if not (git_bin / "bash.exe").is_file():
        raise RuntimeError("Configured tests require the existing Git Bash installation")
    env["PATH"] = str(git_bin) + os.pathsep + env["PATH"]
    record["shell"] = str(git_bin / "bash.exe")
for name in ("test", "lint"):
    command = policy[name].replace("$LANTERN_PYTHON", '"' + Path(sys.executable).as_posix() + '"')
    log = OUT / f"{label}-{name}.log"
    start = time.monotonic()
    with log.open("w", encoding="utf-8") as output:
        result = subprocess.run([record.get("shell", "bash"), "-c", command], cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=policy["timeout_s"])
    text = log.read_text(encoding="utf-8", errors="replace")
    counts = [int(x) for x in re.findall(r"Ran (\d+) tests? in", text)]
    skips = [int(x) for x in re.findall(r"OK \(skipped=(\d+)\)", text)]
    record["results"].append({"name": name, "exit_code": result.returncode, "seconds": round(time.monotonic() - start, 3), "unittest_cases": sum(counts), "unittest_skips": sum(skips), "log": log.name})
    print(json.dumps(record["results"][-1]), flush=True)
after = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
record["runtime_source_unchanged_during_checks"] = hashes == after
record["passed"] = all(r["exit_code"] == 0 for r in record["results"]) and hashes == after
(OUT / f"{label}-quality.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
raise SystemExit(0 if record["passed"] else 1)
