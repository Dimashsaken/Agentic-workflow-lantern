"""Software-factory mechanics (D17): envelopes, write scope, quality gate, fix loop.

    .venv/Scripts/python test_factory.py      (no database, no Azure, real git + bash)

Why these tests exist: every function in factory.py is a place where an agent's claim is
replaced by something the harness checks. If a check regresses, the pipeline goes back to
trusting reports — the failure mode the whole design is built against.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factory as f  # noqa: E402

RUN = "feat-20260908-factory-proof"


def git(*args, cwd: Path) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def product_repo(tmp: Path) -> Path:
    root = tmp / "product"
    root.mkdir()
    git("init", "-q", "-b", "main", cwd=root)
    git("config", "user.name", "t", cwd=root)
    git("config", "user.email", "t@example.invalid", cwd=root)
    (root / "src" / "api").mkdir(parents=True)
    (root / "src" / "api" / "items.py").write_text("def items():\n    return []\n", encoding="utf-8")
    (root / "src" / "ui").mkdir()
    (root / "src" / "ui" / "list.tsx").write_text("export const List = () => null;\n", encoding="utf-8")
    (root / "README.md").write_text("# product\n", encoding="utf-8")
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "seed", cwd=root)
    return root


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_md(path: Path, text: str = "# twin\n\nsome prose\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


STORY = {
    "kind": "story", "run_id": RUN, "title": "Saved items",
    "user_story": "As a user I want to save items so that I can find them later.",
    "acceptance_criteria": [
        {"id": "AC-1", "text": "A signed-in user can save an item from the list.", "edge_cases": ["double click saves once"]},
        {"id": "AC-2", "text": "Saved items appear on /saved in save order.", "edge_cases": []},
        {"id": "AC-3", "text": "Unsaving removes the item within one second.", "edge_cases": ["offline"]},
    ],
    "non_goals": ["sharing saved lists"], "open_questions": [],
}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="factory-"))
        self.repo_backup = f.REPO
        f.REPO = self.tmp / "lantern"
        (f.REPO / "workflow" / "runs" / RUN).mkdir(parents=True)
        self.rd = f.REPO / "workflow" / "runs" / RUN
        self.product = product_repo(self.tmp)

    def tearDown(self):
        f.REPO = self.repo_backup
        shutil.rmtree(self.tmp, ignore_errors=True)

    def story(self, data=STORY):
        write_json(self.rd / "00-story" / "story.json", data)
        write_md(self.rd / "00-story" / "story.md")


class Envelopes(Base):
    def test_unknown_stage_has_no_envelope(self):
        self.assertEqual(f.check_envelope(RUN, "04-qa-dev"), [])

    def test_missing_envelope_and_twin_are_named(self):
        probs = f.check_envelope(RUN, "00-story.write")
        self.assertTrue(any("story.md missing" in p for p in probs))
        self.assertTrue(any("story.json missing" in p for p in probs))

    def test_story_valid(self):
        self.story()
        self.assertEqual(f.check_envelope(RUN, "00-story.write"), [])

    def test_story_rejects_bad_ids_duplicates_and_empty_text(self):
        bad = dict(STORY, acceptance_criteria=[
            {"id": "1", "text": "x", "edge_cases": []},
            {"id": "AC-2", "text": "", "edge_cases": []},
            {"id": "AC-2", "text": "y", "edge_cases": "not a list"}])
        self.story(bad)
        probs = "\n".join(f.check_envelope(RUN, "00-story.write"))
        self.assertIn("must look like AC-1", probs)
        self.assertIn("AC-2: text is required", probs)
        self.assertIn("duplicate acceptance criterion id AC-2", probs)
        self.assertIn("edge_cases must be a list", probs)

    def test_kind_and_run_id_must_match(self):
        self.story(dict(STORY, kind="plan", run_id="other"))
        probs = "\n".join(f.check_envelope(RUN, "00-story.write"))
        self.assertIn("kind must be 'story'", probs)
        self.assertIn("run_id must be", probs)

    def test_research_paths_must_exist_when_checkout_given(self):
        data = {"kind": "research", "run_id": RUN,
                "patterns": [{"path": "src/api/items.py", "note": "handler style"}],
                "similar_features": [{"name": "list", "paths": ["src/ui/list.tsx"]}],
                "risks": [{"risk": "no tests on api", "severity": "medium"}],
                "likely_files": ["src/api/items.py", "src/api/saved.py"],
                "conventions": ["pytest"]}
        write_json(self.rd / "00-story" / "research.json", data)
        write_md(self.rd / "00-story" / "research.md")
        self.assertEqual(f.check_envelope(RUN, "00-story.scout"), [])            # no checkout: skip
        probs = "\n".join(f.check_envelope(RUN, "00-story.scout", self.product))
        self.assertIn("src/api/saved.py", probs)                                  # not in the tree
        self.assertNotIn("src/api/items.py", probs)
        data["likely_files"] = ["product/src/api/items.py"]                     # product/ prefix ok
        write_json(self.rd / "00-story" / "research.json", data)
        self.assertEqual(f.check_envelope(RUN, "00-story.scout", self.product), [])

    def test_research_requires_likely_files_and_risk_shape(self):
        write_json(self.rd / "00-story" / "research.json",
                   {"kind": "research", "run_id": RUN, "patterns": [], "risks": [{"risk": "x", "severity": "huge"}],
                    "likely_files": []})
        write_md(self.rd / "00-story" / "research.md")
        probs = "\n".join(f.check_envelope(RUN, "00-story.scout"))
        self.assertIn("likely_files must list at least one path", probs)
        self.assertIn("severity", probs)

    def plan(self, **over):
        data = {"kind": "plan", "run_id": RUN,
                "tasks": [{"id": 1, "title": "save endpoint", "size": "S", "hitl": False, "criteria": ["AC-1"]},
                          {"id": 2, "title": "saved page", "size": "M", "hitl": False, "criteria": ["AC-2", "AC-3"]}],
                "write_scope": ["src/api/**", "src/ui/**", "tests/**"],
                "schema_changes": False, "hitl_required": False, "deferred_criteria": []}
        data.update(over)
        write_json(self.rd / "02-pre-coding" / "plan.json", data)
        write_md(self.rd / "02-pre-coding" / "task-plan.md")

    def test_plan_valid_with_story_cross_check(self):
        self.story()
        self.plan()
        self.assertEqual(f.check_envelope(RUN, "02-pre-coding"), [])

    def test_plan_without_story_skips_cross_check(self):
        self.plan()
        self.assertEqual(f.check_envelope(RUN, "02-pre-coding"), [])

    def test_plan_must_cover_or_defer_every_criterion(self):
        self.story()
        self.plan(tasks=[{"id": 1, "title": "save endpoint", "hitl": False, "criteria": ["AC-1", "AC-9"]}])
        probs = "\n".join(f.check_envelope(RUN, "02-pre-coding"))
        self.assertIn("criteria the story does not define: AC-9", probs)
        self.assertIn("no task and no deferral reason: AC-2, AC-3", probs)
        self.plan(tasks=[{"id": 1, "title": "save endpoint", "hitl": False, "criteria": ["AC-1", "AC-2"]}],
                  deferred_criteria=[{"id": "AC-3", "reason": "needs the offline queue first"}])
        self.assertEqual(f.check_envelope(RUN, "02-pre-coding"), [])

    def test_plan_requires_write_scope_and_booleans(self):
        self.plan(write_scope=[], schema_changes="no")
        probs = "\n".join(f.check_envelope(RUN, "02-pre-coding"))
        self.assertIn("write_scope must list at least one path glob", probs)
        self.assertIn("schema_changes must be true or false", probs)

    def validation(self, **over):
        data = {"kind": "validation", "run_id": RUN,
                "criteria": [{"id": "AC-1", "status": "covered", "evidence": "src/api/saved.py + tests/test_saved.py; qa session 1 0:12"},
                             {"id": "AC-2", "status": "covered", "evidence": "src/ui/saved.tsx; qa session 1 0:40"},
                             {"id": "AC-3", "status": "covered", "evidence": "qa session 2 0:05"}],
                "fix_now": [], "verdict": "pass"}
        data.update(over)
        write_json(self.rd / "05-post-coding" / "validation.json", data)
        write_md(self.rd / "05-post-coding" / "validation.md")

    def test_validation_pass(self):
        self.story()
        self.validation()
        self.assertEqual(f.check_envelope(RUN, "05-post-coding.validate"), [])

    def test_validation_every_criterion_once_with_evidence(self):
        self.story()
        self.validation(criteria=[{"id": "AC-1", "status": "covered", "evidence": ""},
                                  {"id": "AC-1", "status": "covered", "evidence": "x"},
                                  {"id": "AC-7", "status": "covered", "evidence": "x"}])
        probs = "\n".join(f.check_envelope(RUN, "05-post-coding.validate"))
        self.assertIn("AC-1: evidence is required", probs)
        self.assertIn("duplicate criterion AC-1", probs)
        self.assertIn("criteria not validated: AC-2, AC-3", probs)
        self.assertIn("criteria the story does not define: AC-7", probs)

    def test_validation_verdict_is_computed_not_chosen(self):
        self.story()
        crit = [{"id": "AC-1", "status": "covered", "evidence": "x"},
                {"id": "AC-2", "status": "missing", "evidence": "no /saved route in the diff"},
                {"id": "AC-3", "status": "covered", "evidence": "x"}]
        self.validation(criteria=crit, verdict="pass")
        probs = "\n".join(f.check_envelope(RUN, "05-post-coding.validate"))
        self.assertIn("verdict says 'pass' but the criteria say 'fail'", probs)
        self.validation(criteria=crit, verdict="fail",
                        fix_now=[{"id": "F-1", "title": "add /saved route", "criterion": "AC-2"}])
        probs = "\n".join(f.check_envelope(RUN, "05-post-coding.validate"))
        self.assertNotIn("verdict says", probs)
        self.assertIn("validation verdict FAIL", probs)
        self.assertIn("AC-2=missing", probs)
        self.assertIn(f"pipeline.py rework {RUN} --to 03-coding", probs)


class WriteScope(Base):
    def test_glob_semantics(self):
        self.assertTrue(f.path_in_scope("src/api/a/b.py", ["src/api/**"]))
        self.assertFalse(f.path_in_scope("src/ui/x.tsx", ["src/api/**"]))
        self.assertTrue(f.path_in_scope("a.py", ["*.py"]))
        self.assertFalse(f.path_in_scope("d/a.py", ["*.py"]))
        self.assertTrue(f.path_in_scope("x/y/test_a.py", ["**/test_*.py"]))
        self.assertTrue(f.path_in_scope("test_a.py", ["**/test_*.py"]))
        self.assertTrue(f.path_in_scope("docs/guide/a.md", ["docs/"]))
        self.assertTrue(f.path_in_scope("src\\api\\w.py", ["src/api/**"]))     # windows separators
        self.assertFalse(f.path_in_scope("srcx/api/w.py", ["src/api/**"]))

    def test_check_write_scope_reads_the_plan(self):
        self.assertEqual(f.check_write_scope(RUN, ["anything/at/all.py"]), [])   # no plan.json
        write_json(self.rd / "02-pre-coding" / "plan.json",
                   {"kind": "plan", "run_id": RUN, "tasks": [], "write_scope": ["src/api/**"],
                    "schema_changes": False, "hitl_required": False})
        self.assertEqual(f.check_write_scope(RUN, ["src/api/saved.py"]), [])
        probs = f.check_write_scope(RUN, ["src/api/saved.py", "src/ui/list.tsx", "README.md"])
        self.assertEqual(len(probs), 1)
        self.assertIn("2 changed path(s) fall outside", probs[0])
        self.assertIn("src/ui/list.tsx", probs[0])
        self.assertIn("plan.json", probs[0])


class QualityGate(Base):
    def toml(self, body: str) -> None:
        (self.product / "lantern.toml").write_text(body, encoding="utf-8")

    def test_no_config_means_green_with_nothing_configured(self):
        gate = f.run_quality_gate(RUN, "03-coding", self.product, f"{RUN}:03-coding:1", 0)
        self.assertTrue(gate["passed"])
        self.assertEqual(gate["configured"], [])
        self.assertTrue((self.rd / "03-coding" / "gate.json").is_file())
        self.assertIn("No quality commands are configured", (self.rd / "03-coding" / "gate.md").read_text(encoding="utf-8"))

    def test_failures_only_reach_the_brief(self):
        self.toml('[quality]\ntest = "echo all good"\nlint = "echo boom >&2; exit 3"\n')
        gate = f.run_quality_gate(RUN, "03-coding", self.product, f"{RUN}:03-coding:1", 0)
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["configured"], ["test", "lint"])
        self.assertEqual([r["name"] for r in gate["results"] if not r["passed"]], ["lint"])
        brief = f.gate_failure_brief(gate)
        self.assertIn("boom", brief)
        self.assertNotIn("all good", brief)
        md = (self.rd / "03-coding" / "gate.md").read_text(encoding="utf-8")
        self.assertIn("RED", md)
        self.assertIn("## lint — FAILED", md)
        prompt = f.fix_prompt(gate, 1, 3)
        self.assertIn("fix round 1 of 3", prompt)
        self.assertIn("boom", prompt)

    def test_harness_interpreter_is_passed_through(self):
        self.toml('[quality]\ntest = "$LANTERN_PYTHON -c \\"import sys; print(sys.version_info[0])\\""\n')
        gate = f.run_quality_gate(RUN, "03-coding", self.product, "k", 0)
        self.assertTrue(gate["passed"], gate["results"])
        self.assertIn("3", gate["results"][0]["output_tail"])

    def test_timeout_is_a_failure_not_a_hang(self):
        self.toml('[quality]\ntest = "sleep 5"\ntimeout_s = 1\n')
        gate = f.run_quality_gate(RUN, "03-coding", self.product, "k", 0)
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["results"][0]["exit"], 124)

    def test_bad_toml_is_a_red_gate(self):
        self.toml("[quality\ntest = ")
        gate = f.run_quality_gate(RUN, "03-coding", self.product, "k", 0)
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["results"][-1]["name"], "config")

    def test_write_scope_is_part_of_the_gate(self):
        write_json(self.rd / "02-pre-coding" / "plan.json",
                   {"kind": "plan", "run_id": RUN, "tasks": [], "write_scope": ["src/api/**"],
                    "schema_changes": False, "hitl_required": False})
        start = git("rev-parse", "HEAD", cwd=self.product)
        (self.product / "src" / "api" / "saved.py").write_text("x = 1\n", encoding="utf-8")
        git("add", "-A", cwd=self.product)
        git("commit", "-q", "-m", "in scope", cwd=self.product)
        gate = f.run_quality_gate(RUN, "03-coding", self.product, "k", 0, since_sha=start)
        self.assertTrue(gate["passed"], gate["results"])
        (self.product / "src" / "ui" / "list.tsx").write_text("changed\n", encoding="utf-8")   # uncommitted, outside
        gate = f.run_quality_gate(RUN, "03-coding", self.product, "k", 1, since_sha=start)
        self.assertFalse(gate["passed"])
        scope = [r for r in gate["results"] if r["name"] == "write-scope"][0]
        self.assertIn("src/ui/list.tsx", scope["output_tail"])

    def test_postcondition_reads_only_this_executions_gate(self):
        self.assertEqual(f.check_quality_gate(RUN, "03-coding", "k1"), [])       # absent: degrade
        self.toml('[quality]\ntest = "exit 1"\n')
        f.run_quality_gate(RUN, "03-coding", self.product, "k1", 2)
        probs = f.check_quality_gate(RUN, "03-coding", "k1")
        self.assertTrue(probs and "RED after 2 fix round(s): test" in probs[0])
        self.assertTrue("belongs to execution" in f.check_quality_gate(RUN, "03-coding", "k2")[0])
        self.toml('[quality]\ntest = "exit 0"\n')
        f.run_quality_gate(RUN, "03-coding", self.product, "k1", 0)
        self.assertEqual(f.check_quality_gate(RUN, "03-coding", "k1"), [])

    def test_gate_note_tells_the_builder_up_front(self):
        self.toml('[quality]\ntest = "pytest -q"\n')
        write_json(self.rd / "02-pre-coding" / "plan.json",
                   {"kind": "plan", "run_id": RUN, "tasks": [], "write_scope": ["src/**"],
                    "schema_changes": False, "hitl_required": False})
        note = f.coding_gate_note(RUN, self.product)
        self.assertIn("`pytest -q`", note)
        self.assertIn("`src/**`", note)
        self.assertIn("no `lantern.toml [quality]`", f.coding_gate_note(RUN, self.tmp / "nowhere"))


class FixLoop(Base):
    def test_failures_go_back_until_green_then_stop(self):
        (self.product / "lantern.toml").write_text(
            '[quality]\ntest = "test -f FIXED || (echo marker missing; exit 1)"\n', encoding="utf-8")
        prompts = []

        async def run_turn(text):
            prompts.append(text)
            if text.startswith("# Quality gate"):        # the "agent" fixes it on the first fix turn
                (self.product / "FIXED").write_text("", encoding="utf-8")
            return {"turn": len(prompts)}

        results, gate = asyncio.run(f.coding_turns(
            run_turn, "Begin", run_id=RUN, stage="03-coding", root=self.product,
            execution_key="k", max_rounds=3))
        self.assertEqual(len(results), 2)
        self.assertTrue(gate["passed"])
        self.assertEqual(gate["round"], 1)
        self.assertEqual(prompts[0], "Begin")
        self.assertIn("fix round 1 of 3", prompts[1])
        self.assertIn("marker missing", prompts[1])

    def test_bounded_then_honest_red(self):
        (self.product / "lantern.toml").write_text('[quality]\ntest = "exit 1"\n', encoding="utf-8")
        n = 0

        async def run_turn(text):
            nonlocal n
            n += 1
            return {}

        results, gate = asyncio.run(f.coding_turns(
            run_turn, "Begin", run_id=RUN, stage="03-coding", root=self.product,
            execution_key="k", max_rounds=2))
        self.assertEqual(n, 3)                          # build + 2 fix rounds
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["round"], 2)
        self.assertTrue(f.check_quality_gate(RUN, "03-coding", "k"))

    def test_zero_rounds_means_one_turn(self):
        (self.product / "lantern.toml").write_text('[quality]\ntest = "exit 1"\n', encoding="utf-8")
        calls = []

        async def run_turn(text):
            calls.append(text)
            return {}

        results, gate = asyncio.run(f.coding_turns(
            run_turn, "Begin", run_id=RUN, stage="03-coding", root=self.product,
            execution_key="k", max_rounds=0))
        self.assertEqual(calls, ["Begin"])
        self.assertFalse(gate["passed"])

    def test_fix_rounds_env(self):
        with unittest.mock.patch.dict(os.environ, {"LANTERN_FIX_ROUNDS": "5"}):
            self.assertEqual(f.fix_rounds(), 5)
        with unittest.mock.patch.dict(os.environ, {"LANTERN_FIX_ROUNDS": "nope"}):
            self.assertEqual(f.fix_rounds(), f.FIX_ROUNDS_DEFAULT)


class RateLimitError(Exception):
    """Same class NAME openai raises; classification matches names, never imports."""


class FakeAPIStatusError(Exception):
    def __init__(self, status_code):
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class MaxTurnsExceeded(Exception):
    """Same name the Agents SDK uses; classification must keep it terminal."""


class Retry(unittest.TestCase):
    def test_transport_names_are_retryable(self):
        for name in ("RateLimitError", "APIConnectionError", "APITimeoutError"):
            exc = type(name, (Exception,), {})()
            self.assertEqual(f.classify_error(exc), "retryable", name)

    def test_unknown_errors_are_terminal(self):
        self.assertEqual(f.classify_error(ValueError("bad json")), "terminal")

    def test_status_code_outranks_the_name(self):
        self.assertEqual(f.classify_error(FakeAPIStatusError(429)), "retryable")
        self.assertEqual(f.classify_error(FakeAPIStatusError(400)), "terminal")
        self.assertEqual(f.classify_error(FakeAPIStatusError(503)), "retryable")

    def test_agent_budget_and_refusals_stay_terminal(self):
        # A 429 is the deployment saying "later"; MaxTurnsExceeded is the agent saying
        # "I could not finish". Retrying the second one just buys the same answer twice.
        self.assertEqual(f.classify_error(MaxTurnsExceeded()), "terminal")

    def test_retries_a_throttle_then_succeeds(self):
        calls, slept = [], []

        async def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise RateLimitError("429")
            return "done"

        async def fake_sleep(d):
            slept.append(d)

        out = asyncio.run(f.with_retry(flaky, attempts=3, base_delay=1.0,
                                       sleep=fake_sleep, jitter=lambda: 1.0))
        self.assertEqual(out, "done")
        self.assertEqual(len(calls), 3)
        self.assertEqual(slept, [1.0, 2.0])          # exponential, jitter pinned to max

    def test_gives_up_and_reraises_the_last_error(self):
        async def always():
            raise RateLimitError("429")

        async def fake_sleep(d):
            pass

        with self.assertRaises(RateLimitError):
            asyncio.run(f.with_retry(always, attempts=2, sleep=fake_sleep,
                                     jitter=lambda: 0.0))

    def test_terminal_errors_are_not_retried(self):
        calls = []

        async def bad():
            calls.append(1)
            raise ValueError("malformed envelope")

        with self.assertRaises(ValueError):
            asyncio.run(f.with_retry(bad, attempts=5, sleep=None, jitter=lambda: 0.0))
        self.assertEqual(len(calls), 1)

    def test_backoff_is_capped(self):
        slept = []

        async def always():
            raise RateLimitError("429")

        async def fake_sleep(d):
            slept.append(d)

        with self.assertRaises(RateLimitError):
            asyncio.run(f.with_retry(always, attempts=8, base_delay=10.0,
                                     sleep=fake_sleep, jitter=lambda: 1.0))
        self.assertTrue(max(slept) <= f.MODEL_RETRY_CAP_S, slept)

    def test_retries_env(self):
        with unittest.mock.patch.dict(os.environ, {"LANTERN_MODEL_RETRIES": "7"}):
            self.assertEqual(f.model_retries(), 7)
        with unittest.mock.patch.dict(os.environ, {"LANTERN_MODEL_RETRIES": "nope"}):
            self.assertEqual(f.model_retries(), f.MODEL_RETRIES_DEFAULT)


class Checkpoints(Base):
    def test_snapshot_includes_untracked_work_and_restores_it(self):
        # The whole point: a builder's NEW file is untracked until it commits, and
        # `git stash create` would have silently omitted it.
        (self.product / "src" / "api" / "new_feature.py").write_text("x = 1\n", encoding="utf-8")
        (self.product / "README.md").write_text("# product\nedited\n", encoding="utf-8")
        sha = f.checkpoint_tree(self.product, "run:03-coding:1", 0)
        self.assertTrue(sha)

        (self.product / "src" / "api" / "new_feature.py").write_text("BROKEN\n", encoding="utf-8")
        (self.product / "README.md").write_text("# product\n", encoding="utf-8")
        self.assertTrue(f.restore_checkpoint(self.product, sha))

        self.assertEqual((self.product / "src" / "api" / "new_feature.py").read_text(encoding="utf-8"), "x = 1\n")
        self.assertEqual((self.product / "README.md").read_text(encoding="utf-8"), "# product\nedited\n")

    def test_checkpoint_leaves_head_and_the_real_index_alone(self):
        head_before = git("rev-parse", "HEAD", cwd=self.product)
        status_before = git("status", "--porcelain", cwd=self.product)
        (self.product / "untracked.txt").write_text("hi\n", encoding="utf-8")
        f.checkpoint_tree(self.product, "k", 0)
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.product), head_before)
        # still untracked — the snapshot did not stage anything on the agent's behalf
        self.assertIn("?? untracked.txt", git("status", "--porcelain", cwd=self.product))
        self.assertNotEqual(status_before, git("status", "--porcelain", cwd=self.product))

    def test_checkpoint_is_reachable_by_ref(self):
        sha = f.checkpoint_tree(self.product, "feat:03-coding:2", 1)
        ref = f.checkpoint_ref("feat:03-coding:2", 1)
        self.assertEqual(git("rev-parse", ref, cwd=self.product), sha)

    def test_ignored_files_stay_out(self):
        (self.product / ".gitignore").write_text("secrets.env\n", encoding="utf-8")
        (self.product / "secrets.env").write_text("KEY=abc\n", encoding="utf-8")
        sha = f.checkpoint_tree(self.product, "k", 0)
        self.assertNotIn("secrets.env", git("ls-tree", "-r", "--name-only", sha, cwd=self.product))

    def test_never_raises_outside_a_repo(self):
        self.assertIsNone(f.checkpoint_tree(self.tmp / "not-a-repo", "k", 0))

    def test_gate_score_orders_green_above_red_and_fewer_failures_above_more(self):
        green = {"passed": True, "results": [{"passed": True}]}
        one_red = {"passed": False, "results": [{"passed": True}, {"passed": False}]}
        two_red = {"passed": False, "results": [{"passed": False}, {"passed": False}]}
        self.assertGreater(f.gate_score(green), f.gate_score(one_red))
        self.assertGreater(f.gate_score(one_red), f.gate_score(two_red))


class CoherenceCollapse(Base):
    """D24: a fix round that makes things worse must cost a round, not the work."""

    def _two_check_product(self):
        (self.product / "lantern.toml").write_text(
            '[quality]\ntest = "test -f GOOD"\nlint = "test -f ALSO_GOOD"\n', encoding="utf-8")

    def test_a_worse_fix_round_does_not_ship(self):
        self._two_check_product()
        turns = []

        async def run_turn(text):
            turns.append(text)
            if len(turns) == 1:
                (self.product / "GOOD").write_text("", encoding="utf-8")   # 1 of 2 green
            else:
                (self.product / "GOOD").unlink()                           # thrash it away
            return {}

        results, gate = asyncio.run(f.coding_turns(
            run_turn, "Begin", run_id=RUN, stage="03-coding", root=self.product,
            execution_key="k", max_rounds=1))

        self.assertEqual(len(turns), 2)
        self.assertFalse(gate["passed"])                 # honest: it never went green
        self.assertEqual(gate.get("restored_from_round"), 0)
        self.assertTrue((self.product / "GOOD").exists(), "round 0's better tree was not restored")
        # gate.json on disk describes the tree that ships, not the one thrown away
        on_disk = json.loads((self.rd / "03-coding" / "gate.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk.get("restored_from_round"), 0)
        self.assertIn("restored from round 0",
                      (self.rd / "03-coding" / "gate.md").read_text(encoding="utf-8"))

    def test_a_better_final_round_ships_unchanged(self):
        self._two_check_product()
        turns = []

        async def run_turn(text):
            turns.append(text)
            (self.product / ("GOOD" if len(turns) == 1 else "ALSO_GOOD")).write_text("", encoding="utf-8")
            return {}

        results, gate = asyncio.run(f.coding_turns(
            run_turn, "Begin", run_id=RUN, stage="03-coding", root=self.product,
            execution_key="k", max_rounds=2))
        self.assertTrue(gate["passed"])
        self.assertIsNone(gate.get("restored_from_round"))

    def test_checkpoints_can_be_switched_off(self):
        self._two_check_product()

        async def run_turn(text):
            (self.product / "GOOD").write_text("", encoding="utf-8")
            return {}

        _, gate = asyncio.run(f.coding_turns(
            run_turn, "Begin", run_id=RUN, stage="03-coding", root=self.product,
            execution_key="k", max_rounds=0, checkpoints=False))
        self.assertIsNone(gate.get("restored_from_round"))
        self.assertEqual(git("for-each-ref", "--count=1", f.CHECKPOINT_NS, cwd=self.product), "")


class Usage(unittest.TestCase):
    def test_merge_sums_the_ledgers(self):
        merged = f.merge_usage([{"requests": 1, "input_tokens": 10, "output_tokens": 2},
                                {"requests": 2, "input_tokens": 5, "cached_input_tokens": 4}, None])
        self.assertEqual(merged, {"requests": 3, "input_tokens": 15, "output_tokens": 2, "cached_input_tokens": 4})


if __name__ == "__main__":
    import unittest.mock  # noqa: F401  (FixLoop.test_fix_rounds_env)
    unittest.main(verbosity=2)
