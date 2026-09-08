"""`pipeline.py evals …` — the factory measures itself (D20).

    pipeline.py evals build                       run folders → tools/evals/data/*.jsonl
    pipeline.py evals run --suite plan|validate|triage|repro|all [--live]
    pipeline.py evals report                      → tools/evals/REPORT.md (+ data/results.json)

Also runnable directly: `python tools/evals/evals_cli.py build`. Everything except
`run --live` is local: no database, no model, no network.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "azure-runner"))

import build  # noqa: E402
import replay  # noqa: E402
import report  # noqa: E402

ROOT = HERE.parents[1]
DATA = HERE / "data"
RUNS = ROOT / "workflow" / "runs"


def cmd_build(data_dir: Path = DATA, runs: Path = RUNS) -> dict[str, int]:
    counts = build.build(runs, data_dir)
    print("frozen: " + ", ".join(f"{n} {k}" for k, n in counts.items()) + f" -> {data_dir}")
    return counts


def cmd_run(suite: str, live: bool, data_dir: Path = DATA, model_call=None) -> dict[str, dict]:
    suites = list(replay.SUITES) if suite == "all" else [suite]
    out: dict[str, dict] = {}
    for s in suites:
        if live and s not in replay.LIVE_SUITES:
            print(f"{s}: frozen only (no live replay) - scoring what is on disk")
        res = replay.run_suite(s, data_dir, live=live and s in replay.LIVE_SUITES, model_call=model_call)
        (data_dir / f"results-{s}.json").write_text(json.dumps(res, indent=2, sort_keys=True) + "\n",
                                                     encoding="utf-8", newline="\n")
        metric, value = replay.headline(res)
        print(f"{s:<9} {res['mode']:<7} n={res['n_inputs']:<3} {metric}: {value}")
        out[s] = res
    return out


def cmd_report(data_dir: Path = DATA, root: Path = ROOT, reuse_live: bool = True) -> Path:
    if not any((data_dir / f"{n}.jsonl").is_file() for n in build.FILES):
        cmd_build(data_dir)
    results: dict[str, dict] = {}
    for s in replay.SUITES:
        prior = data_dir / f"results-{s}.json"
        res = None
        if reuse_live and prior.is_file():
            try:
                cand = json.loads(prior.read_text(encoding="utf-8"))
                if cand.get("mode") == "live":
                    res = cand
            except ValueError:
                res = None
        results[s] = res or replay.run_suite(s, data_dir)
    path = report.write_report(root, data_dir, results)
    print(f"wrote {path.relative_to(root).as_posix()}")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline.py evals", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="freeze workflow/runs/* into tools/evals/data/*.jsonl")
    p = sub.add_parser("run", help="score one suite (frozen), or replay the role on the real model")
    p.add_argument("--suite", required=True, choices=list(replay.SUITES) + ["all"])
    p.add_argument("--live", action="store_true", help="replay with the real model (Azure, opt-in, costs)")
    sub.add_parser("report", help="write tools/evals/REPORT.md from every suite")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        cmd_build()
    elif a.cmd == "run":
        if not any((DATA / f"{n}.jsonl").is_file() for n in build.FILES):
            cmd_build()
        cmd_run(a.suite, a.live)
    elif a.cmd == "report":
        cmd_report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
