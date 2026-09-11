"""tender-qa-account.py against a stub of Tender's auth forms (no network, no product).

    python infra/ec2/test_tender_qa_account.py
"""

from __future__ import annotations

import http.cookies
import http.server
import importlib.util
import secrets
import sys
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("tender_qa_account", HERE / "tender-qa-account.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


class StubTender(http.server.BaseHTTPRequestHandler):
    """GET /signup|/login render a csrf hidden input and set a session cookie; POST checks
    the token against that cookie, keeps accounts in memory, answers like Tender does."""

    accounts: dict[str, str] = {}
    sessions: dict[str, str] = {}      # sid -> csrf token

    def log_message(self, *_):        # quiet
        pass

    def _session(self) -> tuple[str, str, bool]:
        c = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        sid = c["sid"].value if "sid" in c else ""
        if sid in self.sessions:
            return sid, self.sessions[sid], False
        sid, token = secrets.token_hex(8), secrets.token_urlsafe(16)
        self.sessions[sid] = token
        return sid, token, True

    def do_GET(self):
        if self.path not in ("/signup", "/login", "/healthz"):
            self.send_response(404); self.end_headers(); return
        sid, token, fresh = self._session()
        body = f'<form method="post"><input type="hidden" name="csrf_token" value="{token}">' \
               f'<input name="email"><input name="password"></form>'.encode()
        self.send_response(200)
        if fresh:
            self.send_header("Set-Cookie", f"sid={sid}; Path=/")
        self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        fields = dict(urllib.parse.parse_qsl(self.rfile.read(length).decode()))
        sid, token, fresh = self._session()
        if fresh or fields.get("csrf_token") != token:
            self.send_response(403); self.end_headers(); self.wfile.write(b"expired"); return
        email, password = fields.get("email", ""), fields.get("password", "")
        if self.path == "/signup":
            if email in self.accounts:
                self.send_response(422); self.end_headers()
                self.wfile.write(b"<p>That email is already registered.</p>"); return
            self.accounts[email] = password
            self.send_response(303); self.send_header("Location", "/setup"); self.end_headers(); return
        if self.path == "/login":
            if self.accounts.get(email) == password:
                self.send_response(303); self.send_header("Location", "/conversations"); self.end_headers()
            else:
                self.send_response(401); self.end_headers(); self.wfile.write(b"incorrect")
            return
        self.send_response(404); self.end_headers()


class QaAccount(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), StubTender)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        StubTender.accounts.clear()
        StubTender.sessions.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.env = Path(self.tmp.name) / ".env"
        self.env.write_text("OTHER=1\nLANTERN_QA_DEV_USER=qa@tender.test\nLANTERN_QA_DEV_PASS=s3cret-pass\n",
                            encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_run_creates_then_second_run_finds_it(self):
        self.assertEqual(qa.main(["--base-url", self.base, "--env-file", str(self.env)]), 0)
        self.assertEqual(StubTender.accounts, {"qa@tender.test": "s3cret-pass"})
        self.assertEqual(qa.main(["--base-url", self.base, "--env-file", str(self.env)]), 0)
        self.assertEqual(len(StubTender.accounts), 1)

    def test_existing_account_with_another_password_is_not_ready(self):
        StubTender.accounts["qa@tender.test"] = "something-else"
        self.assertEqual(qa.main(["--base-url", self.base, "--env-file", str(self.env)]), 2)

    def test_missing_login_or_unreachable_app_is_not_ready(self):
        self.env.write_text("LANTERN_QA_DEV_USER=qa@tender.test\n", encoding="utf-8")
        self.assertEqual(qa.main(["--base-url", self.base, "--env-file", str(self.env)]), 1)
        self.env.write_text("LANTERN_QA_DEV_USER=u@x\nLANTERN_QA_DEV_PASS=p\n", encoding="utf-8")
        self.assertEqual(qa.main(["--base-url", "http://127.0.0.1:9", "--env-file", str(self.env)]), 1)

    def test_csrf_rejection_is_reported_not_swallowed(self):
        self.assertEqual(qa.hidden_inputs('<input type="hidden" name="csrf_token" value="abc">'
                                          '<input name="email">'), {"csrf_token": "abc"})
        # A token that did not come from the form (no session cookie round-trip) is a 403 on
        # the server; the script must surface that instead of claiming the account exists.
        with mock.patch.object(qa.Client, "csrf_for", return_value="wrong"):
            with self.assertRaises(qa.QaAccountError):
                qa.ensure_account(self.base, "a@b", "p")
        self.assertNotIn("a@b", StubTender.accounts)


if __name__ == "__main__":
    unittest.main(verbosity=2)
