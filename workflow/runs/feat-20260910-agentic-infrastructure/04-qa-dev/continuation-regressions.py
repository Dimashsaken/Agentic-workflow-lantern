"""Independent local regressions; explicit logs, exit codes and source snapshot."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent


def snapshot():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ("tools/azure-runner", "tools/mission-control")
            for p in sorted((ROOT / folder).glob("*.py"))}


before = snapshot()
results = []
env = os.environ.copy()
env["PYTHONPATH"] = os.pathsep.join(filter(None, [env.get("PYTHONPATH"), str(ROOT / "tools/azure-runner")]))
suites = [("tools/azure-runner", n) for n in
          ("test_tool_policy.py", "test_evidence.py", "test_gate_integrity.py", "test_execution_journal.py")]
suites.append(("tools/mission-control", "test_traceability.py"))
for directory, name in suites:
    command = [sys.executable, "-m", "unittest", "discover", "-s", directory, "-p", name, "-v"]
    proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log = f"continuation-{name.removesuffix('.py')}.txt"
    (OUT / log).write_text(proc.stdout + proc.stderr, encoding="utf-8")
    result = {"suite": name, "exit": proc.returncode, "log": log}
    results.append(result)
    print(json.dumps(result), flush=True)
after = snapshot()
record = {"kind": "local_regression", "fleet_execution": False,
          "recorded_at": datetime.now(timezone.utc).isoformat(), "python": sys.version,
          "results": results, "source_sha256": before, "source_changed_during_tests": before != after}
(OUT / "continuation-regression-results.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
raise SystemExit(int(any(r["exit"] for r in results)))
