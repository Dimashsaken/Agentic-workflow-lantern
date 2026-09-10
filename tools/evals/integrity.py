"""Labelled, deterministic negative controls for the quality-gate verifier.

These measure false greens on deliberately invalid records, not model quality or
human acceptance. Keep positive controls to detect a verifier that refuses everything.
"""

from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "azure-runner"))
import factory


def fixtures():
    good = {"kind": "quality_gate", "run_id": "eval-integrity", "stage": "03-coding",
            "builder": None, "execution_key": "eval:1", "round": 0, "passed": True,
            "configured": ["test"], "config_sha256": "a" * 64,
            "results": [{"name": "test", "command": "pytest -q", "exit": 0,
                         "passed": True, "seconds": 1, "output_tail": "1 passed"}]}
    cases = [("valid tested gate", good, True)]
    for label, changes in (
        ("no configured tests", {"configured": []}),
        ("missing result", {"results": []}),
        ("unrun lint command", {"configured": ["test", "lint"]}),
        ("duplicate command", {"configured": ["test", "test"]}),
        ("wrong run", {"run_id": "other"}),
        ("wrong stage", {"stage": "04-qa-dev"}),
        ("wrong builder", {"builder": "api"}),
        ("truthy string verdict", {"passed": "true"}),
        ("missing config fingerprint", {"config_sha256": None}),
        ("invalid round", {"round": True}),
    ):
        cases.append((label, {**deepcopy(good), **changes}, False))
    for label, changes in (
        ("nonzero exit with claimed pass", {"exit": 1}),
        ("boolean exit", {"exit": False}),
        ("truthy result", {"passed": "true"}),
        ("missing command", {"command": ""}),
    ):
        bad = deepcopy(good)
        bad["results"][0].update(changes)
        cases.append((label, bad, False))
    return cases


def evaluate(verifier=None):
    verifier = verifier or (lambda gate: not factory.gate_problems(gate, "eval-integrity", "03-coding"))
    rows = [{"case": name, "expected": expected, "accepted": bool(verifier(gate))}
            for name, gate, expected in fixtures()]
    negative = [r for r in rows if not r["expected"]]
    positive = [r for r in rows if r["expected"]]
    return {"cases": rows, "negative_controls": len(negative), "positive_controls": len(positive),
            "false_green": sum(r["accepted"] for r in negative),
            "false_red": sum(not r["accepted"] for r in positive)}


def render(result):
    return ("## Gate integrity — labelled negative and positive controls\n\n"
            f"Invalid records accepted: **{result['false_green']}/{result['negative_controls']}**. "
            f"Valid records rejected: **{result['false_red']}/{result['positive_controls']}**.\n\n"
            "Checks cover missing tests/results, identity mismatch, contradictory exit codes, "
            "truthy strings, duplicate commands and missing policy fingerprints. These are "
            "deterministic verifier fixtures, not production false-green rates, live model "
            "evaluations, or proof of OS isolation. Regression tests also exercise the command "
            "runner, SDK tools, evidence resolver and both execution paths.\n")
