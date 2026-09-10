"""Disposable-repository controls for execution-bound host evidence."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import evidence_manifest as em


class EvidenceManifest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.product = self.root / "product"
        self.product.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Evidence Test")
        self.git("config", "core.autocrlf", "false")
        (self.product / "app.py").write_bytes(b"print('hello')\n")
        (self.product / "lantern.toml").write_text('[quality]\ntest = "python app.py"\n')
        self.commit()
        self.artifacts = self.root / "run" / "03-coding"
        self.artifacts.mkdir(parents=True)
        (self.artifacts / "test.txt").write_text("test=pass\n")
        self.before = em.capture_product_state(self.product)
        self.kwargs = dict(run_id="feat-test", execution_key="execution-1", stage="03-coding",
                           attempt=0, lease_token=None, product=self.product, product_before=self.before,
                           harness_revision="a" * 40, image_digest="sha256:" + "b" * 64,
                           quality_policy_sha256=hashlib.sha256((self.product / "lantern.toml").read_bytes()).hexdigest(),
                           tests=[{"id": "quality:test", "command": "python app.py", "exit_code": 0, "outcome": "pass"}],
                           requirement_tests={"AC-1": ["quality:test"]}, artifact_root=self.artifacts,
                           artifacts=[{"path": "test.txt"}])

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.product, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "source")

    def build(self, **updates):
        return em.build_manifest(**{**self.kwargs, **updates})

    def receipt(self, manifest):
        return em.publish_manifest(self.root / "authority", manifest,
                                   writable_roots=[self.product, self.artifacts])

    def verify(self, manifest, *, expected=None, requirements=("AC-1",), **updates):
        receipt = self.receipt(manifest)
        identity = {k: manifest[k] for k in (*em.IDENTITY_FIELDS, "product")}
        return em.verify_manifest(Path(receipt["path"]), expected_sha256=receipt["sha256"],
                                  expected_identity=expected or identity, product=self.product,
                                  artifact_root=self.artifacts, expected_requirements=requirements, **updates)

    def test_valid_controller_record_and_idempotent_publish(self):
        manifest = self.build()
        self.assertEqual(self.verify(manifest), [])
        self.assertEqual(self.receipt(manifest), self.receipt(manifest))

    def test_source_edits_fail_even_when_index_flags_hide_them(self):
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                self.git("update-index", flag, "app.py")
                (self.product / "app.py").write_bytes(b"print('changed')\n")
                with self.assertRaisesRegex(ValueError, "differs from committed"):
                    self.build()
                (self.product / "app.py").write_bytes(b"print('hello')\n")
                self.git("update-index", "--no-assume-unchanged", "--no-skip-worktree", "app.py")

    def test_staged_and_untracked_sources_are_not_a_tested_commit(self):
        (self.product / "extra.py").write_text("source")
        with self.assertRaisesRegex(ValueError, "clean and committed"):
            self.build()
        self.git("add", "extra.py")
        with self.assertRaisesRegex(ValueError, "clean and committed"):
            self.build()

    def test_post_test_commit_is_rejected_even_when_clean(self):
        (self.product / "app.py").write_text("changed")
        self.commit()
        with self.assertRaisesRegex(ValueError, "changed after"):
            self.build()

    def test_mutation_after_publication_is_rejected(self):
        manifest = self.build()
        (self.product / "app.py").write_text("changed")
        self.assertIn("differs from committed", " ".join(self.verify(manifest)))

    def test_autocrlf_checks_exact_git_blob_and_records_actual_bytes(self):
        self.git("config", "core.autocrlf", "true")
        (self.product / "app.py").write_bytes(b"print('hello')\r\n")
        after = em.capture_product_state(self.product)
        self.assertEqual(after["head_sha"], self.before["head_sha"])
        self.assertNotEqual(after["worktree_sha256"], self.before["worktree_sha256"])

    def test_swapped_execution_revision_policy_image_and_attempt_fail(self):
        manifest = self.build()
        identity = {k: manifest[k] for k in (*em.IDENTITY_FIELDS, "product")}
        for field in (*em.IDENTITY_FIELDS, "product"):
            with self.subTest(field=field):
                bad = {**identity, field: "different"}
                self.assertIn("expected " + field, " ".join(self.verify(manifest, expected=bad)))

    def test_missing_expected_identity_cannot_be_inferred_from_claim(self):
        manifest = self.build()
        self.assertTrue(self.verify(manifest, expected={"run_id": manifest["run_id"]}))

    def test_worker_manifest_replacement_fails_pinned_digest(self):
        manifest = self.build()
        receipt = self.receipt(manifest)
        path = Path(receipt["path"])
        bad = deepcopy(manifest)
        bad["execution_key"] = "worker-invented"
        path.write_text(json.dumps(bad))
        identity = {k: manifest[k] for k in (*em.IDENTITY_FIELDS, "product")}
        errors = em.verify_manifest(path, expected_sha256=receipt["sha256"], expected_identity=identity,
                                    product=self.product, artifact_root=self.artifacts)
        self.assertIn("authoritative digest", " ".join(errors))

    def test_changed_or_missing_artifact_fails(self):
        manifest = self.build()
        (self.artifacts / "test.txt").write_text("test=fail\n")
        self.assertIn("artifact bytes differ", " ".join(self.verify(manifest)))
        (self.artifacts / "test.txt").unlink()
        self.assertTrue(self.verify(manifest))

    def test_artifacts_confined_and_nonempty(self):
        (self.root / "outside.txt").write_text("outside")
        for path in ("../../outside.txt", "/outside.txt", "C:\\outside.txt", "test.txt:stream", ".git/config"):
            with self.subTest(path=path), self.assertRaises((ValueError, PermissionError)):
                self.build(artifacts=[{"path": path}])
        (self.artifacts / "empty.txt").touch()
        with self.assertRaisesRegex(ValueError, "empty"):
            self.build(artifacts=[{"path": "empty.txt"}])

    def test_authority_cannot_be_in_or_contain_worker_roots(self):
        manifest = self.build()
        for authority in (self.artifacts, self.artifacts / "hidden", self.root):
            with self.subTest(authority=authority), self.assertRaisesRegex(ValueError, "separate"):
                em.publish_manifest(authority, manifest, writable_roots=[self.artifacts])

    def test_nonzero_result_is_recorded_but_cannot_support_coverage(self):
        failed = [{"id": "quality:test", "command": "python app.py", "exit_code": 1, "outcome": "fail"}]
        manifest = self.build(tests=failed)
        self.assertEqual(self.verify(manifest, requirements=()), [])
        self.assertIn("failing tests", " ".join(self.verify(manifest)))

    def test_contradictory_or_malformed_process_outcomes_fail(self):
        for change in ({"exit_code": 1}, {"exit_code": False}, {"outcome": "passed"}, {"command": ""}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.build(tests=[{**self.kwargs["tests"][0], **change}])
        with self.assertRaisesRegex(ValueError, "duplicate test id"):
            self.build(tests=self.kwargs["tests"] * 2)
        with self.assertRaisesRegex(ValueError, "observed tests"):
            self.build(tests=[])

    def test_missing_links_do_not_silently_claim_coverage(self):
        manifest = self.build(requirement_tests={})
        self.assertEqual(self.verify(manifest, requirements=()), [])
        self.assertIn("missing requirement-to-test", " ".join(self.verify(manifest)))
        for links in ({"AC-1": []}, {"AC-1": ["fictional"]}, {"AC-1": ["quality:test", "quality:test"]}):
            with self.subTest(links=links), self.assertRaises(ValueError):
                self.build(requirement_tests=links)

    def test_records_are_frozen_against_later_result_mutation(self):
        manifest = self.build()
        self.kwargs["tests"][0]["exit_code"] = 9
        self.assertEqual(self.verify(manifest), [])

    def video_spec(self):
        return {"path": "test.txt", "kind": "video", "capture": {
            "execution_key": "execution-1", "recorder": "host-playwright", "session_id": "capture-1",
            "started_at": "2026-09-10T01:00:00Z", "ended_at": "2026-09-10T01:00:01Z"}}

    def test_video_requires_recorder_identity_and_decoder_evidence(self):
        decoded = {"duration_seconds": 1.0, "streams": [{"codec_type": "video", "codec_name": "vp8",
                                                       "width": 640, "height": 480}], "decoded": True}
        spec = self.video_spec()
        manifest = self.build(artifacts=[spec], video_probe=lambda _: decoded)
        self.assertEqual(self.verify(manifest, video_probe=lambda _: decoded), [])
        self.assertTrue(self.verify(manifest, video_probe=lambda _: {**decoded, "duration_seconds": 2.0}))
        spec["capture"]["execution_key"] = "stale-execution"
        with self.assertRaisesRegex(ValueError, "matching recorder"):
            self.build(artifacts=[spec], video_probe=lambda _: decoded)
        with self.assertRaisesRegex(ValueError, "matching recorder"):
            self.build(artifacts=[{"path": "test.txt", "kind": "video"}])

    def test_probe_rejects_invalid_stream_and_decode_failure(self):
        good = {"format": {"duration": "1.25"}, "streams": [{"codec_type": "video", "codec_name": "vp8", "width": 8, "height": 8}]}
        probe = subprocess.CompletedProcess([], 0, json.dumps(good), "")
        fail = subprocess.CompletedProcess([], 1, b"", b"invalid frame")
        with patch.object(em.subprocess, "run", side_effect=[probe, fail]):
            with self.assertRaisesRegex(ValueError, "decode failed"):
                em.probe_video(self.artifacts / "test.txt")
        for value in ({"format": {"duration": "nan"}, "streams": good["streams"]},
                      {"format": {"duration": "1"}, "streams": []}):
            with patch.object(em.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(value), "")):
                with self.assertRaises(ValueError):
                    em.probe_video(self.artifacts / "test.txt")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "video tools unavailable")
    def test_real_decoder_accepts_synthetic_video_and_rejects_text(self):
        # This is a real decoder control, not a browser recording or live QA claim.
        video = self.artifacts / "synthetic.webm"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=32x32:r=5",
                        "-t", "0.4", "-c:v", "libvpx", str(video)], check=True, capture_output=True,
                       stdin=subprocess.DEVNULL, timeout=30)
        facts = em.probe_video(video)
        self.assertTrue(facts["decoded"])
        self.assertGreater(facts["duration_seconds"], 0)
        with self.assertRaisesRegex(ValueError, "probe failed"):
            em.probe_video(self.artifacts / "test.txt")


if __name__ == "__main__":
    unittest.main()
