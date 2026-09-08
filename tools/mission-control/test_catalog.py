"""The factory catalog from fixture files (Mission Control v3, D22).

    ..\\..\\tools\\azure-runner\\.venv\\Scripts\\python test_catalog.py

Stdlib only, no database. A temporary repo carries role charters, the tool matrix doc,
a lantern.toml, an evals report and a plan with builders; the env mapping is explicit.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as mc  # noqa: E402
import catalog  # noqa: E402

CHARTER = ("# Charter — story\n\n## Mission\n\nTurn a rough brief into the contract the whole "
           "factory is held to: one user story,\nnumbered acceptance criteria, edge cases, non-goals.\n\n"
           "Second paragraph is not the one-liner.\n\n## Pipeline position\n\nStage 0.\n")
TOOLING = ("# Agent tooling\n\n## 6. Per-agent connection matrix\n\n"
           "| Agent | MCP / CLIs | Credentials (SSM) | May write to |\n|---|---|---|---|\n"
           "| story | run folder reads | — | run folder only (`00-story/story.*`) |\n"
           "| qa-dev | `playwright` (video), qa-recorder | github, `/lantern/qa/dev/*` | run folder, PR comments |\n")
TOML = "[quality]\ntest = \"pytest -q\"\nlint = \"ruff check .\"\ntimeout_s = 120\n"


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mc-catalog-"))
        for role, text in (("story", CHARTER), ("qa-dev", "# Charter — qa-dev\n\n## Mission\n\nBreak the feature before users can.\n")):
            d = self.tmp / "agents" / role
            d.mkdir(parents=True)
            (d / "charter.md").write_text(text, encoding="utf-8")
            (d / "skills.md").write_text("# skills\n", encoding="utf-8")
            (d / "memory.md").write_text("# memory\n\n- 2026-09-01: one\n- 2026-09-02: two\n", encoding="utf-8")
        (self.tmp / "agents" / "_template").mkdir()
        (self.tmp / "agents" / "_template" / "charter.md").write_text("# template\n", encoding="utf-8")
        (self.tmp / "docs").mkdir()
        (self.tmp / "docs" / "AGENT-TOOLING.md").write_text(TOOLING, encoding="utf-8")
        (self.tmp / "lantern.toml").write_text(TOML, encoding="utf-8")
        self.env = {"LANTERN_MODEL_REASONING": "gpt-5.6-sol", "LANTERN_EFFORT_FAST": "xhigh",
                    "LANTERN_EFFORT_CODING": "bogus", "LANTERN_FIX_ROUNDS": "2",
                    "AZURE_OPENAI_ENDPOINT": "https://x.openai.azure.com"}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, products=(), plans=None):
        return catalog.build_catalog(self.tmp, self.env, list(products), mc.STAGE_META, mc.GATE_META, plans)

    def test_roles_from_charters_with_mission_tier_and_tools(self):
        c = self.build()
        roles = {r["role"]: r for r in c["roles"]}
        self.assertEqual(set(roles), {"story", "qa-dev"})            # _template skipped
        story = roles["story"]
        self.assertTrue(story["mission"].startswith("Turn a rough brief into the contract"))
        self.assertNotIn("Second paragraph", story["mission"])
        self.assertEqual(story["tier"], "reasoning")
        self.assertIn("00-story.write", story["stages"])
        self.assertEqual(story["tools"], "run folder reads")
        self.assertEqual(story["writes"], "run folder only (00-story/story.*)")
        self.assertEqual(story["memory_entries"], 2)
        qa = roles["qa-dev"]
        self.assertEqual(qa["tier"], "fast")
        self.assertIn("playwright", qa["tools"])
        self.assertIn("04-qa-dev", qa["stages"])

    def test_stages_and_gates_follow_the_pipeline_table(self):
        c = self.build()
        keys = [s["stage"] for s in c["stages"]]
        self.assertEqual(keys[0], "00-story.scout")
        self.assertEqual(keys[-1], "07-qa-staging")
        by = {s["stage"]: s for s in c["stages"]}
        self.assertEqual(by["00-story.write"]["gate"], "story_signoff")
        self.assertEqual(by["00-story.write"]["gate_title"], "Approve the story")
        self.assertEqual(by["00-story.write"]["envelope"][1], "story.json")
        self.assertEqual(by["03-coding"]["type"], "human")
        self.assertEqual(by["03-coding"]["role"], "coding")
        self.assertIsNone(by["03-coding"]["tier"])
        self.assertEqual(by["01-ui-ux.diverge"]["tier"], "fast")
        self.assertEqual(by["01-ui-ux.design"]["runner"], "workstation")

    def test_model_stack_resolves_fallbacks_and_effort(self):
        ms = self.build()["model_stack"]
        tiers = {t["tier"]: t for t in ms["tiers"]}
        self.assertEqual(tiers["reasoning"]["deployment"], "gpt-5.6-sol")
        self.assertIsNone(tiers["reasoning"]["via"])
        self.assertEqual(tiers["coding"]["deployment"], "gpt-5.6-sol")
        self.assertEqual(tiers["coding"]["via"], "reasoning")
        self.assertIsNone(tiers["coding"]["configured"])
        self.assertEqual(tiers["fast"]["effort"], "xhigh")
        self.assertFalse(tiers["fast"]["effort_default"])
        self.assertEqual(tiers["coding"]["effort"], "high")
        self.assertIn("invalid", tiers["coding"]["effort_note"])
        self.assertEqual(tiers["reasoning"]["effort"], "high")
        self.assertTrue(tiers["reasoning"]["effort_default"])
        self.assertTrue(ms["endpoint"])
        knobs = {k["var"]: k for k in ms["knobs"]}
        self.assertEqual(knobs["LANTERN_FIX_ROUNDS"]["value"], "2")
        self.assertIsNone(knobs["LANTERN_EXECUTOR"]["value"])
        self.assertEqual(knobs["LANTERN_EXECUTOR"]["default"], "inprocess")

    def test_unset_reasoning_tier_is_reported_not_fatal(self):
        self.env.pop("LANTERN_MODEL_REASONING")
        tiers = {t["tier"]: t for t in self.build()["model_stack"]["tiers"]}
        self.assertIsNone(tiers["reasoning"]["deployment"])
        self.assertIsNone(tiers["coding"]["deployment"])

    def test_products_read_lantern_toml_and_explain_the_rest(self):
        other = self.tmp / "other-product"
        other.mkdir()
        c = self.build(products=[str(other), "https://github.com/org/repo", str(self.tmp / "missing"),
                                 str(self.tmp)])                     # this repo again → deduped
        labels = [p["label"] for p in c["products"]]
        self.assertEqual(labels[0], "this repository (dogfood gate)")
        self.assertEqual(len(c["products"]), 4)
        mine = c["products"][0]
        self.assertEqual([x["name"] for x in mine["commands"]], ["test", "lint"])
        self.assertEqual(mine["commands"][0]["command"], "pytest -q")
        self.assertEqual(mine["timeout_s"], 120)
        by = {p["repo"]: p for p in c["products"]}
        self.assertEqual(by[str(other)]["commands"], [])
        self.assertTrue(by[str(other)]["exists"])
        self.assertIn("remote repository", by["https://github.com/org/repo"]["error"])
        self.assertIn("not a directory", by[str(self.tmp / "missing")]["error"])

    def test_evals_and_builders_when_present(self):
        c = self.build()
        self.assertIsNone(c["evals"])
        self.assertEqual(c["builders"], [])
        (self.tmp / "tools" / "evals").mkdir(parents=True)
        (self.tmp / "tools" / "evals" / "REPORT.md").write_text("# Evals\n\n| suite | score |\n|---|---|\n| plan coverage | 0.91 |\n",
                                                                encoding="utf-8")
        plan = self.tmp / "plan.json"
        plan.write_text(json.dumps({"tasks": [], "builders": [
            {"name": "api", "write_scope": ["src/api/**"], "tasks": ["T1"], "criteria": ["AC-1"]},
            {"name": "docs", "write_scope": ["docs/**"], "tasks": ["T2"], "criteria": ["AC-2"]}]}), encoding="utf-8")
        c = self.build(plans=[("feat-20260909-x", plan), ("feat-nope", self.tmp / "absent.json")])
        self.assertIn("plan coverage", c["evals"])
        self.assertEqual(len(c["builders"]), 1)
        self.assertEqual([b["name"] for b in c["builders"][0]["builders"]], ["api", "docs"])

    def test_render_mentions_every_section(self):
        (self.tmp / "tools" / "evals").mkdir(parents=True)
        (self.tmp / "tools" / "evals" / "REPORT.md").write_text("# Evals\n\nplan coverage 0.91\n", encoding="utf-8")
        html = catalog.render_catalog(self.build(), mc.render_markdown)
        for text in ("Roles", "story", "Stages and gates", "story_signoff", "Model stack",
                     "via reasoning fallback", "xhigh", "Products and their quality gates",
                     "pytest -q", "Evals", "plan coverage 0.91", "Parallel builders",
                     "No plan declares"):
            self.assertIn(text, html, text)
        html2 = catalog.render_catalog(self.build(products=[str(self.tmp / "empty")]), mc.render_markdown)
        self.assertIn("not a directory", html2)

    def test_parse_tool_matrix_ignores_headers_and_rules(self):
        m = catalog.parse_tool_matrix(TOOLING)
        self.assertEqual(set(m), {"story", "qa-dev"})
        self.assertEqual(m["qa-dev"]["credentials"], "github, `/lantern/qa/dev/*`")


if __name__ == "__main__":
    unittest.main(verbosity=2)
