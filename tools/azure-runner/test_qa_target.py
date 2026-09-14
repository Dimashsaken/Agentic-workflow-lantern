"""`pipeline.py qa-target` — pointing a QA stage at a running app without leaking a value.

    .venv/Scripts/python test_qa_target.py      (no database, no Azure)

Found 2026-09-12 preparing stage 4 of the first Tender run: the box's `.env` still held
the dogfood-era Mission Control login (`LANTERN_QA_DEV_USER=qa-dev`), and the playbook's
`serve` step only appended names that were missing — so QA would have been pointed at
Tender with a user that cannot exist there. `.env` beats SSM for these names
(`load_ssm_qa_env` fills only unset ones), so what this command writes IS the target.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline as p  # noqa: E402

DOGFOOD = """# box env
AZURE_OPENAI_ENDPOINT=https://x.openai.azure.com
LANTERN_QA_DEV_BASE_URL=http://172.17.0.1:8080
LANTERN_QA_DEV_USER=qa-dev
LANTERN_QA_DEV_PASS=old-mission-control-pass
LANTERN_QA_STAGING_BASE_URL=http://172.17.0.1:8081
LANTERN_PUBLIC_URL=http://44.222.199.220:8080
"""


def values(path: Path) -> dict[str, str]:
    out = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if "=" in ln and not ln.startswith("#"):
            k, v = ln.split("=", 1)
            out[k] = v
    return out


class QaTarget(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = Path(self.tmp.name) / ".env"
        self.env.write_text(DOGFOOD, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_user_replaces_url_and_login_and_regenerates_the_password(self):
        r = p.set_qa_target(self.env, "qa-dev", "http://172.17.0.1:8000", user="qa@tender.test")
        v = values(self.env)
        self.assertEqual(v["LANTERN_QA_DEV_BASE_URL"], "http://172.17.0.1:8000")
        self.assertEqual(v["LANTERN_QA_DEV_USER"], "qa@tender.test")
        self.assertNotEqual(v["LANTERN_QA_DEV_PASS"], "old-mission-control-pass")
        self.assertGreaterEqual(len(v["LANTERN_QA_DEV_PASS"]), 12)
        self.assertTrue(r["password_changed"])
        self.assertFalse(r["created"])
        # Everything else is untouched, in place, in order.
        lines = self.env.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "# box env")
        self.assertEqual(lines[1], "AZURE_OPENAI_ENDPOINT=https://x.openai.azure.com")
        self.assertEqual(lines[2].split("=")[0], "LANTERN_QA_DEV_BASE_URL")
        self.assertEqual(lines[-1], "LANTERN_PUBLIC_URL=http://44.222.199.220:8080")
        self.assertEqual(v["LANTERN_QA_STAGING_BASE_URL"], "http://172.17.0.1:8081")

    def test_same_user_again_keeps_the_password(self):
        p.set_qa_target(self.env, "qa-dev", "http://172.17.0.1:8000", user="qa@tender.test")
        first = values(self.env)["LANTERN_QA_DEV_PASS"]
        r = p.set_qa_target(self.env, "qa-dev", "http://172.17.0.1:8000", user="qa@tender.test")
        self.assertEqual(values(self.env)["LANTERN_QA_DEV_PASS"], first)
        self.assertFalse(r["password_changed"])
        # No user given: the existing login and password stay, only the URL moves.
        r = p.set_qa_target(self.env, "qa-dev", "http://172.17.0.1:8010")
        v = values(self.env)
        self.assertEqual((v["LANTERN_QA_DEV_BASE_URL"], v["LANTERN_QA_DEV_USER"], v["LANTERN_QA_DEV_PASS"]),
                         ("http://172.17.0.1:8010", "qa@tender.test", first))
        self.assertFalse(r["password_changed"])

    def test_rotate_and_explicit_password(self):
        p.set_qa_target(self.env, "qa-dev", "http://172.17.0.1:8000", user="qa@tender.test")
        first = values(self.env)["LANTERN_QA_DEV_PASS"]
        r = p.set_qa_target(self.env, "qa-dev", "http://172.17.0.1:8000", rotate=True)
        self.assertTrue(r["password_changed"])
        self.assertNotEqual(values(self.env)["LANTERN_QA_DEV_PASS"], first)
        r = p.set_qa_target(self.env, "qa-dev", "http://172.17.0.1:8000", password="given-one")
        self.assertEqual(values(self.env)["LANTERN_QA_DEV_PASS"], "given-one")
        self.assertTrue(r["password_changed"])

    def test_staging_target_and_missing_names_are_added(self):
        r = p.set_qa_target(self.env, "qa-staging", "http://172.17.0.1:8001", user="qa@tender.test")
        v = values(self.env)
        self.assertEqual(v["LANTERN_QA_STAGING_BASE_URL"], "http://172.17.0.1:8001")
        self.assertEqual(v["LANTERN_QA_STAGING_USER"], "qa@tender.test")
        self.assertTrue(v["LANTERN_QA_STAGING_PASS"])
        self.assertTrue(r["password_changed"])          # there was no password before
        self.assertEqual(v["LANTERN_QA_DEV_USER"], "qa-dev")   # the other target is not touched

    def test_missing_file_is_created_and_duplicates_collapse(self):
        fresh = Path(self.tmp.name) / "sub" / ".env"
        r = p.set_qa_target(fresh, "qa-dev", "http://h:1", user="u@x")
        self.assertTrue(r["created"])
        self.assertEqual(sorted(values(fresh)), ["LANTERN_QA_DEV_BASE_URL", "LANTERN_QA_DEV_PASS", "LANTERN_QA_DEV_USER"])
        if os.name != "nt":
            self.assertEqual(fresh.stat().st_mode & 0o777, 0o600)
        self.env.write_text(DOGFOOD + "LANTERN_QA_DEV_USER=later-duplicate\n", encoding="utf-8")
        p.set_qa_target(self.env, "qa-dev", "http://172.17.0.1:8000", user="qa@tender.test")
        text = self.env.read_text(encoding="utf-8")
        self.assertEqual(text.count("LANTERN_QA_DEV_USER="), 1)
        self.assertNotIn("later-duplicate", text)

    def test_bad_role_and_bad_url_are_refused_before_writing(self):
        before = self.env.read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            p.set_qa_target(self.env, "qa-prod", "http://h:1")
        with self.assertRaises(ValueError):
            p.set_qa_target(self.env, "qa-dev", "172.17.0.1:8000")
        self.assertEqual(self.env.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
