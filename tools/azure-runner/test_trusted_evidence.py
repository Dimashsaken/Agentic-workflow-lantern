"""Adapter controls use disposable Git repos and an injected worker identity.

These test host authority logic; they do not claim Docker isolation or Azure QA.
"""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import tool_execution
import trusted_evidence as te
import factory
import execution_runtime


class TrustedEvidence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.product = self.root / "product"
        self.product.mkdir()
        for args in (("init", "-q"), ("config", "user.name", "Test"),
                     ("config", "user.email", "test@example.invalid"), ("config", "core.autocrlf", "false")):
            self.git(*args)
        (self.product / "source.py").write_text("print('test')\n")
        (self.product / "lantern.toml").write_text('[quality]\ntest = "python source.py"\n')
        self.git("add", "-A")
        self.git("commit", "-qm", "source")
        self.artifacts = self.root / "run"
        self.artifacts.mkdir()
        self.media = self.root / "media"
        self.media.mkdir()
        self.worker = SimpleNamespace(product_root=self.product.resolve(), output_root=self.media.resolve(),
                                      execution_key="feat-test:03-coding:1", image_id="sha256:" + "b" * 64,
                                      writable_product=False)
        token = tool_execution.CURRENT.set(self.worker)
        self.addCleanup(tool_execution.CURRENT.reset, token)
        self.env = patch.dict(os.environ, {"LANTERN_TRUSTED_EVIDENCE": "1",
                                          "LANTERN_AUTHORITY_DIR": str(self.root / "authority")})
        self.env.start()
        self.addCleanup(self.env.stop)
        # Product plumbing really runs against the disposable repository; only
        # routing and worker identity are injected instead of starting Docker.
        self._real_route = tool_execution.run
        def local_route(argv, **kwargs):
            if argv[0] == "bash" and argv[-1] == "python source.py":
                argv = [sys.executable, "source.py"]
            return subprocess.run(argv, **kwargs)
        route = patch.object(tool_execution, "run", side_effect=local_route)
        route.start()
        self.addCleanup(route.stop)
        self.before = te.capture_before(self.product)
        self.worker._frozen_source_identity = deepcopy(self.before)
        # Unit snapshot transport only: image isolation remains the opt-in Docker
        # test. The fixture still exercises tracked file/object rebuilding.
        class FixtureSnapshotWorker:
            def __init__(self, product_root, output_root, execution_key, image, writable_product=True, **kwargs):
                self.product_root, self.output_root = Path(product_root), Path(output_root)
                self.execution_key, self.image_id = execution_key, image
                self.writable_product = writable_product
            def run(self, command, timeout_s):
                if command != 'git -c safe.directory=/work/product -c core.fsmonitor=false read-tree HEAD':
                    raise AssertionError('fixture preparation may only form the index')
                return subprocess.run(['git', 'read-tree', 'HEAD'], cwd=self.product_root,
                                      capture_output=True, text=True, timeout=timeout_s)
            def stop(self):
                pass
        self.snapshot_worker_patch = patch.object(te, 'IsolatedToolWorker', FixtureSnapshotWorker)
        self.snapshot_worker_patch.start()
        self.addCleanup(self.snapshot_worker_patch.stop)
        self.contract = {"commands": [("test", "python source.py")],
                         "sha256": hashlib.sha256((self.product / "lantern.toml").read_bytes()).hexdigest()}
        self.gate = {"kind": "quality_gate", "run_id": "feat-test", "execution_key": "feat-test:03-coding:1",
                     "stage": "03-coding", "round": 0, "passed": True, "configured": ["test"],
                     "config_sha256": self.contract["sha256"], "ran_at": "2026-09-10T10:00:00Z",
                     "results": [{"name": "test", "command": "python source.py", "exit": 0,
                                  "passed": True, "seconds": 0.1, "output_tail": "test"}]}

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.product, capture_output=True, text=True, check=True).stdout.strip()

    def seal(self, **updates):
        kwargs = dict(gate=self.gate, root=self.product, contract=self.contract, before=self.before,
                      requirement_tests={"AC-1": ["quality:test"]}, expected_requirements=["AC-1"],
                      artifact_root=self.artifacts)
        kwargs.update(updates)
        return te.seal_gate(**kwargs)

    def verify(self, gate):
        return te.verify_gate(gate, self.product, "feat-test", "feat-test:03-coding:1", ["AC-1"])

    def test_valid_gate_is_sealed_and_loaded_only_from_authority(self):
        gate = self.seal()
        self.assertTrue(gate["passed"], gate)
        self.assertEqual(self.verify(gate), [])
        loaded, error = te.load_gate("feat-test", "feat-test:03-coding:1")
        self.assertIsNone(error)
        self.assertEqual(loaded, gate)
        self.assertFalse((self.artifacts / "gate.json").exists())

    def test_writable_product_cannot_seal_quality_evidence(self):
        self.worker.writable_product = True
        gate = self.seal()
        self.assertFalse(gate['passed'])
        self.assertIn('read-only committed snapshot', gate['provenance']['error'])

    def test_snapshot_omits_ignored_dependencies_and_copies_no_git_hooks(self):
        (self.product / '.gitignore').write_text('ignored-helper.py\n')
        self.git('add', '.gitignore')
        self.git('commit', '-qm', 'ignore fixture')
        (self.product / 'ignored-helper.py').write_text('raise RuntimeError("untracked")\n')
        hooks = self.product / '.git/hooks'
        hooks.mkdir(exist_ok=True)
        (hooks / 'post-checkout').write_text('malicious hook')
        with te.quality_snapshot(self.product) as snapshot:
            self.assertFalse(snapshot.worker.writable_product)
            self.assertFalse((snapshot.root / 'ignored-helper.py').exists())
            self.assertFalse((snapshot.root / '.git/hooks').exists())
            self.assertEqual((snapshot.root / 'source.py').read_bytes(), (self.product / 'source.py').read_bytes())
            self.assertNotEqual(snapshot.root, self.product)
            self.assertEqual(snapshot.before, te.capture_before(self.product))

    def test_snapshot_hash_checks_refuse_changed_blob_during_copy(self):
        before = te.capture_before(self.product)
        destination = self.root / 'snapshot'
        destination.mkdir()
        (self.product / 'source.py').write_text('changed after capture')
        with self.assertRaisesRegex(ValueError, 'differs from committed'):
            te._snapshot_files(self.product, destination, before)

    def test_flag_off_preserves_existing_behavior_without_authority(self):
        with patch.dict(os.environ, {"LANTERN_TRUSTED_EVIDENCE": "0"}):
            self.assertFalse(te.enabled())
            self.assertEqual(self.seal(), self.gate)
        self.assertIsNotNone(te.load_gate("feat-test", "feat-test:03-coding:1")[1])

    def test_capture_requires_matching_bound_isolated_worker(self):
        token = tool_execution.CURRENT.set(None)
        try:
            with self.assertRaisesRegex(ValueError, "bound isolated"):
                te.capture_before(self.product)
            self.assertFalse(self.seal()["passed"])
        finally:
            tool_execution.CURRENT.reset(token)

    def test_missing_links_fail_and_replace_previous_green_authority(self):
        self.assertTrue(self.seal()["passed"])
        gate = self.seal(requirement_tests={})
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["results"][-1]["name"], "config")
        self.assertEqual(te.load_gate("feat-test", "feat-test:03-coding:1")[0], gate)
        self.assertTrue(self.verify(gate))

    def test_source_mutation_after_test_fails_and_records_red_authority(self):
        self.assertTrue(self.seal()["passed"])
        (self.product / "source.py").write_text("changed")
        gate = self.seal()
        self.assertFalse(gate["passed"])
        self.assertIn("differs from committed", gate["provenance"]["error"])
        self.assertFalse(te.load_gate("feat-test", "feat-test:03-coding:1")[0]["passed"])

    def test_display_mirror_cannot_supply_authority(self):
        gate = self.seal()
        changed = deepcopy(gate)
        changed["results"][0]["output_tail"] = "fabricated evidence"
        (self.artifacts / "gate.json").write_text(json.dumps(changed))
        self.assertTrue(self.verify(changed))
        self.assertEqual(self.verify(gate), [])

    def test_cross_execution_gate_or_worker_is_rejected(self):
        gate = self.seal()
        self.assertTrue(te.verify_gate(gate, self.product, "feat-test", "key-other", ["AC-1"]))
        self.worker.execution_key = "key-other"
        self.assertFalse(self.seal()["passed"])

    def test_worker_mount_or_harness_cannot_hold_authority(self):
        for root in (self.product, self.media / "authority", te.REPO / "authority"):
            with self.subTest(root=root), patch.dict(os.environ, {"LANTERN_AUTHORITY_DIR": str(root)}):
                with self.assertRaisesRegex(ValueError, "overlaps"):
                    te.authority_root()
                self.assertFalse(self.seal()["passed"])

    def test_controller_logs_cannot_be_worker_writable(self):
        for root in (self.product, self.media):
            with self.subTest(root=root):
                gate = self.seal(artifact_root=root)
                self.assertFalse(gate["passed"])
                self.assertIn("outside worker mounts", gate["provenance"]["error"])

    def test_changed_policy_and_command_outcomes_fail(self):
        changed = deepcopy(self.gate)
        changed["results"][0]["command"] = "echo green"
        self.assertFalse(self.seal(gate=changed)["passed"])
        changed = deepcopy(self.gate)
        changed["results"][0]["exit"] = 1
        self.assertFalse(self.seal(gate=changed)["passed"])
        (self.product / "lantern.toml").write_text('[quality]\ntest = "echo green"\n')
        self.assertFalse(self.seal()["passed"])

    def test_summary_cannot_hide_nonquality_failure(self):
        changed = deepcopy(self.gate)
        changed["results"].append({"name": "write-scope", "command": "scope check", "exit": 1,
                                   "passed": False, "seconds": 0, "output_tail": "outside scope"})
        gate = self.seal(gate=changed)
        self.assertFalse(gate["passed"])
        self.assertIn("summary contradicts", gate["provenance"]["error"])

    def test_observed_failure_retains_manifest_without_claiming_coverage(self):
        changed = deepcopy(self.gate)
        changed["passed"] = False
        changed["results"][0].update(exit=1, passed=False, output_tail="assertion failed")
        gate = self.seal(gate=changed)
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["provenance"]["status"], "verified")
        self.assertIn("failing tests", " ".join(self.verify(gate)))

    def test_fix_rounds_preserve_distinct_manifests_and_latest_gate(self):
        first = self.seal()
        self.gate["round"] = 1
        second = self.seal()
        self.assertNotEqual(first["provenance"]["manifest"]["path"], second["provenance"]["manifest"]["path"])
        self.assertTrue(Path(first["provenance"]["manifest"]["path"]).is_file())
        self.assertEqual(te.load_gate("feat-test", "feat-test:03-coding:1")[0], second)
        self.assertTrue(self.verify(first))
        self.assertEqual(self.verify(second), [])

    def test_logs_and_manifest_are_revalidated_from_protected_receipt(self):
        gate = self.seal()
        manifest_path = Path(gate["provenance"]["manifest"]["path"])
        manifest = json.loads(manifest_path.read_text())
        log = Path(gate["provenance"]["artifact_root"]) / manifest["artifacts"][0]["path"]
        log.write_text("tampered")
        self.assertTrue(self.verify(gate))
        manifest_path.write_text("{}")
        self.assertIn("authoritative digest", " ".join(self.verify(gate)))

    def test_missing_or_changed_expected_requirements_fail(self):
        self.assertFalse(self.seal(expected_requirements=[])["passed"])
        self.assertFalse(self.seal(requirement_tests={"AC-1": ["fictional:test"]})["passed"])
        gate = self.seal()
        self.assertTrue(te.verify_gate(gate, self.product, "feat-test", "feat-test:03-coding:1", ["AC-2"]))

    def test_attempt_and_lease_identity_are_separate_from_quality_round(self):
        lease = SimpleNamespace(run_id="feat-test", owner="dispatcher", execution_id=7, fence=3, parent_fence=2)
        ownership = SimpleNamespace(lease=lease)
        token = execution_runtime.STAGE.set(ownership)
        try:
            changed = deepcopy(self.gate)
            changed["round"] = 8
            gate = self.seal(gate=changed)
            self.assertTrue(gate["passed"], gate)
            self.assertEqual(gate["provenance"]["identity"]["attempt"], 1)
            self.assertEqual(gate["provenance"]["identity"]["lease_token"], "dispatcher:7:3:2")
            self.assertEqual(self.verify(gate), [])
            lease.fence = 4
            self.assertIn("fence is stale", " ".join(self.verify(gate)))
        finally:
            execution_runtime.STAGE.reset(token)

    def test_lease_mode_cannot_seal_without_owned_stage(self):
        with patch.dict(os.environ, {"LANTERN_EXECUTION_LEASES": "1"}):
            gate = self.seal()
        self.assertFalse(gate["passed"])
        self.assertIn("no stage lease", gate["provenance"]["error"])


class FactoryGateHooks(unittest.TestCase):
    setUp = TrustedEvidence.setUp
    git = TrustedEvidence.git

    def prepare(self):
        mock = patch.object(factory, "REPO", self.root / "controller")
        mock.start()
        self.addCleanup(mock.stop)
        run = factory.run_dir("feat-test")
        (run / "00-story").mkdir(parents=True)
        (run / "00-story/story.json").write_text(json.dumps({"acceptance_criteria": [{"id": "AC-1"}]}))
        (run / "02-pre-coding").mkdir()
        (run / "02-pre-coding/plan.json").write_text(json.dumps({"write_scope": ["**"],
                                                               "requirement_tests": {"AC-1": ["quality:test"]}}))
        return run

    def test_factory_runs_actual_command_then_ignores_tampered_mirror(self):
        run = self.prepare()
        gate = factory.run_quality_gate("feat-test", "03-coding", self.product, self.worker.execution_key, 0)
        self.assertTrue(gate["passed"], gate)
        self.assertEqual(factory.check_quality_gate("feat-test", "03-coding", self.worker.execution_key), [])
        (run / "03-coding/gate.json").write_text('{"passed":false}')
        self.assertEqual(factory.check_quality_gate("feat-test", "03-coding", self.worker.execution_key), [])
        (self.product / "source.py").write_text("changed")
        self.assertTrue(factory.check_quality_gate("feat-test", "03-coding", self.worker.execution_key))

    def test_dirty_pretest_capture_prevents_command_execution(self):
        self.prepare()
        (self.product / "source.py").write_text("changed")
        with patch.object(factory, "run_command") as command:
            gate = factory.run_quality_gate("feat-test", "03-coding", self.product, self.worker.execution_key, 0)
        command.assert_not_called()
        self.assertFalse(gate["passed"])

    def test_missing_plan_links_hold_a_green_command(self):
        run = self.prepare()
        (run / "02-pre-coding/plan.json").write_text('{"write_scope":["**"]}')
        gate = factory.run_quality_gate("feat-test", "03-coding", self.product, self.worker.execution_key, 0)
        self.assertFalse(gate["passed"])
        self.assertIn("planned requirement", gate["provenance"]["error"])

    def test_optional_plan_links_have_a_typed_contract(self):
        self.prepare()
        plan = {"tasks": [{"id": 1, "title": "change", "criteria": ["AC-1"]}],
                "write_scope": ["**"], "schema_changes": False, "hitl_required": False}
        self.assertEqual(factory._check_plan(plan, "feat-test", self.product), [])
        for mapping in ([], {"AC-9": ["quality:test"]}, {"AC-1": ["fictional:test"]}, {"AC-1": []}):
            self.assertTrue(factory._check_plan({**plan, "requirement_tests": mapping}, "feat-test", self.product))

    @unittest.skipUnless(os.environ.get("LANTERN_LIVE_EVIDENCE_TEST") == "1", "explicit live Docker proof only")
    def test_real_isolated_worker_quality_gate_and_tamper_controls(self):
        # Only this opt-in case starts real Docker. No Azure model or live gate.
        from isolated_tools import IsolatedToolWorker
        self.prepare()
        (self.product / 'source.py').write_text("from pathlib import Path\nassert not Path('ignored-helper.py').exists()\nprint('test')\n")
        (self.product / '.gitignore').write_text('ignored-helper.py\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'tracked-only live snapshot proof')
        (self.product / 'ignored-helper.py').write_text('untracked dependency\n')
        source_bytes = (self.product / 'source.py').read_bytes()
        # Remove the unit routing injection installed by setUp.
        tool_execution.run = self._real_route
        self.snapshot_worker_patch.stop()
        worker = IsolatedToolWorker(self.product, self.media, self.worker.execution_key,
                                    os.environ.get("LANTERN_TOOL_IMAGE", "lantern-sandbox:agentic-infrastructure"))
        worker.start()
        token = tool_execution.CURRENT.set(worker)
        try:
            probe = tool_execution.run(["git", "-c", "core.fsmonitor=false", "rev-parse", "HEAD"],
                                       cwd=self.product, text=True, capture_output=True)
            self.assertEqual(probe.returncode, 0, probe.stderr)
            gate = factory.run_quality_gate("feat-test", "03-coding", self.product, worker.execution_key, 0)
            self.assertTrue(gate["passed"], gate)
            self.assertEqual(factory.check_quality_gate("feat-test", "03-coding", worker.execution_key), [])
            manifest = json.loads(Path(gate["provenance"]["manifest"]["path"]).read_text())
            self.assertEqual(manifest["image_digest"], worker.image_id)
            self.assertEqual(manifest["attempt"], 1)
            self.assertEqual(manifest['tested_source']['kind'], 'read-only-committed-snapshot')
            self.assertIn("dirty", manifest["harness_state"])
            manifest_path = Path(gate["provenance"]["manifest"]["path"])
            manifest_bytes = manifest_path.read_bytes()
            manifest_path.write_text("{}")
            self.assertIn("authoritative digest", " ".join(factory.check_quality_gate(
                "feat-test", "03-coding", worker.execution_key)))
            manifest_path.write_bytes(manifest_bytes)
            (self.product / "source.py").write_text("tampered")
            self.assertTrue(factory.check_quality_gate("feat-test", "03-coding", worker.execution_key))
            (self.product / 'source.py').write_bytes(source_bytes)
            # This command is green on a mutable checkout: it tests replaced source
            # and restores it before capture. The immutable snapshot must refuse.
            (self.product / 'mutate_restore.py').write_text(
                "from pathlib import Path\np=Path('source.py')\noriginal=p.read_bytes()\n"
                "try:\n p.write_text(\"print('forged pass')\\n\")\n exec(p.read_text())\n"
                "finally:\n p.write_bytes(original)\n")
            (self.product / 'lantern.toml').write_text('[quality]\ntest = "python mutate_restore.py"\n')
            self.git('add', '-A')
            self.git('commit', '-qm', 'temporary source mutation negative control')
            with patch.dict(os.environ, {'LANTERN_TRUSTED_EVIDENCE':'0'}):
                mutable_gate = factory.run_quality_gate('feat-test', '03-coding', self.product, worker.execution_key, 1)
            self.assertTrue(mutable_gate['passed'], mutable_gate)
            frozen_gate = factory.run_quality_gate('feat-test', '03-coding', self.product, worker.execution_key, 2)
            self.assertFalse(frozen_gate['passed'], frozen_gate)
            test_result = next(result for result in frozen_gate['results'] if result['name'] == 'test')
            self.assertNotEqual(test_result['exit'], 0)
            self.assertIn('Read-only file system', test_result['output_tail'])
            self.assertEqual((self.product / 'source.py').read_bytes(), source_bytes)
            print(json.dumps({"kind": "real-isolated-quality-evidence", "image_digest": worker.image_id,
                              "tested_product": manifest["product"], "harness_state": gate["provenance"]["harness_state"],
                              "execution_key": worker.execution_key, "manifest_sha256": gate["provenance"]["manifest"]["sha256"],
                              "command": manifest["tests"][0], "valid_gate": True,
                              "changed_manifest_rejected": True, "changed_source_rejected": True,
                              "ignored_dependencies_excluded": True,
                              "mutable_modify_restore_passed": mutable_gate['passed'],
                              "readonly_modify_restore_rejected": not frozen_gate['passed'],
                              "readonly_command_result": test_result,
                              "source_preserved_for_fix_loop": True,
                              "azure_used": False, "database_used": False}))
        finally:
            tool_execution.CURRENT.reset(token)
            worker.stop()


if __name__ == "__main__":
    unittest.main()
