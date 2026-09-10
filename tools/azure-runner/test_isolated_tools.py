"""Boundary construction and lifecycle failure controls (no Docker required)."""

import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from isolated_tools import IsolatedToolWorker, IsolationError, _bounded_run, cleanup_execution


IMAGE = "sha256:" + "a" * 64
CONTAINER = "b" * 64


class Workers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.product, self.media, self.authority = [self.root / name for name in
                                                  ("product", "media", "authority")]
        for root in (self.product, self.media, self.authority):
            root.mkdir()

    def worker(self, **kwargs):
        return IsolatedToolWorker(self.product, self.media, "execution", "image", **kwargs)

    def docker(self, argv, **kwargs):
        if argv[1:3] == ["image", "inspect"]:
            output = json.dumps([{"Id": IMAGE, "Config": {"Env": ["PATH=/usr/bin"]}}])
        else:
            output = CONTAINER
        return subprocess.CompletedProcess(argv, 0, output, "")

    def test_only_explicit_target_credentials_allowed(self):
        for key in ("AZURE_OPENAI_API_KEY", "DATABASE_URL", "DOCKER_HOST", "PATH", "QA_BASE_URL"):
            with self.subTest(key=key), self.assertRaises(IsolationError):
                self.worker(target_env={key: "value"})
        worker = self.worker(target_env={"QA_USER": "test", "QA_PASS": "target-only"})
        self.assertIn("QA_USER=test", worker._env_args())

    def test_unapproved_network_fails_with_supported_scope(self):
        with self.assertRaisesRegex(IsolationError, "approved allowlisted proxy"):
            self.worker(network="bridge")

    def test_overlapping_authority_or_mounts_rejected(self):
        with self.assertRaises(IsolationError):
            self.worker(protected_roots=[self.root])
        with self.assertRaises(IsolationError):
            IsolatedToolWorker(self.product, self.product, "key", "image")
        self.worker(protected_roots=[self.authority])

    def test_readonly_product_and_kernel_boundaries(self):
        args = self.worker(writable_product=False)._args("name")
        self.assertIn("--read-only", args)
        self.assertIn("--cap-drop=ALL", args)
        self.assertIn("--security-opt=no-new-privileges", args)
        self.assertEqual(args[args.index("--network") + 1], "none")
        self.assertEqual(args[args.index("--user") + 1], "1000:1000")
        self.assertEqual(args.count("--mount"), 2)
        self.assertTrue(any(arg.endswith("target=/work/product,readonly") for arg in args))
        self.assertNotIn(str(self.authority), " ".join(args))

    def test_mcp_uses_exact_container_and_clean_environment(self):
        worker = self.worker()
        with self.assertRaises(IsolationError):
            worker.mcp_command(["python", "-V"])
        with patch("isolated_tools.subprocess.run", side_effect=self.docker):
            worker.start()
            command = worker.mcp_command(["python", "-V"])
            self.assertEqual(command[:6], ["docker", "exec", "-i", CONTAINER, "/usr/bin/env", "-i"])
            worker.stop()
        with self.assertRaises(IsolationError):
            worker.mcp_command(["python", "-V"])

    def test_image_is_pinned_and_reused(self):
        worker = self.worker()
        with patch("isolated_tools.subprocess.run", side_effect=self.docker) as run:
            worker.start()
            worker.start()
            self.assertEqual(worker.image_id, IMAGE)
            self.assertEqual(sum(call.args[0][1:3] == ["image", "inspect"]
                                 for call in run.call_args_list), 1)
            self.assertIn(IMAGE, run.call_args_list[-1].args[0])
            worker.stop()

    def test_images_with_implicit_volumes_or_environment_rejected(self):
        for config in ({"Volumes": {"/secret": {}}}, {"Env": ["DATABASE_URL=secret"]}):
            result = subprocess.CompletedProcess([], 0, json.dumps([
                {"Id": IMAGE, "Config": config}]), "")
            with patch("isolated_tools.subprocess.run", return_value=result), self.assertRaises(IsolationError):
                self.worker().start()

    def test_success_and_failed_commands_both_force_remove_container(self):
        for code in (0, 7):
            worker = self.worker()
            with patch("isolated_tools.subprocess.run", side_effect=self.docker) as docker:
                with patch("isolated_tools._bounded_run", return_value=
                           subprocess.CompletedProcess([], code, "out", "err")):
                    result = worker.run("exit " + str(code))
                self.assertEqual(result.returncode, code)
                self.assertEqual(docker.call_args.args[0][:3], ["docker", "rm", "--force"])
                self.assertEqual(worker._names, set())

    def test_timeout_and_interrupt_force_remove_container(self):
        for error in (subprocess.TimeoutExpired("test", 1), KeyboardInterrupt()):
            worker = self.worker()
            with patch("isolated_tools.subprocess.run", side_effect=self.docker) as docker:
                with patch("isolated_tools._bounded_run", side_effect=error):
                    with self.assertRaises(type(error)):
                        worker.run("sleep 300", 1)
                self.assertEqual(docker.call_args.args[0][:3], ["docker", "rm", "--force"])

    def test_failed_cleanup_is_visible_and_retryable(self):
        worker = self.worker()
        worker._names.add("test")
        result = subprocess.CompletedProcess([], 1, "", "daemon unreachable")
        with patch("isolated_tools.subprocess.run", return_value=result):
            with self.assertRaises(IsolationError):
                worker.stop()
        self.assertEqual(worker._names, {"test"})
        with patch("isolated_tools.subprocess.run", side_effect=self.docker):
            worker.stop()
        self.assertEqual(worker._names, set())

    def test_create_failure_attempts_cleanup_before_returning(self):
        worker = self.worker()
        worker.image_id = IMAGE
        failure = subprocess.CalledProcessError(1, ["docker", "create"])
        with patch("isolated_tools.subprocess.run", side_effect=[failure,
                   subprocess.CompletedProcess([], 0, "", "")]) as docker:
            with self.assertRaises(subprocess.CalledProcessError):
                worker.run("true")
        self.assertEqual(docker.call_args.args[0][:3], ["docker", "rm", "--force"])
        self.assertEqual(worker._names, set())

    def test_cleanup_can_interrupt_an_active_command_without_late_creation(self):
        import threading
        worker = self.worker()
        started, stopped = threading.Event(), threading.Event()

        def run_command(argv, timeout):
            started.set()
            self.assertTrue(stopped.wait(5))
            return subprocess.CompletedProcess(argv, 137, "", "")

        with patch("isolated_tools.subprocess.run", side_effect=self.docker) as docker:
            with patch("isolated_tools._bounded_run", side_effect=run_command):
                thread = threading.Thread(target=lambda: worker.run("sleep 300"))
                thread.start()
                self.assertTrue(started.wait(5))
                worker.stop()
                stopped.set()
                thread.join(5)
                self.assertFalse(thread.is_alive())
            commands = [call.args[0][1] for call in docker.call_args_list]
        self.assertLess(commands.index("create"), commands.index("rm"))
        self.assertEqual(worker._names, set())

    def test_stopped_worker_cannot_launch(self):
        worker = self.worker()
        worker.image_id = IMAGE
        worker.stop()
        with self.assertRaises(IsolationError):
            worker.run("echo bad")

    def test_invalid_command_timeout_or_mcp_args_rejected(self):
        worker = self.worker()
        for command, timeout in (("", 1), ("x\0", 1), ("true", 0), ("true", True)):
            with self.assertRaises(ValueError):
                worker.run(command, timeout)
        with self.assertRaises(ValueError):
            worker.mcp_command([])

    def test_output_is_bounded_but_both_pipes_are_drained(self):
        import sys
        result = _bounded_run([sys.executable, "-c", "import sys; "
                               "sys.stdout.write('x'*300000); sys.stderr.write('y'*300000)"], 10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "x" * 128000)
        self.assertEqual(result.stderr, "y" * 128000)

    def test_recovery_cleanup_verifies_exact_execution_labels_before_removing(self):
        labels = {"lantern.tool-worker": "true", "lantern.execution-key":
                  hashlib.sha256(b"lost-key").hexdigest()}
        results = [subprocess.CompletedProcess([], 0, CONTAINER + "\n", ""),
                   subprocess.CompletedProcess([], 0, json.dumps([
                       {"Id": CONTAINER, "Config": {"Labels": labels}}]), ""),
                   subprocess.CompletedProcess([], 0, "", "")]
        with patch("isolated_tools.subprocess.run", side_effect=results) as docker:
            self.assertEqual(cleanup_execution("lost-key"), [CONTAINER])
        self.assertIn("label=lantern.execution-key=" + labels["lantern.execution-key"],
                      docker.call_args_list[0].args[0])
        self.assertEqual(docker.call_args.args[0], ["docker", "rm", "--force", CONTAINER])

    def test_recovery_cleanup_refuses_wrong_labels_or_ambiguous_ids(self):
        for candidate in (CONTAINER[:12], CONTAINER):
            results = [subprocess.CompletedProcess([], 0, candidate, ""),
                       subprocess.CompletedProcess([], 0, json.dumps([
                           {"Id": CONTAINER, "Config": {"Labels": {}}}]), "")]
            with patch("isolated_tools.subprocess.run", side_effect=results) as docker:
                with self.assertRaises(IsolationError):
                    cleanup_execution("lost-key")
            self.assertFalse(any(call.args[0][1] == "rm" for call in docker.call_args_list))

    def test_recovery_cleanup_requires_execution_and_is_idempotent_after_removal(self):
        with self.assertRaises(ValueError):
            cleanup_execution("")
        with patch("isolated_tools.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, "", "")) as docker:
            self.assertEqual(cleanup_execution("lost-key"), [])
        self.assertEqual(docker.call_count, 1)


if __name__ == "__main__":
    unittest.main()
