"""`pipeline.py init-product` — installing the factory into a product repo (D21).

    .venv/Scripts/python test_init_product.py    (no database, no network, no model)

Fixture repos for each stack the detector claims to know, plus the two rules that make
the command safe to run twice on a repository someone else owns: an existing
`lantern.toml` is never silently replaced, and existing AGENTS.md text is never rewritten.

The written `lantern.toml` is parsed back with the SAME loader the coding gate uses
(`factory.quality_config`), so "it wrote a file" is never mistaken for "the gate can
read it".
"""

import sys
import tempfile
import tomllib
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import factory                       # noqa: E402
import init_product                  # noqa: E402

TODAY = datetime(2026, 9, 8, tzinfo=timezone.utc)


def repo(files: dict) -> Path:
    d = Path(tempfile.mkdtemp())
    for name, text in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return d


NODE = {"package.json": '{"name":"app","scripts":{"test":"jest","lint":"eslint .","build":"vite build"},'
                        '"devDependencies":{"typescript":"^5"}}'}
PYTHON = {"pyproject.toml": '[project]\nname = "app"\n\n[tool.ruff]\nline-length = 100\n\n[tool.mypy]\nstrict = true\n'}
GO = {"go.mod": "module example.com/app\n\ngo 1.22\n"}
RUST = {"Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\n'}


class Detection(unittest.TestCase):
    """The command must read the repo, not guess from its name."""

    def test_node_repo_gets_npm_commands(self):
        s = init_product.detect(repo(NODE))
        self.assertEqual([x["name"] for x in s], ["node"])
        self.assertEqual(s[0]["test"], "npm test")
        self.assertEqual(s[0]["lint"], "npm run lint")
        self.assertEqual(s[0]["typecheck"], "npx tsc --noEmit")
        self.assertEqual(s[0]["build"], "npm run build")

    def test_node_without_scripts_still_gets_a_test_and_a_warning(self):
        s = init_product.detect(repo({"package.json": '{"name":"a"}'}))
        self.assertEqual(s[0]["test"], "npm test")
        self.assertNotIn("lint", s[0])
        self.assertNotIn("build", s[0])
        self.assertTrue(any("test` script" in n for n in s[0]["notes"]))

    def test_the_npm_placeholder_test_script_is_not_treated_as_a_real_one(self):
        s = init_product.detect(repo({"package.json":
                                      '{"scripts":{"test":"echo \\"Error: no test specified\\" && exit 1"}}'}))
        self.assertTrue(s[0].get("notes"))

    def test_python_repo_gets_pytest_and_the_tools_it_configures(self):
        s = init_product.detect(repo(PYTHON))
        self.assertEqual(s[0]["test"], "pytest -q")
        self.assertEqual(s[0]["lint"], "ruff check .")
        self.assertEqual(s[0]["typecheck"], "mypy .")

    def test_setup_py_alone_is_a_python_repo(self):
        s = init_product.detect(repo({"setup.py": "from setuptools import setup\nsetup()\n"}))
        self.assertEqual([x["name"] for x in s], ["python"])
        self.assertEqual(s[0]["test"], "pytest -q")
        self.assertNotIn("lint", s[0])

    def test_go_and_rust(self):
        self.assertEqual(init_product.detect(repo(GO))[0]["test"], "go test ./...")
        self.assertEqual(init_product.detect(repo(RUST))[0]["test"], "cargo test")

    def test_a_polyglot_repo_runs_every_stack_and_one_red_fails_the_gate(self):
        cmds = init_product.quality_commands(init_product.detect(repo({**NODE, **PYTHON})))
        self.assertEqual(cmds["test"], "npm test && pytest -q")
        self.assertEqual(cmds["lint"], "npm run lint && ruff check .")

    def test_an_unknown_stack_is_said_out_loud(self):
        res = init_product.install(repo({"README.md": "# hi\n"}), today=TODAY)
        self.assertEqual(res["stacks"], [])
        self.assertTrue(any("no known stack" in n for n in res["notes"]))
        self.assertIn("TODO", res["toml_text"])


class WhatItWrites(unittest.TestCase):

    def test_lantern_toml_is_readable_by_the_gate_that_will_run_it(self):
        root = repo(NODE)
        init_product.install(root, today=TODAY)
        cfg = factory.quality_config(root)          # the coding gate's own loader
        self.assertEqual(dict(cfg["commands"])["test"], "npm test")
        self.assertEqual(dict(cfg["commands"])["typecheck"], "npx tsc --noEmit")
        self.assertEqual(cfg["timeout_s"], init_product.TIMEOUT_S)
        self.assertNotIn("error", cfg)

    def test_optional_commands_the_repo_lacks_stay_commented_examples(self):
        root = repo(GO)
        init_product.install(root, today=TODAY)
        text = (root / "lantern.toml").read_text(encoding="utf-8")
        self.assertIn('test = "go test ./..."', text)
        self.assertIn("# typecheck", text)
        self.assertEqual(tomllib.loads(text)["quality"].get("typecheck"), None)

    def test_agents_md_is_created_when_absent(self):
        root = repo(PYTHON)
        res = init_product.install(root, today=TODAY)
        self.assertEqual(res["agents_action"], "created")
        text = (root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Built by the Lantern software factory", text)
        self.assertIn("pytest -q", text)
        self.assertIn("lantern/regressions/", text)

    def test_existing_agents_md_text_is_never_touched(self):
        root = repo({**PYTHON, "AGENTS.md": "# House rules\n\nUse tabs. Never rebase.\n"})
        res = init_product.install(root, today=TODAY)
        self.assertEqual(res["agents_action"], "appended")
        text = (root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# House rules\n\nUse tabs. Never rebase.\n"))
        self.assertIn(init_product.START, text)

    def test_running_twice_changes_nothing_the_second_time(self):
        root = repo(NODE)
        init_product.install(root, today=TODAY)
        first = (root / "AGENTS.md").read_text(encoding="utf-8")
        res = init_product.install(root, today=TODAY)
        self.assertEqual(res["agents_action"], "unchanged (block present)")
        self.assertIn("kept", res["toml_action"])
        self.assertEqual(first, (root / "AGENTS.md").read_text(encoding="utf-8"))

    def test_an_existing_lantern_toml_is_kept_unless_forced(self):
        root = repo({**NODE, "lantern.toml": '[quality]\ntest = "make check"\n'})
        init_product.install(root, today=TODAY)
        self.assertEqual(dict(factory.quality_config(root)["commands"])["test"], "make check",
                         "the team's own gate was overwritten without being asked")
        init_product.install(root, force=True, today=TODAY)
        self.assertEqual(dict(factory.quality_config(root)["commands"])["test"], "npm test")

    def test_dry_run_writes_nothing(self):
        root = repo(NODE)
        res = init_product.install(root, dry_run=True, today=TODAY)
        self.assertFalse((root / "lantern.toml").exists())
        self.assertFalse((root / "AGENTS.md").exists())
        self.assertIn("npm test", res["toml_text"])

    def test_it_says_how_to_point_a_run_at_the_repo(self):
        res = init_product.install(repo(GO), today=TODAY)
        for expected in ("Product repo:", "--product-repo", "set-product"):
            self.assertIn(expected, res["how_to_point"])


class CommandLine(unittest.TestCase):

    def test_main_returns_zero_on_a_known_stack_and_one_on_an_unknown_one(self):
        self.assertEqual(init_product.main([str(repo(RUST)), "--dry-run"]), 0)
        self.assertEqual(init_product.main([str(repo({"a.txt": "x"})), "--dry-run"]), 1)

    def test_a_missing_directory_is_an_error_not_a_traceback(self):
        self.assertEqual(init_product.main([str(Path(tempfile.gettempdir()) / "no-such-repo-xyz")]), 2)

    def test_pipeline_dispatches_it_without_a_database(self):
        src = (HERE / "pipeline.py").read_text(encoding="utf-8")
        self.assertIn('LOCAL_ONLY_CMDS = {"repos", "init-product"}', src)
        self.assertIn('sub.add_parser("init-product"', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
