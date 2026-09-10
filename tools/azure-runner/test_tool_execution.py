"""Product routing: isolation fails closed and binary Git results stay exact."""
import base64
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import tool_execution as execution
from isolated_tools import IsolationError


class Routing(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.product, self.media = self.root / "product", self.root / "media"
        self.product.mkdir()
        self.media.mkdir()
        self.worker = SimpleNamespace(product_root=self.product, output_root=self.media,
            run=Mock(return_value=subprocess.CompletedProcess([], 0, "ok", "")))
        self.env = patch.dict(os.environ, {"LANTERN_ISOLATED_TOOLS": "0", "LANTERN_EXECUTOR": "inprocess"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.token = execution.CURRENT.set(None)
        self.addCleanup(execution.CURRENT.reset, self.token)

    def bind(self):
        execution.CURRENT.set(self.worker)

    def envelope(self, stdout=b"", stderr=b"", code=0):
        self.worker.run.return_value = subprocess.CompletedProcess([], code, json.dumps({
            "version": 1, "stdout": base64.b64encode(stdout).decode(),
            "stderr": base64.b64encode(stderr).decode()}), "")

    def test_legacy_host_execution_remains_explicit_when_isolation_disabled(self):
        with patch("tool_execution.subprocess.run") as host:
            execution.run(["git", "status"], cwd=self.product, capture_output=True)
        host.assert_called_once()

    def test_enabled_without_worker_never_runs_product_on_host(self):
        for cwd in (None, self.product):
            with patch.dict(os.environ, {"LANTERN_ISOLATED_TOOLS": "1"}), patch(
                    "tool_execution.subprocess.run") as host, self.assertRaises(IsolationError):
                execution.run(["git", "status"], cwd=cwd)
            host.assert_not_called()

    def test_bound_worker_disallows_sibling_cwd_even_without_environment_flag(self):
        self.bind()
        with patch("tool_execution.subprocess.run") as host, self.assertRaises(IsolationError):
            execution.run(["git", "status"], cwd=self.media)
        host.assert_not_called()

    def test_product_subdirectory_and_media_arguments_translate(self):
        self.bind()
        child = self.product / "sub dir"
        child.mkdir()
        execution.run(["cat", self.media / "a file"], cwd=child, text=True)
        command = self.worker.run.call_args.args[0]
        self.assertIn("cd '/work/product/sub dir'", command)
        self.assertIn("'/work/media/a file'", command)
        self.assertNotIn(str(self.root), command)

    def test_safe_git_controls_cannot_be_weakened_and_secrets_do_not_cross(self):
        self.bind()
        env = {"GIT_NO_REPLACE_OBJECTS": "0", "GIT_CONFIG_GLOBAL": "/secret/config",
               "AZURE_OPENAI_API_KEY": "synthetic-secret", "DATABASE_URL": "synthetic-db",
               "LD_PRELOAD": "/malicious.so", "GIT_CONFIG_COUNT": "1",
               "GIT_AUTHOR_NAME": "test author"}
        execution.run(["git", "show", "HEAD"], cwd=self.product, text=True, env=env)
        command = self.worker.run.call_args.args[0]
        self.assertIn("GIT_NO_REPLACE_OBJECTS=1", command)
        self.assertIn("GIT_CONFIG_GLOBAL=/dev/null", command)
        self.assertIn("GIT_AUTHOR_NAME=test author", command)
        for forbidden in ("synthetic-secret", "synthetic-db", "LD_PRELOAD", "GIT_CONFIG_COUNT", "/secret/config"):
            self.assertNotIn(forbidden, command)

    def test_temporary_index_rejects_outside_product(self):
        self.bind()
        with self.assertRaises(IsolationError):
            execution.run(["git", "add", "."], cwd=self.product, text=True,
                          env={"GIT_INDEX_FILE": str(self.media / "index")})
        self.worker.run.assert_not_called()

    def test_binary_blob_and_stderr_are_exact_including_non_utf8_and_nul(self):
        self.bind()
        binary = bytes(range(256)) + b"\0\r\n\xff"
        self.envelope(binary, b"\x80error\x00")
        result = execution.run(["git", "show", "HEAD:asset.bin"], cwd=self.product, capture_output=True)
        self.assertEqual(result.stdout, binary)
        self.assertEqual(result.stderr, b"\x80error\x00")
        payload = json.loads(base64.b64decode(shlex.split(self.worker.run.call_args.args[0])[-1]))
        self.assertEqual(payload["argv"], ["git", "-c", "safe.directory=/work/product", "show", "HEAD:asset.bin"])
        self.assertEqual(shlex.split(self.worker.run.call_args.args[0])[:3],
                         ["/opt/lantern/venv/bin/python", "-I", "-c"])

    def test_binary_stdin_and_shell_metacharacters_are_data(self):
        self.bind()
        self.envelope()
        argument = "$(touch /outside); 'quotes' & more"
        execution.run(["test", argument], cwd=self.product, input=b"\xff\x00\r\n")
        payload = json.loads(base64.b64decode(shlex.split(self.worker.run.call_args.args[0])[-1]))
        self.assertEqual(payload["argv"], ["test", argument])
        self.assertEqual(base64.b64decode(payload["input"]), b"\xff\x00\r\n")

    def test_truncated_or_fabricated_binary_transport_fails_closed(self):
        self.bind()
        for invalid in ('tail only', '{"version":1,"stdout":"??","stderr":""}',
                        '{"version":1,"stdout":"","stderr":"","passed":true}'):
            self.worker.run.return_value = subprocess.CompletedProcess([], 0, invalid, "")
            with self.subTest(invalid=invalid), self.assertRaises(IsolationError):
                execution.run(["git", "show"], cwd=self.product)

    def test_check_preserves_binary_failure_evidence_and_original_arguments(self):
        self.bind()
        self.envelope(b"\xff", b"error", 3)
        with self.assertRaises(subprocess.CalledProcessError) as raised:
            execution.run(["git", "bad"], cwd=self.product, check=True)
        self.assertEqual(raised.exception.cmd, ["git", "bad"])
        self.assertEqual(raised.exception.output, b"\xff")
        self.assertEqual(raised.exception.stderr, b"error")

    def test_shell_or_host_file_descriptors_are_not_silently_accepted(self):
        self.bind()
        for kwargs in ({"shell": True}, {"stdin": 40}, {"stdout": 41}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                execution.run(["git", "status"], cwd=self.product, **kwargs)

    def test_file_routing_is_lexical_and_cannot_follow_a_post_policy_swap(self):
        self.bind()
        selected = self.product / "directory" / "file.txt"
        with patch.object(Path, "resolve", side_effect=AssertionError("host resolution after policy")):
            self.assertEqual(execution.file_route(selected), ("/work/product", ("directory", "file.txt")))
            self.assertEqual(execution.file_route(self.media / "capture.txt"), ("/work/media", ("capture.txt",)))

    def test_worker_file_operations_require_binding_but_host_artifacts_stay_host(self):
        with patch.dict(os.environ, {"LANTERN_ISOLATED_TOOLS": "1"}):
            with self.assertRaises(IsolationError):
                execution.file_route(self.product / "app.py", product_root=self.product)
        self.bind()
        self.assertIsNone(execution.file_route(self.root / "controller" / "report.md", product_root=self.product))
        with self.assertRaises(IsolationError):
            execution.file_io("read", self.root / "controller" / "report.md")

    def test_worker_file_read_uses_isolated_python_and_base64(self):
        self.bind()
        self.worker.run.return_value = subprocess.CompletedProcess([], 0, json.dumps({
            "ok": True, "value": base64.b64encode("hello \u2603".encode()).decode()}), "")
        self.assertEqual(execution.file_io("read", self.product / "file.txt"), "hello \u2603")
        command = shlex.split(self.worker.run.call_args.args[0])
        self.assertEqual(command[:3], ["/opt/lantern/venv/bin/python", "-I", "-c"])
        payload = json.loads(base64.b64decode(command[-1]))
        self.assertEqual(payload["parts"], ["file.txt"])
        self.assertNotIn(str(self.root), self.worker.run.call_args.args[0])

    def test_worker_file_refusal_is_not_followed_by_host_io(self):
        self.bind()
        self.worker.run.return_value = subprocess.CompletedProcess([], 1, json.dumps({
            "ok": False, "error": "PermissionError", "message": "symlink denied"}), "")
        with patch.object(Path, "read_text") as host, self.assertRaises(PermissionError):
            execution.file_io("read", self.product / "file.txt")
        host.assert_not_called()


if __name__ == "__main__":
    unittest.main()
