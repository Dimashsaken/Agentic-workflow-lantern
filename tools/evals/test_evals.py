"""The factory's evals (D20): scorers with known answers, the data build, the replay
path with a fake model, the report, and the PR rule.

    ../azure-runner/.venv/Scripts/python test_evals.py      (no database, no model; real git for check_pr)

Why these tests exist: the evals are what lets a prompt or gate change be judged by a
number instead of a feeling. A scorer that drifts silently, or a PR rule that can be
satisfied by editing REPORT.md by hand, would turn the rule back into ceremony.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "azure-runner"))

import build  # noqa: E402
import check_pr  # noqa: E402
import replay  # noqa: E402
import report  # noqa: E402
import scorers  # noqa: E402

STORY_IDS = ["AC-1", "AC-2", "AC-3"]
PLAN_FULL = {"tasks": [{"id": 1, "criteria": ["AC-1", "AC-2"]}],
             "deferred_criteria": [{"id": "AC-3", "reason": "needs PostHog"}], "write_scope": ["src/**"]}
PLAN_HOLE = {"tasks": [{"id": 1, "criteria": ["AC-1"]}], "deferred_criteria": [{"id": "AC-3", "reason": ""}]}

BUGS_MD_CLEAN = "# Bugs\n\nNo sev-1/sev-2/sev-3 entries. Zero open product bugs.\n"
BUGS_MD_OPEN = """# Bugs — run

### QA-1 — Export button does nothing on AC-2 list
- **Severity:** sev-2
- **Repro:** click export

### QA-2 — Tooltip typo
- **Severity:** sev-4

### QA-3 — Old crash
- **Severity:** sev-1
- **Status:** Resolved in attempt 2
"""
VALIDATION_PASS = {"verdict": "pass", "criteria": [{"id": "AC-1", "status": "covered"}, {"id": "AC-2", "status": "covered"}]}
VALIDATION_FAIL = {"verdict": "fail", "criteria": [{"id": "AC-1", "status": "covered"}, {"id": "AC-2", "status": "missing"}]}


class Scorers(unittest.TestCase):
    def test_plan_coverage_counts_planned_and_reasoned_deferrals(self):
        r = scorers.plan_coverage(STORY_IDS, PLAN_FULL)
        self.assertEqual((r["planned"], r["deferred"], r["uncovered"], r["score"]), (2, 1, [], 1.0))
        r = scorers.plan_coverage(STORY_IDS, PLAN_HOLE)
        self.assertEqual((r["planned"], r["deferred"], r["uncovered"]), (1, 0, ["AC-2", "AC-3"]))
        self.assertAlmostEqual(r["score"], 0.333, places=3)
        self.assertIsNone(scorers.plan_coverage([], PLAN_FULL)["score"])
        self.assertEqual(scorers.plan_coverage(STORY_IDS, None)["score"], 0.0)

    def test_bugs_md_parsing(self):
        qa = scorers.parse_bugs_md(BUGS_MD_OPEN)
        self.assertEqual([b["id"] for b in qa["bugs"]], ["QA-1", "QA-2", "QA-3"])
        self.assertEqual(qa["bugs"][0]["severity"], "sev-2")
        self.assertEqual(qa["bugs"][0]["criteria"], ["AC-2"])
        self.assertTrue(qa["bugs"][0]["open"])
        self.assertFalse(qa["bugs"][2]["open"])                  # resolved sev-1 is not open
        self.assertEqual(qa["open_sev12"], 1)
        clean = scorers.parse_bugs_md(BUGS_MD_CLEAN)
        self.assertEqual((clean["open_sev12"], clean["bugs"], clean["declares_none"]), (0, [], True))

    def test_validator_agreement(self):
        clean, open_ = scorers.parse_bugs_md(BUGS_MD_CLEAN), scorers.parse_bugs_md(BUGS_MD_OPEN)
        self.assertTrue(scorers.validator_agreement(VALIDATION_PASS, clean)["agree"])
        r = scorers.validator_agreement(VALIDATION_PASS, open_)
        self.assertFalse(r["agree"])
        self.assertEqual(r["criterion_conflicts"], ["AC-2"])     # covered by the validator, broken per QA
        r = scorers.validator_agreement(VALIDATION_FAIL, open_)
        self.assertTrue(r["agree"])                               # both say the branch is not done
        self.assertFalse(scorers.validator_agreement(VALIDATION_FAIL, clean)["agree"])

    def test_classification_accuracy_with_known_answers(self):
        rows = [{"run_id": "a", "predicted": "small", "truth": "small"},
                {"run_id": "b", "predicted": "small", "truth": "large"},
                {"run_id": "c", "predicted": "trivial", "truth": "trivial"},
                {"run_id": "d", "predicted": "needs-human", "truth": "small"},
                {"run_id": "e", "predicted": "large", "truth": None}]
        r = scorers.classification_accuracy(rows)
        self.assertEqual((r["n"], r["correct"], r["unscored"]), (3, 2, 2))
        self.assertAlmostEqual(r["accuracy"], 0.667, places=3)
        self.assertEqual(r["confusion"]["small"], {"small": 1, "large": 1})
        self.assertEqual(r["misses"], [{"run_id": "b", "predicted": "small", "truth": "large"}])
        self.assertIsNone(scorers.classification_accuracy([])["accuracy"])

    def test_repro_rate(self):
        r = scorers.repro_rate([{"run_id": "a", "reproduced": True}, {"run_id": "b", "reproduced": False},
                                {"run_id": "c", "reproduced": None}])
        self.assertEqual((r["n"], r["reproduced"], r["rate"], r["not_reproduced"]), (2, 1, 0.5, ["b"]))


def make_runs(root: Path) -> None:
    """Two feature runs and two bug runs, enough for every jsonl file."""
    def j(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def t(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    feat = root / "feat-20260901-export"
    t(feat / "brief.md", "# Feature Brief: Export\n\n## Problem\n\nexports\n")
    j(feat / "00-story" / "story.json", {"kind": "story", "title": "Export",
                                         "acceptance_criteria": [{"id": i, "text": "x"} for i in STORY_IDS]})
    j(feat / "02-pre-coding" / "plan.json", PLAN_FULL)
    j(feat / "05-post-coding" / "validation.json", VALIDATION_PASS)
    t(feat / "04-qa-dev" / "bugs.md", BUGS_MD_CLEAN)
    feat2 = root / "feat-20260902-half"
    t(feat2 / "brief.md", "# Feature Brief: Half\n")
    j(feat2 / "00-story" / "story.json", {"kind": "story", "title": "Half",
                                          "acceptance_criteria": [{"id": i, "text": "x"} for i in STORY_IDS]})
    j(feat2 / "02-pre-coding" / "plan.json", PLAN_HOLE)
    j(feat2 / "05-post-coding" / "validation.json", VALIDATION_PASS)
    t(feat2 / "04-qa-dev" / "bugs.md", BUGS_MD_OPEN)
    for slug, cls, lines, reproduced in (("small-ok", "small", 20, True), ("small-big", "small", 200, False)):
        bug = root / f"bug-20260903-{slug}"
        t(bug / "brief.md", f"# Bug Report: {slug}\n")
        t(bug / "intake" / "feedback.md", "<!-- UNTRUSTED -->\n# UNTRUSTED\n\n---\n\nexport breaks on 500 rows\n")
        j(bug / "01-triage" / "triage.json", {"kind": "triage", "classification": cls})
        j(bug / "02-repro" / "repro.json", {"kind": "repro", "reproduced": reproduced})
        j(bug / "03-coding" / "handoff.json", {"diffstat": f" 2 files changed, {lines} insertions(+)"})


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="evals-"))
        self.runs = self.tmp / "runs"
        self.data = self.tmp / "data"
        make_runs(self.runs)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_freezes_every_run_into_jsonl(self):
        counts = build.build(self.runs, self.data)
        self.assertEqual(counts, {"briefs": 4, "stories": 2, "plans": 2, "validations": 2, "repros": 2})
        repros = build.load(self.data, "repros")
        by_id = {r["run_id"]: r for r in repros}
        self.assertEqual(by_id["bug-20260903-small-ok"]["truth"], "small")
        self.assertEqual(by_id["bug-20260903-small-big"]["truth"], "large")
        self.assertEqual(by_id["bug-20260903-small-ok"]["feedback"], "export breaks on 500 rows")
        self.assertEqual(build.load(self.data, "validations")[1]["qa"]["open_sev12"], 1)
        self.assertEqual(build.load(self.data, "briefs")[0]["kind"], "bug")   # sorted: bug-… before feat-…
        first = (self.data / "repros.jsonl").read_bytes()
        build.build(self.runs, self.data)
        self.assertEqual(first, (self.data / "repros.jsonl").read_bytes())   # deterministic

    def test_frozen_suites_score_the_fixture_as_expected(self):
        build.build(self.runs, self.data)
        plan = replay.run_suite("plan", self.data)
        self.assertEqual((plan["mode"], plan["n_inputs"], plan["summary"]["full_coverage"]), ("frozen", 2, 1))
        self.assertAlmostEqual(plan["summary"]["mean_coverage"], 0.667, places=2)
        val = replay.run_suite("validate", self.data)
        self.assertEqual(val["summary"]["agreement"], 0.5)
        tri = replay.run_suite("triage", self.data)
        self.assertEqual((tri["summary"]["n"], tri["summary"]["correct"], tri["summary"]["accuracy"]), (2, 1, 0.5))
        rep = replay.run_suite("repro", self.data)
        self.assertEqual((rep["summary"]["n"], rep["summary"]["rate"]), (2, 0.5))
        with self.assertRaises(ValueError):
            replay.run_suite("nope", self.data)

    def test_live_replay_uses_the_injected_model_and_scores_its_output(self):
        build.build(self.runs, self.data)
        prompts = []

        def fake_model(role, prompt):
            prompts.append((role, prompt))
            if role == "debug":
                return 'thinking…\n```json\n{"kind": "triage", "classification": "large"}\n```'
            if role == "pre-coding":
                return json.dumps({"kind": "plan", "tasks": [{"id": 1, "criteria": STORY_IDS}], "write_scope": ["x"]})
            return json.dumps(VALIDATION_FAIL)

        tri = replay.run_suite("triage", self.data, live=True, model_call=fake_model)
        self.assertEqual(tri["mode"], "live")
        self.assertEqual(tri["summary"]["accuracy"], 0.5)          # large/large right, large/small wrong
        self.assertTrue(all(r == "debug" for r, _ in prompts))
        self.assertIn("UNTRUSTED", prompts[0][1])
        self.assertIn("export breaks on 500 rows", prompts[0][1])
        plan = replay.run_suite("plan", self.data, live=True, model_call=fake_model)
        self.assertEqual(plan["summary"]["mean_coverage"], 1.0)
        val = replay.run_suite("validate", self.data, live=True, model_call=fake_model)
        self.assertEqual(val["summary"]["agreement"], 0.5)
        with self.assertRaises(ValueError):
            replay.run_suite("repro", self.data, live=True, model_call=fake_model)

    def test_parse_json_object(self):
        self.assertEqual(replay.parse_json_object('x {"a": 1} y'), {"a": 1})
        self.assertEqual(replay.parse_json_object('```json\n{"a": [1]}\n```'), {"a": [1]})
        self.assertIsNone(replay.parse_json_object("no json here"))
        self.assertIsNone(replay.parse_json_object("[1, 2]"))

    def test_report_renders_every_suite_and_carries_the_fingerprint(self):
        build.build(self.runs, self.data)
        results = {s: replay.run_suite(s, self.data) for s in replay.SUITES}
        (self.tmp / "agents" / "debug").mkdir(parents=True)
        (self.tmp / "agents" / "debug" / "charter.md").write_text("# c\n", encoding="utf-8")
        path = report.write_report(self.tmp, self.data, results)
        text = path.read_text(encoding="utf-8")
        self.assertEqual(path.name, "REPORT.md")
        self.assertEqual(check_pr.report_fingerprint(text), check_pr.fingerprint(self.tmp))
        for needle in ("| plan | frozen | 2 |", "| triage | frozen | 2 |", "feat-20260902-half", "AC-2, AC-3",
                       "bug-20260903-small-big", "predicted small, was large", "1 of 2 reproduced"):
            self.assertIn(needle, text)
        self.assertTrue((self.data / "results.json").is_file())


def git(*args, cwd: Path) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


ORCH_V1 = '''import os

PHASE_NOTES = {"03-coding": "note"}


def build_instructions(role, run_id, stage):
    return "a" + role


def helper():
    return 1


async def check_postconditions(conn, role, run_id, stage, execution_key):
    return []
'''
ORCH_V2 = ORCH_V1.replace('return "a" + role', 'return "b" + role')           # prompt builder changed
ORCH_V3 = ORCH_V1.replace("return 1", "return 2")                              # only the helper changed


class PrRule(unittest.TestCase):
    def test_pure_rule(self):
        self.assertEqual(check_pr.evaluate(["docs/x.md", "tools/mission-control/app.py"], [], False, None), [])
        probs = check_pr.evaluate(["agents/debug/skills.md"], [], False, None)
        self.assertEqual(len(probs), 1)
        self.assertIn("tools/evals/REPORT.md", probs[0])
        self.assertEqual(check_pr.evaluate(["agents/debug/memory.md"], [], False, None), [])   # rendered view
        self.assertEqual(check_pr.evaluate(["agents/_template/charter.md"], [], False, None), [])
        self.assertEqual(check_pr.evaluate(["tools/azure-runner/factory.py"], [], True, True), [])
        self.assertIn("not generated against", check_pr.evaluate(["tools/azure-runner/factory.py"], [], True, False)[0])
        self.assertIn("build_instructions", check_pr.evaluate([], ["build_instructions"], False, None)[0])

    def test_orchestrator_units_by_name(self):
        self.assertEqual(check_pr.touched_units(ORCH_V1, ORCH_V2), ["build_instructions"])
        self.assertEqual(check_pr.touched_units(ORCH_V1, ORCH_V3), [])
        self.assertEqual(check_pr.touched_units(ORCH_V1, ORCH_V1.replace('"note"', '"other"')), ["PHASE_NOTES"])
        self.assertEqual(check_pr.touched_units(None, ORCH_V1), ["PHASE_NOTES", "build_instructions", "check_postconditions"])

    def test_on_real_diffs(self):
        tmp = Path(tempfile.mkdtemp(prefix="checkpr-"))
        try:
            git("init", "-q", "-b", "main", cwd=tmp)
            git("config", "user.name", "t", cwd=tmp)
            git("config", "user.email", "t@example.invalid", cwd=tmp)
            (tmp / "agents" / "debug").mkdir(parents=True)
            (tmp / "agents" / "debug" / "skills.md").write_text("# skills v1\n", encoding="utf-8")
            (tmp / "tools" / "azure-runner").mkdir(parents=True)
            (tmp / "tools" / "azure-runner" / "orchestrator.py").write_text(ORCH_V1, encoding="utf-8")
            (tmp / "tools" / "evals").mkdir(parents=True)
            (tmp / "tools" / "evals" / "REPORT.md").write_text(
                f"# r\n<!-- {check_pr.FINGERPRINT_MARK} {check_pr.fingerprint(tmp)} -->\n", encoding="utf-8")
            (tmp / "README.md").write_text("hi\n", encoding="utf-8")
            git("add", "-A", cwd=tmp)
            git("commit", "-q", "-m", "seed", cwd=tmp)
            git("checkout", "-q", "-b", "feat/x", cwd=tmp)

            # 1. an unrelated change passes
            (tmp / "README.md").write_text("hello\n", encoding="utf-8")
            git("commit", "-q", "-am", "docs", cwd=tmp)
            self.assertEqual(check_pr.check(tmp, "main")[0], 0)

            # 2. a prompt change without REPORT.md blocks (committed AND uncommitted)
            (tmp / "agents" / "debug" / "skills.md").write_text("# skills v2\n", encoding="utf-8")
            code, msg = check_pr.check(tmp, "main")
            self.assertEqual(code, 1)
            self.assertIn("agents/debug/skills.md", msg)
            git("commit", "-q", "-am", "prompt", cwd=tmp)
            self.assertEqual(check_pr.check(tmp, "main")[0], 1)

            # 3. REPORT.md edited by hand (stale fingerprint) still blocks
            (tmp / "tools" / "evals" / "REPORT.md").write_text("# r\n<!-- lantern-evals-fingerprint: " + "0" * 64 + " -->\n",
                                                                encoding="utf-8")
            code, msg = check_pr.check(tmp, "main")
            self.assertEqual(code, 1)
            self.assertIn("not generated against", msg)

            # 4. a regenerated REPORT.md passes
            (tmp / "tools" / "evals" / "REPORT.md").write_text(
                f"# r\n<!-- {check_pr.FINGERPRINT_MARK} {check_pr.fingerprint(tmp)} -->\n", encoding="utf-8")
            git("commit", "-q", "-am", "report", cwd=tmp)
            code, msg = check_pr.check(tmp, "main")
            self.assertEqual(code, 0, msg)

            # 5. an orchestrator helper change is not watched; a prompt builder change is
            (tmp / "tools" / "azure-runner" / "orchestrator.py").write_text(ORCH_V3, encoding="utf-8")
            self.assertEqual(check_pr.check(tmp, "main")[0], 0)
            (tmp / "tools" / "azure-runner" / "orchestrator.py").write_text(ORCH_V2, encoding="utf-8")
            code, msg = check_pr.check(tmp, "main")
            self.assertEqual(code, 1)
            self.assertIn("build_instructions", msg)

            # 6. no resolvable base = the rule cannot apply, never a block
            self.assertEqual(check_pr.check(tmp, "no-such-branch")[0], 1)   # main still resolves
            git("branch", "-m", "main", "trunk", cwd=tmp)
            self.assertEqual(check_pr.check(tmp, None)[0], 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class IntegrityControls(unittest.TestCase):
    def test_verifier_accepts_positive_and_rejects_negative_controls(self):
        import integrity
        result = integrity.evaluate()
        self.assertEqual(result["false_green"], 0)
        self.assertEqual(result["false_red"], 0)
        self.assertGreater(result["negative_controls"], 10)
        self.assertGreater(result["positive_controls"], 0)

    def test_unconditional_acceptance_and_refusal_are_both_detected(self):
        import integrity
        self.assertGreater(integrity.evaluate(lambda _: True)["false_green"], 0)
        self.assertGreater(integrity.evaluate(lambda _: False)["false_red"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
