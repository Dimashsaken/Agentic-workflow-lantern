"""Adversarial capability tests, including the actual SDK function-tool boundary."""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import factory
import orchestrator as o
from agents.tool_context import ToolContext
from tool_policy import StageAccess, readable


RUN = "feat-20260910-policy"


class Capabilities(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo, self.product = self.root / "lantern", self.root / "product"
        self.repo.mkdir()
        self.product.mkdir()
        (self.product / "app.py").write_text("value = 1\n", encoding="utf-8")
        (self.repo / "AGENTS.md").write_text("contract\n", encoding="utf-8")
        self.addCleanup(patch.stopall)
        patch.object(o, "REPO", self.repo).start()
        patch.object(factory, "REPO", self.repo).start()
        patch.dict(os.environ, {"LANTERN_PRODUCT_DIR": str(self.product),
                               "LANTERN_PRODUCT_WRITABLE": "1"}).start()

    def policy(self, role="coding", stage="03-coding", **kw):
        return StageAccess(self.repo, self.product, RUN, role, stage, stage, **kw)

    def invoke(self, tools, name, **args):
        tool = next(t for t in tools if t.name == name)
        arguments = json.dumps(args)
        ctx = ToolContext(context=None, tool_name=name, tool_call_id="test-call", tool_arguments=arguments)
        return asyncio.run(tool.on_invoke_tool(ctx, arguments))

    def test_scope_holds_through_real_sdk_tools(self):
        tools = o.stage_tools("pre-coding", RUN, "02-pre-coding", "execution-a")
        good = f"workflow/runs/{RUN}/02-pre-coding/plan.json"
        self.assertEqual(self.invoke(tools, "write_file", path=good, content="{}"), f"wrote {good}")
        for path in ("tools/azure-runner/orchestrator.py", "agents/coding/skills.md",
                     "workflow/RUNBOARD.md", f"workflow/runs/{RUN}/00-story/story.json",
                     "workflow/runs/another/02-pre-coding/plan.json", "product/app.py"):
            with self.subTest(path=path):
                self.assertNotEqual(self.invoke(tools, "write_file", path=path, content="tampered"), f"wrote {path}")
        self.assertEqual((self.product / "app.py").read_text(), "value = 1\n")

    def test_stage_tools_capture_identity_when_other_execution_changes_environment(self):
        first = o.stage_tools("coding", RUN, "03-coding", "a")
        other_product = self.root / "other-product"
        other_product.mkdir()
        (other_product / "app.py").write_text("other\n")
        os.environ["LANTERN_PRODUCT_DIR"] = str(other_product)
        second = o.stage_tools("coding", "feat-other", "03-coding", "b")
        self.assertEqual(self.invoke(first, "read_file", path="product/app.py"), "value = 1\n")
        self.invoke(first, "write_file", path="product/app.py", content="first")
        self.assertEqual(self.invoke(second, "read_file", path="product/app.py"), "other\n")
        other_run = f"workflow/runs/{RUN}/03-coding/report.md"
        self.assertNotEqual(self.invoke(second, "write_file", path=other_run, content="x"), f"wrote {other_run}")

    def test_roles_cannot_inherit_coding_shell_or_design_exports(self):
        for role, stage in (("researcher", "00-story.scout"), ("reviewer", "03-coding.review"),
                            ("qa-dev", "04-qa-dev"), ("security", "06-security")):
            names = {t.name for t in o.stage_tools(role, RUN, stage, "x")}
            self.assertFalse({"product_shell", "list_exports", "collect_export", "collect_jsx"} & names)
        self.assertIn("product_shell", {t.name for t in o.stage_tools("coding", RUN, "03-coding", "x")})
        self.assertIn("collect_export", {t.name for t in o.stage_tools("ui-ux", RUN, "01-ui-ux.design", "x")})
        with self.assertRaises(ValueError):
            o.stage_tools("coding", RUN, "06-security", "x")

    def test_host_artifacts_and_sibling_outputs_are_protected(self):
        policy = self.policy()
        for file in ("gate.json", "gate.md", "handoff.json", "branch.bundle", "state.json",
                     "builders.json", "trace/execution.json", "review/review.json",
                     "builders/sibling/report.md", "media/fake.webm", "media-manifest.json", ".collected.json"):
            with self.subTest(file=file), self.assertRaises(PermissionError):
                policy.write(f"workflow/runs/{RUN}/03-coding/{file}")
        builder = StageAccess(self.repo, self.product, RUN, "coding", "03-coding.api", "03-coding/builders/api")
        builder.write(f"workflow/runs/{RUN}/03-coding/builders/api/report.md")
        with self.assertRaises(PermissionError):
            builder.write(f"workflow/runs/{RUN}/03-coding/builders/ui/report.md")

    def test_windows_case_aliases_cannot_cross_role_or_run_boundaries(self):
        coding = self.policy()
        post = self.policy("post-coding", "05-post-coding")
        for path in (f"workflow/runs/{RUN}/03-coding/REVIEW/review.json",
                     f"workflow/runs/{RUN}/03-coding/TRACE/events.json",
                     f"workflow/runs/{RUN}/03-coding/GATE.JSON"):
            with self.subTest(path=path), self.assertRaises(PermissionError):
                coding.write(path)
        with self.assertRaises(PermissionError):
            post.write(f"workflow/runs/{RUN}/05-post-coding/VALIDATION.JSON")
        with self.assertRaises(PermissionError):
            coding.read("WORKFLOW/RUNS/other-run/report.md")

    def test_shared_reports_are_append_only_for_later_roles(self):
        for role, stage in (("story", "00-story"), ("validator", "05-post-coding"), ("reviewer", "03-coding")):
            policy = self.policy(role, stage)
            path = f"workflow/runs/{RUN}/{stage}/report.md"
            with self.assertRaises(PermissionError):
                policy.write(path)
            policy.write(path, append=True)

    def test_product_file_scope_is_checked_before_write(self):
        policy = self.policy(product_write=True, product_scope=("src/**",))
        policy.write("product/src/api.py")
        with self.assertRaises(PermissionError):
            policy.write("product/tests/test_api.py")

    def test_portable_paths_reject_traversal_streams_and_secret_aliases(self):
        for path in ("../outside", "/etc/passwd", "C:/outside", "product/../AGENTS.md",
                     "product/app.py:stream", "product/.env", "product/.ENV.production",
                     "product/.git/config", "tools/azure-runner/.env", "product/id_ed25519",
                     "product/cert.pem", "product/.env.", "product/.aws/credentials"):
            with self.subTest(path=path), self.assertRaises((ValueError, PermissionError)):
                readable(self.repo, self.product, path)
        self.assertEqual(readable(self.repo, self.product, "product/.env.example"), self.product / ".env.example")

    def test_symlink_cannot_alias_secret_or_escape(self):
        (self.product / ".env").write_text("SAMPLE_SECRET=value")
        alias = self.product / "innocent.txt"
        try:
            alias.symlink_to(self.product / ".env")
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        with self.assertRaises((PermissionError, ValueError)):
            self.policy().read("product/innocent.txt")

    def test_exports_cannot_overwrite_harness_or_manifest(self):
        tools = o.stage_tools("ui-ux", RUN, "01-ui-ux.design", "x")
        with patch.object(o, "_collect_export") as collect:
            for path in ("tools/azure-runner/orchestrator.py", f"workflow/runs/{RUN}/01-ui-ux/.collected.json"):
                self.invoke(tools, "collect_export", filename="option.png", dest_path=path)
            collect.assert_not_called()
        self.assertEqual(self.invoke(tools, "list_dir", path="product"), "app.py")

    def test_hardlink_cannot_alias_a_secret_under_an_innocent_name(self):
        secret = self.product / ".env"
        secret.write_text("SAMPLE_SECRET=value")
        os.link(secret, self.product / "innocent.txt")
        with self.assertRaises(PermissionError):
            self.policy().read("product/innocent.txt")


class CapabilityDocumentation(unittest.TestCase):
    def test_generated_catalog_matches_policy(self):
        from tool_policy import render_capabilities
        root = Path(__file__).resolve().parents[2]
        self.assertEqual((root / "docs/AGENT-CAPABILITIES.md").read_text(encoding="utf-8"), render_capabilities())


class ReadOnlyGit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for args in (("init", "-q"), ("config", "user.name", "test"), ("config", "user.email", "test@example.invalid")):
            self.git(*args)
        (self.root / "app.py").write_text("value = 1\n")
        self.git("add", "app.py")
        self.git("commit", "-qm", "seed")
        self.git("branch", "keep")
        self.git("tag", "keep")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=True).stdout

    def inspect(self, subcommand, *args):
        return o._product_git(subcommand, list(args), root=self.root)

    def test_normal_inspection_works(self):
        self.assertIn("seed", self.inspect("log", "--oneline", "-1"))
        self.assertIn("value", self.inspect("grep", "-n", "value", "--", "app.py"))
        self.assertIn("value", self.inspect("show", "HEAD:app.py"))
        self.assertIn("keep", self.inspect("branch", "-a"))
        self.assertIn("keep", self.inspect("tag"))
        self.assertIn("app.py", self.inspect("ls-tree", "--name-only", "HEAD"))
        self.assertIn("value", self.inspect("blame", "-L", "1,1", "--", "app.py"))

    def test_mutation_execution_and_file_escape_forms_are_rejected(self):
        before = self.git("show-ref")
        cases = [("branch", "-D", "keep"), ("branch", "-m", "renamed"), ("tag", "-d", "keep"),
                 ("grep", "--open-files-in-pager=echo bad", "value"), ("grep", "--open=echo bad", "value"),
                 ("grep", "-Oecho bad", "value"), ("grep", "--no-index", "value", "/tmp"),
                 ("grep", "-f", "/etc/passwd"), ("log", "--output=stolen"),
                 ("log", "--out=stolen"), ("diff", "--ext-diff"), ("show", "--textconv", "HEAD"),
                 ("blame", "--contents", "/etc/passwd", "app.py"),
                 ("show", "HEAD:.env"), ("show", "HEAD:../outside"),
                 ("ls-files", "--", ":(top)../outside"), ("rev-parse", "--resolve-git-dir", "/tmp")]
        for command, *args in cases:
            with self.subTest(command=command, args=args), self.assertRaises((ValueError, PermissionError)):
                self.inspect(command, *args)
        self.inspect("branch", "new-ref")
        self.inspect("tag", "new-ref")
        self.assertEqual(self.git("show-ref"), before)

    def test_optional_value_cannot_smuggle_an_output_flag(self):
        self.inspect("log", "--format", "--output=stolen")
        self.assertFalse((self.root / "stolen").exists())

    def test_protected_contents_are_excluded_from_search_history_and_wildcards(self):
        marker = "SYNTHETIC_CREDENTIAL_CANARY_489123"
        for name in (".env", "nested/.ENV.production", "private.key", "nested/.aws/credentials"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(marker + "\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture files")
        secret_blob = self.git("rev-parse", "HEAD:.env").strip()
        cases = [("show", "HEAD"), ("log", "-p"), ("grep", "-n", marker),
                 ("grep", "-e", marker, ".env"), ("grep", "-e", marker, "HEAD"),
                 ("show", "HEAD", "--", "*env"), ("show", "HEAD", "--", "*"),
                 ("diff", "HEAD~1", "HEAD"), ("show", secret_blob),
                 ("diff", secret_blob, "HEAD:app.py"),
                 ("show", "HEAD:app.py", "HEAD"), ("show", "--all")]
        for command, *args in cases:
            with self.subTest(command=command, args=args):
                try:
                    output = self.inspect(command, *args)
                except (ValueError, PermissionError):
                    continue
                self.assertNotIn(marker, output)
                self.assertNotIn("[stderr]", output)
        # Historical credentials remain excluded after their files are deleted.
        self.git("rm", ".env")
        self.git("commit", "-qm", "remove fixture")
        self.assertNotIn(marker, self.inspect("log", "-p"))

    def test_worktree_aliases_do_not_bypass_git_content_policy(self):
        secret = self.root / ".env"
        marker = "SYNTHETIC_LINK_CANARY_91834"
        secret.write_text(marker)
        (self.root / "app.py").unlink()
        os.link(secret, self.root / "app.py")
        self.assertNotIn(marker, self.inspect("grep", "-n", marker))
        self.assertNotIn(marker, self.inspect("diff"))
        with self.assertRaises(PermissionError):
            self.inspect("blame", "--", "app.py")

    def test_repository_config_cannot_execute_a_diff_driver_or_fsmonitor(self):
        self.git("config", "diff.external", "touch PWNED")
        self.git("config", "core.fsmonitor", "touch PWNED")
        (self.root / "app.py").write_text("changed\n")
        self.inspect("diff")
        self.inspect("status", "--short")
        self.assertFalse((self.root / "PWNED").exists())

    def test_global_line_ending_policy_does_not_create_false_changes(self):
        with tempfile.TemporaryDirectory() as settings:
            (Path(settings) / ".gitconfig").write_text("[core]\n    autocrlf = true\n")
            (self.root / "app.py").write_bytes(b"value = 1\r\n")
            with patch.dict(os.environ, {"HOME": settings}):
                self.assertEqual(self.git("diff"), "")
                self.assertIn("no output", self.inspect("diff"))
                self.assertEqual(factory.changed_files_since(self.root, None), [])


if __name__ == "__main__":
    unittest.main()
