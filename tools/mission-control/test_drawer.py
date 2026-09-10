"""The execution drawer from a fixture trace (Mission Control v3, D22).

    ..\\..\\tools\\azure-runner\\.venv\\Scripts\\python test_drawer.py

Stdlib only, no database, no model: a temporary run folder gets a trace written by the
REAL factory.write_trace (so the drawer reads exactly what the executors produce), a
report, an envelope, a gate.json and memory rows. Contract under test:
  * the drawer shows the compiled prompt, the kickoff, the tool-call timeline with
    args snippet and result size, the report, the envelope with its validation
    result, gate.md, the memory entries and the ledger numbers;
  * a QA password that was in the running prompt never appears in the drawer;
  * the loop actions follow the pipeline's rules: retry only for a failed run,
    rework-to only to an earlier REWORK_TARGETS stage of a failed/waiting run;
  * an execution without a trace says so honestly instead of showing nothing.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as mc  # noqa: E402
import drawer  # noqa: E402
import factory  # noqa: E402
from fakes import NOW, exec_row, run_row  # noqa: E402

RUN = "feat-20260908-drawer"
PASSWORD = "Qa-Secret-Pw-77"


def call(name, args, cid):
    return SimpleNamespace(type="tool_call_item",
                           raw_item=SimpleNamespace(name=name, arguments=args, call_id=cid))


def output(text, cid):
    return SimpleNamespace(type="tool_call_output_item",
                           raw_item={"call_id": cid, "output": text}, output=text)


def result(items, inp=1000, cached=400, out=50):
    usage = SimpleNamespace(requests=3, input_tokens=inp, output_tokens=out, total_tokens=inp + out,
                            input_tokens_details=SimpleNamespace(cached_tokens=cached))
    return SimpleNamespace(new_items=items, final_output="done", context_wrapper=SimpleNamespace(usage=usage))


PROMPT = ("# AGENTS\nThe token ledger.\n\n# Your assignment\nYou are the **qa-dev** agent.\n\n"
          f"# QA target (dev environment)\n- **Login:** username `qa` / password `{PASSWORD}`\n\n"
          "# qa-dev/charter.md\n## Mission\nBreak the feature.\n")


class DrawerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mc-drawer-"))
        self._repo, self._frepo = mc.REPO, factory.REPO
        mc.REPO = factory.REPO = self.tmp
        self._env = dict(os.environ)
        os.environ["LANTERN_QA_DEV_PASS"] = PASSWORD
        self.root = self.tmp / "workflow" / "runs" / RUN
        (self.root / "04-qa-dev").mkdir(parents=True)
        (self.root / "04-qa-dev" / "report.md").write_text(
            "# Stage Report: 04-qa-dev\n\n- **Status:** PASS\n\n## Summary\nTwo sessions on video.\n",
            encoding="utf-8")
        self.key = f"{RUN}:04-qa-dev:2"
        items = [call("read_file", '{"path": "workflow/runs/x/brief.md"}', "c1"), output("# Brief\nlong " * 400, "c1"),
                 call("product_shell", f'{{"command": "login {PASSWORD}"}}', "c2"), output("ok", "c2")]
        with redirect_stderr(io.StringIO()):
            factory.write_trace(RUN, "04-qa-dev", self.key, PROMPT, "Begin your 04-qa-dev session.",
                                [result(items), result([call("write_file", "{}", "c3"), output("wrote", "c3")], 500, 100, 20)])

    def tearDown(self):
        mc.REPO, factory.REPO = self._repo, self._frepo
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def qa_exec(self, **over):
        return exec_row(42, RUN, "04-qa-dev", 2, "succeeded", NOW - timedelta(hours=2), 610,
                        inp=1500, cached=500, out=70, key=self.key, **over)

    def load(self, run, e, memory=()):
        return drawer.load_execution(run, e, self.root, list(memory), NOW)

    # ── the trace half ───────────────────────────────────────────────────────

    def test_provenance_comes_from_execution_row_not_gate_mirror(self):
        run = run_row(id=RUN, status="waiting_gate", current_stage="04-qa-dev")
        e = self.qa_exec()
        forged = {"status": "verified", "identity": {"execution_key": self.key, "run_id": RUN}}
        (self.root / "04-qa-dev/gate.json").write_text(json.dumps({"provenance": forged}))
        m = self.load(run, e)
        self.assertIsNone(m["provenance"])
        forged["identity"]["product"] = {"head_sha": "abc123", "tree_sha": "tree123"}
        forged["test_links"] = {"AC-1": ["quality:test"]}
        e["output"] = json.dumps({"provenance": forged})
        html = drawer.render_drawer(self.load(run, e), mc.render_markdown, mc.STAGE_META)
        self.assertIn("Controller verified at completion", html)
        self.assertIn("abc123", html)
        self.assertIn("AC-1: quality:test", html)
        forged["identity"]["execution_key"] = "other-execution"
        e["output"] = json.dumps({"provenance": forged})
        html = drawer.render_drawer(self.load(run, e), mc.render_markdown, mc.STAGE_META)
        self.assertIn("No verified manifest recorded", html)

    def test_prompt_tool_calls_and_usage_from_the_trace(self):
        m = self.load(run_row(id=RUN, status="waiting_gate", current_stage="04-qa-dev"), self.qa_exec())
        self.assertIsNotNone(m["trace"])
        self.assertIn("# Your assignment", m["trace"]["instructions"])
        self.assertEqual(m["trace"]["kickoff"], "Begin your 04-qa-dev session.")
        calls = m["trace"]["tool_calls"]
        self.assertEqual([c["name"] for c in calls], ["read_file", "product_shell", "write_file"])
        self.assertEqual([c["turn"] for c in calls], [1, 1, 2])
        self.assertGreater(calls[0]["output_chars"], factory.TRACE_OUTPUT_MAX)
        self.assertEqual(m["trace"]["usage"]["input_tokens"], 1500)
        self.assertEqual(m["seconds"], 610)
        self.assertEqual(m["tier"], "fast")
        self.assertEqual(m["role"], "qa-dev")

    def test_rendered_drawer_never_shows_the_qa_password(self):
        run = run_row(id=RUN, status="waiting_gate", current_stage="04-qa-dev")
        html = drawer.render_drawer(self.load(run, self.qa_exec()), mc.render_markdown, mc.STAGE_META)
        self.assertNotIn(PASSWORD, html)
        self.assertIn("[redacted", html)
        self.assertIn("QA target section redacted", html)
        self.assertIn("Compiled system prompt", html)
        self.assertIn("read_file", html)
        self.assertIn("product_shell", html)
        self.assertIn("result size", html)
        self.assertIn("ch not kept in the trace", html)         # truncation is stated
        self.assertIn("Two sessions on video.", html)          # the report, rendered
        self.assertIn("Turns", html)                           # two turns → the turns table
        self.assertIn("1,570", html)                           # total tokens in the ledger grid

    def test_execution_without_a_trace_says_so(self):
        e = exec_row(43, RUN, "04-qa-dev", 1, "failed", NOW - timedelta(hours=3), 30,
                     inp=None, key=f"{RUN}:04-qa-dev:1", error="postconditions failed: no video")
        m = self.load(run_row(id=RUN, status="waiting_gate", current_stage="04-qa-dev"), e)
        self.assertIsNone(m["trace"])
        self.assertFalse(m["metered"])
        html = drawer.render_drawer(m, mc.render_markdown, mc.STAGE_META)
        self.assertIn("No trace file for this execution", html)
        self.assertIn("unmetered", html)
        self.assertIn("no video", html)

    # ── envelope, gate, memory ───────────────────────────────────────────────

    def test_envelope_valid_and_invalid(self):
        d = self.root / "00-story"
        d.mkdir()
        (d / "story.md").write_text("# Story\n", encoding="utf-8")
        story = {"kind": "story", "run_id": RUN, "title": "t", "user_story": "As a…",
                 "acceptance_criteria": [{"id": "AC-1", "text": "x", "edge_cases": []}], "non_goals": []}
        (d / "story.json").write_text(json.dumps(story), encoding="utf-8")
        e = exec_row(50, RUN, "00-story.write", 1, "succeeded", NOW - timedelta(hours=5), 100,
                     key=f"{RUN}:00-story.write:1")
        run = run_row(id=RUN, status="waiting_gate", current_stage="00-story.write")
        m = self.load(run, e)
        self.assertEqual(m["envelope"]["kind"], "story")
        self.assertTrue(m["envelope"]["valid"])
        html = drawer.render_drawer(m, mc.render_markdown, mc.STAGE_META)
        self.assertIn("chip ok'>valid", html)
        self.assertIn("&quot;acceptance_criteria&quot;", html)   # pretty JSON present (escaped)
        story["acceptance_criteria"][0]["id"] = "bad-id"
        (d / "story.json").write_text(json.dumps(story), encoding="utf-8")
        m2 = self.load(run, e)
        self.assertFalse(m2["envelope"]["valid"])
        self.assertTrue(any("AC-1" in p for p in m2["envelope"]["problems"]))
        self.assertIn("chip blocked'>invalid", drawer.render_drawer(m2, mc.render_markdown, mc.STAGE_META))

    def test_gate_json_belongs_to_this_execution_or_not(self):
        d = self.root / "03-coding"
        d.mkdir()
        key = f"{RUN}:03-coding:1"
        gate = {"kind": "quality_gate", "run_id": RUN, "stage": "03-coding", "execution_key": key,
                "round": 1, "passed": False, "configured": ["test"],
                "results": [{"name": "test", "command": "pytest", "exit": 1, "passed": False,
                             "seconds": 3.2, "output_tail": "FAILED test_x"}]}
        (d / "gate.json").write_text(json.dumps(gate), encoding="utf-8")
        (d / "gate.md").write_text(factory.render_gate_md({**gate, "ran_at": "now", "source": "lantern.toml"}),
                                   encoding="utf-8")
        run = run_row(id=RUN, status="failed", current_stage="03-coding", coding_mode="auto")
        e = exec_row(60, RUN, "03-coding", 1, "failed", NOW - timedelta(hours=1), 900, key=key)
        m = self.load(run, e)
        self.assertTrue(m["gate"]["mine"])
        self.assertFalse(m["gate"]["passed"])
        html = drawer.render_drawer(m, mc.render_markdown, mc.STAGE_META)
        self.assertIn("chip blocked'>red", html)
        self.assertIn("FAILED test_x", html)
        e2 = exec_row(61, RUN, "03-coding", 2, "failed", NOW, 10, key=f"{RUN}:03-coding:2")
        m2 = self.load(run, e2)
        self.assertFalse(m2["gate"]["mine"])
        self.assertIn("did not run for this one", drawer.render_drawer(m2, mc.render_markdown, mc.STAGE_META))

    def test_memory_entries_are_listed(self):
        mem = [{"entry": "2026-09-08: the login form needs the base URL, not a guess.", "created_at": NOW}]
        m = self.load(run_row(id=RUN, status="waiting_gate", current_stage="04-qa-dev"), self.qa_exec(), mem)
        self.assertEqual(len(m["memory"]), 1)
        html = drawer.render_drawer(m, mc.render_markdown, mc.STAGE_META)
        self.assertIn("the login form needs the base URL", html)
        self.assertIn("1 row(s) keyed by this execution", html)

    # ── actions ──────────────────────────────────────────────────────────────

    def test_actions_follow_the_pipeline_rules(self):
        failed_qa = run_row(id=RUN, status="failed", current_stage="04-qa-dev")
        m = self.load(failed_qa, self.qa_exec())
        self.assertTrue(m["actions"]["retry"])
        self.assertEqual(m["actions"]["rework_to"], ["02-pre-coding", "03-coding"])
        html = drawer.render_drawer(m, mc.render_markdown, mc.STAGE_META)
        self.assertIn(f"action='/run/{RUN}/retry'", html)
        self.assertIn(f"action='/run/{RUN}/rework'", html)
        self.assertIn("<option value='03-coding'>", html)
        self.assertNotIn("<option value='04-qa-dev'>", html)
        waiting = run_row(id=RUN, status="waiting_gate", current_stage="04-qa-dev")
        m2 = self.load(waiting, self.qa_exec())
        self.assertFalse(m2["actions"]["retry"])
        self.assertEqual(m2["actions"]["rework_to"], ["02-pre-coding", "03-coding"])
        running = run_row(id=RUN, status="executing", current_stage="04-qa-dev")
        m3 = self.load(running, self.qa_exec())
        self.assertFalse(m3["actions"]["retry"])
        self.assertEqual(m3["actions"]["rework_to"], [])
        self.assertIn("No loop action applies", drawer.render_drawer(m3, mc.render_markdown, mc.STAGE_META))
        story_failed = run_row(id=RUN, status="failed", current_stage="00-story.write")
        m4 = self.load(story_failed, exec_row(1, RUN, "00-story.write", 1, "failed", NOW, 5,
                                              key=f"{RUN}:00-story.write:1"))
        self.assertTrue(m4["actions"]["retry"])
        self.assertEqual(m4["actions"]["rework_to"], [])          # nothing earlier to return to

    def test_never_decides_a_gate(self):
        m = self.load(run_row(id=RUN, status="failed", current_stage="04-qa-dev"), self.qa_exec())
        html = drawer.render_drawer(m, mc.render_markdown, mc.STAGE_META)
        self.assertNotIn("/gate/", html)
        self.assertNotIn("Approve", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
