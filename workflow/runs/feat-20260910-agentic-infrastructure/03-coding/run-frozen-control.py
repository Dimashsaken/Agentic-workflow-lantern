"""Repeat actual-image frozen-source positive and tamper controls without Azure/DB."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
env = dict(os.environ)
env.update(LANTERN_LIVE_EVIDENCE_TEST="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
           LANTERN_SANDBOX_IMAGE="sha256:933a9c0899dae9c9d7f73d5bcf76a5298e7eaccea83b17233d4d8d56e3682756")
if os.name == "nt":
    env["PATH"] = "C:/Program Files/Git/bin;" + env["PATH"]
log = OUT / "continuation3-frozen-source.log"
with log.open("w", encoding="utf-8") as output:
    result = subprocess.run([sys.executable, "tools/azure-runner/test_trusted_evidence.py",
                            "FactoryGateHooks.test_real_isolated_worker_quality_gate_and_tamper_controls", "-v"],
                            cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=300)
records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.startswith('{"kind": "real-isolated-quality-evidence"')]
record = {"environment": "actual Docker image and disposable Git tree; no Azure or database", "exit_code": result.returncode,
          "observations": records, "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(), "passed": result.returncode == 0 and len(records) == 1}
(OUT / "continuation3-frozen-source.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"passed": record["passed"], "exit_code": result.returncode}))
raise SystemExit(0 if record["passed"] else 1)
