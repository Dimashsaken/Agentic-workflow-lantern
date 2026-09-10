"""Run this checkout's configured checks; no database, model call or pipeline gate.

Invoke with a Python environment containing tools/azure-runner/requirements.txt.
This is a local engineering evidence recorder, not a fleet execution attestation.
"""

import hashlib
import json
from pathlib import Path
import re
import sys
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools/azure-runner"))
import factory


def main():
    config = factory.quality_config(ROOT)
    if config.get("error"):
        raise SystemExit(config["error"])
    factory.QUALITY_TAIL = 10_000_000  # retain complete check output in local evidence
    results = []
    for name, command in config["commands"]:
        result = factory.run_command(command, ROOT, config["timeout_s"])
        output = result.pop("output_tail")
        log = OUT / f"quality-{name}.log"
        log.write_text(output, encoding="utf-8")
        result.update(name=name, command=command, log=log.name,
                      unittest_count=sum(int(n) for n in re.findall(r"^Ran (\d+) tests? in", output, re.M)))
        results.append(result)
        print(f"{name}: exit {result['exit']}, {result['seconds']}s; full output in {log.name}", flush=True)
    manifest = {}
    for directory in ("tools/azure-runner", "tools/evals", "tools/mission-control"):
        for path in sorted((ROOT / directory).glob("*.py")):
            manifest[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    record = {"kind": "local_engineering_checks", "fleet_execution": False,
              "recorded_at": datetime.now(timezone.utc).isoformat(),
              "python": sys.version, "quality_sha256": config["sha256"],
              "passed": all(r["passed"] for r in results), "results": results,
              "source_sha256": manifest}
    (OUT / "local-quality.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if record["passed"] else 1)


if __name__ == "__main__":
    main()
