"""Design mode (D25): the brief field, runner routing, and the html handoff checks.

    .venv/bin/python test_design_mode.py      (no network, no database)
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orchestrator as o  # noqa: E402
import pipeline  # noqa: E402

RUN = "feat-20260911-design-mode"


class BriefField(unittest.TestCase):
    def test_reads_html_and_paper_and_ignores_anything_else(self):
        self.assertEqual(pipeline.parse_brief_design_mode("- **Design mode:** html\n"), "html")
        self.assertEqual(pipeline.parse_brief_design_mode("- **Design mode:** `paper`\n"), "paper")
        self.assertEqual(pipeline.parse_brief_design_mode("- **Design mode:** figma\n"), "")
        self.assertEqual(pipeline.parse_brief_design_mode("- **Design mode:**\n- **Coding mode:** auto\n"), "")
        self.assertEqual(pipeline.parse_brief_design_mode("no field at all"), "")


class RunnerRouting(unittest.TestCase):
    def test_design_stage_follows_the_mode(self):
        self.assertEqual(pipeline.stage_runner_for("01-ui-ux.design", "paper"), "workstation")
        self.assertEqual(pipeline.stage_runner_for("01-ui-ux.design", None), "workstation")
        self.assertEqual(pipeline.stage_runner_for("01-ui-ux.design", "html"), "ec2")

    def test_other_stages_are_unchanged(self):
        for stage, _, _, _, runner in pipeline.FEATURE_STAGES:
            if stage != "01-ui-ux.design":
                self.assertEqual(pipeline.stage_runner_for(stage, "html"), runner, stage)


class HtmlHandoffChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo_patch = mock.patch.object(o, "REPO", self.tmp)
        self.repo_patch.start()
        self.sdir = self.tmp / "workflow/runs" / RUN / "01-ui-ux"
        (self.sdir / "prototype").mkdir(parents=True)
        (self.sdir / "media").mkdir()
        (self.sdir / "critique-log.md").write_text("## wizard — layout pass\nok\n", encoding="utf-8")
        (self.sdir / "media" / "wizard@2x.png").write_bytes(b"\x89PNG fake")
        (self.sdir / "prototype" / "wizard.html").write_text("<html>" + "x" * 600 + "</html>", encoding="utf-8")

    def tearDown(self):
        self.repo_patch.stop()

    def handoff(self, **over):
        data = {"design_mode": "html", "paper_url": None, "recommended": "wizard",
                "options": [{"name": "wizard", "status": "presented",
                             "pngs": [f"workflow/runs/{RUN}/01-ui-ux/media/wizard@2x.png"],
                             "prototype": f"workflow/runs/{RUN}/01-ui-ux/prototype/wizard.html"}]}
        data.update(over)
        (self.sdir / "handoff.json").write_text(json.dumps(data), encoding="utf-8")

    def test_html_mode_accepts_prototype_plus_png_and_needs_no_jsx(self):
        self.handoff()
        with mock.patch.dict(os.environ, {"LANTERN_DESIGN_MODE": "html"}):
            self.assertEqual(o.check_claimed_artifacts(RUN, "01-ui-ux"), [])

    def test_html_mode_rejects_a_missing_or_stub_prototype(self):
        self.handoff()
        (self.sdir / "prototype" / "wizard.html").write_text("<html></html>", encoding="utf-8")
        with mock.patch.dict(os.environ, {"LANTERN_DESIGN_MODE": "html"}):
            problems = o.check_claimed_artifacts(RUN, "01-ui-ux")
        self.assertTrue(any("no prototype" in p for p in problems), problems)

    def test_html_mode_requires_the_declaration(self):
        self.handoff(design_mode="paper")
        with mock.patch.dict(os.environ, {"LANTERN_DESIGN_MODE": "html"}):
            problems = o.check_claimed_artifacts(RUN, "01-ui-ux")
        self.assertTrue(any('"design_mode": "html"' in p for p in problems), problems)

    def test_paper_mode_still_demands_jsx(self):
        self.handoff(design_mode="paper")
        with mock.patch.dict(os.environ, {"LANTERN_DESIGN_MODE": "paper"}):
            problems = o.check_claimed_artifacts(RUN, "01-ui-ux")
        self.assertTrue(any("jsx/" in p for p in problems), problems)


class PromptSelection(unittest.TestCase):
    def test_html_note_is_used_only_in_html_mode(self):
        with mock.patch.dict(os.environ, {"LANTERN_DESIGN_MODE": "html"}):
            self.assertTrue(o.html_design_stage("01-ui-ux.design"))
            self.assertFalse(o.html_design_stage("01-ui-ux.diverge"))
        with mock.patch.dict(os.environ, {"LANTERN_DESIGN_MODE": "paper"}):
            self.assertFalse(o.html_design_stage("01-ui-ux.design"))
        self.assertIn("01-ui-ux.design:html", o.PHASE_NOTES)


if __name__ == "__main__":
    unittest.main()
