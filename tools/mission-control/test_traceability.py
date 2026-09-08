"""The traceability matrix from fixture envelopes (Mission Control v3, D22).

    ..\\..\\tools\\azure-runner\\.venv\\Scripts\\python test_traceability.py

Stdlib only, no database. A temporary run folder carries a story, a plan, a coding
handoff, a QA charter and a validation envelope; the matrix must trace every criterion
across them by identifier and compute — never choose — each row's verdict.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as mc  # noqa: E402  (loads pipeline for everyone)
import traceability as tr  # noqa: E402

RUN = "feat-20260908-trace-matrix"

STORY = {"kind": "story", "run_id": RUN, "title": "Status facts",
         "acceptance_criteria": [
             {"id": "AC-1", "text": "runs carry branch facts", "edge_cases": ["nulls", "empty"]},
             {"id": "AC-2", "text": "gates carry age_seconds", "edge_cases": []},
             {"id": "AC-3", "text": "human output is byte-identical", "edge_cases": ["no runs"]}],
         "non_goals": []}
PLAN = {"kind": "plan", "run_id": RUN, "write_scope": ["tools/**"], "schema_changes": False,
        "hitl_required": False,
        "tasks": [{"id": "T1", "title": "add branch fields", "size": "S", "criteria": ["AC-1"]},
                  {"id": "T2", "title": "add age_seconds", "size": "S", "criteria": ["AC-2"]},
                  {"id": "T3", "title": "refactor helper", "size": "XS", "criteria": []}],
        "deferred_criteria": [{"id": "AC-3", "reason": "covered by the existing snapshot test"}]}
HANDOFF = {"kind": "coding_branch", "run_id": RUN, "branch": "feat/x", "commits": [
    {"sha": "dd62c336b50f", "subject": f"{RUN}: task 1 — branch fields in status json"},
    {"sha": "40df07cf7080", "subject": f"{RUN}: AC-2 age_seconds on pending gates"},
    {"sha": "b192ee9388b3", "subject": "chore: tidy imports"}]}
CHARTER = ("# Test charter\n\n## 1. Branch facts (AC-1)\n- null working branch stays null\n\n"
           "## 2. Gate ages\nProbe AC-2 with a future requested_at.\n\n## 3. Exploratory\nWander.\n")
VALIDATION = {"kind": "validation", "run_id": RUN, "verdict": "fail",
              "criteria": [{"id": "AC-1", "status": "covered", "evidence": "test_status_json.py::test_branch_fields"},
                           {"id": "AC-2", "status": "missing", "evidence": "no test asserts age_seconds"},
                           {"id": "AC-3", "status": "skipped", "evidence": "deferred by the plan"}],
              "fix_now": [{"id": "F1", "title": "assert age_seconds", "criterion": "AC-2"}]}


class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mc-matrix-"))
        self.root = self.tmp / RUN

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel: str, data):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")

    def full(self):
        self.write("00-story/story.json", STORY)
        self.write("02-pre-coding/plan.json", PLAN)
        self.write("03-coding/handoff.json", HANDOFF)
        self.write("04-qa-dev/test-charter.md", CHARTER)
        self.write("05-post-coding/validation.json", VALIDATION)
        return tr.build_matrix(RUN, self.root)

    def test_every_stage_present_and_rows_traced_by_identifier(self):
        m = self.full()
        self.assertTrue(all(m["present"].values()))
        rows = {r["id"]: r for r in m["rows"]}
        ac1, ac2, ac3 = rows["AC-1"], rows["AC-2"], rows["AC-3"]
        self.assertEqual([t["id"] for t in ac1["tasks"]], ["T1"])
        self.assertEqual([c["sha"] for c in ac1["commits"]], ["dd62c336"])     # via "task 1"
        self.assertEqual(ac1["charter"], ["1. Branch facts (AC-1)"])
        self.assertEqual(ac1["verdict"]["status"], "covered")
        self.assertEqual(ac1["overall"], "complete")
        self.assertEqual([c["sha"] for c in ac2["commits"]], ["40df07cf"])     # via "AC-2"
        self.assertEqual(ac2["charter"], ["2. Gate ages"])
        self.assertEqual(ac2["validation_state"], "missing")
        self.assertEqual(ac2["overall"], "gap")
        self.assertEqual(ac3["plan_state"], "deferred")
        self.assertEqual(ac3["deferred"], "covered by the existing snapshot test")
        self.assertEqual(ac3["commits"], [])
        self.assertEqual(ac3["coding_state"], "deferred")
        self.assertEqual(ac3["qa_state"], "deferred")
        self.assertEqual(ac3["overall"], "deferred")
        self.assertEqual(m["counts"], {"complete": 1, "gap": 1, "deferred": 1, "pending": 0})

    def test_notes_name_what_traces_to_nothing(self):
        m = self.full()
        joined = " | ".join(m["notes"])
        self.assertIn("1 plan task(s) map to no criterion: T3", joined)
        self.assertIn("1 commit(s) name no criterion or task: b192ee93 chore: tidy imports", joined)
        self.assertIn("charter section(s) name no criterion: 3. Exploratory", joined)
        self.assertIn("validation verdict: fail · fix_now 1", joined)

    def test_partial_run_marks_later_stages_pending(self):
        self.write("00-story/story.json", STORY)
        m = tr.build_matrix(RUN, self.root)
        self.assertTrue(m["present"]["story"])
        self.assertFalse(m["present"]["plan"])
        for r in m["rows"]:
            self.assertEqual(r["plan_state"], "pending")
            self.assertEqual(r["coding_state"], "pending")
            self.assertEqual(r["qa_state"], "pending")
            self.assertEqual(r["validation_state"], "pending")
            self.assertEqual(r["overall"], "pending")
        self.assertEqual(m["counts"]["pending"], 3)

    def test_unplanned_and_untraced_are_gaps_once_the_stage_ran(self):
        self.write("00-story/story.json", STORY)
        plan = dict(PLAN, tasks=PLAN["tasks"][:1], deferred_criteria=[])
        self.write("02-pre-coding/plan.json", plan)
        m = tr.build_matrix(RUN, self.root)
        rows = {r["id"]: r for r in m["rows"]}
        self.assertEqual(rows["AC-2"]["plan_state"], "unplanned")
        self.assertEqual(rows["AC-2"]["overall"], "gap")
        self.assertEqual(rows["AC-1"]["plan_state"], "planned")
        self.assertEqual(rows["AC-1"]["overall"], "pending")           # coding has not run

    def test_no_story_means_no_matrix(self):
        m = tr.build_matrix(RUN, self.root)
        self.assertFalse(m["present"]["story"])
        self.assertEqual(m["rows"], [])
        self.assertIn("No story yet", tr.render_matrix(m))

    def test_builder_handoffs_are_read_too(self):
        self.write("00-story/story.json", STORY)
        self.write("03-coding/builders/api/handoff.json",
                   {"commits": [{"sha": "aaaaaaaaaaaa", "subject": "AC-1 api fields"}]})
        self.write("03-coding/builders/docs/handoff.json",
                   {"commits": [{"sha": "bbbbbbbbbbbb", "subject": "AC-2 docs"}]})
        m = tr.build_matrix(RUN, self.root)
        rows = {r["id"]: r for r in m["rows"]}
        self.assertEqual(rows["AC-1"]["commits"][0]["builder"], "api")
        self.assertEqual(rows["AC-2"]["commits"][0]["builder"], "docs")
        self.assertEqual(m["commit_count"], 2)

    def test_render_shows_chips_headers_and_summary(self):
        html = tr.render_matrix(self.full())
        self.assertIn("class='matrix'", html)
        self.assertIn("chip ok'>complete", html)
        self.assertIn("chip blocked'>gap", html)
        self.assertIn("chip warn'>deferred", html)
        self.assertIn("chip blocked'>missing", html)
        self.assertIn("02-pre-coding/plan.json · present", html)
        self.assertIn("<b>3</b> criteria", html)
        self.assertIn("test_status_json.py::test_branch_fields", html)
        self.assertIn("[api]", tr.render_matrix(self._with_builder()))

    def _with_builder(self):
        self.write("00-story/story.json", STORY)
        self.write("03-coding/builders/api/handoff.json",
                   {"commits": [{"sha": "aaaaaaaaaaaa", "subject": "AC-1 api fields"}]})
        return tr.build_matrix(RUN, self.root)

    def test_charter_sections_split_on_headings(self):
        secs = tr.charter_sections(CHARTER)
        self.assertEqual([s["title"] for s in secs], ["Test charter", "1. Branch facts (AC-1)",
                                                      "2. Gate ages", "3. Exploratory"])
        self.assertEqual(secs[1]["mentions"], {"AC-1"})
        self.assertEqual(secs[2]["mentions"], {"AC-2"})
        self.assertEqual(tr.charter_sections(""), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
