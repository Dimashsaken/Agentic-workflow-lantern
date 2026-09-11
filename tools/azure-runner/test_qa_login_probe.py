"""qa_login_probe against two login-form shapes: Tender's (csrf + email) and Mission
Control's (username, no token, 200 on a rejected login). No network beyond localhost.

    .venv/Scripts/python test_qa_login_probe.py
"""

from __future__ import annotations

import http.cookies
import http.server
import secrets
import sys
import threading
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_login_probe as qp  # noqa: E402

ACCOUNT = ("qa@tender.test", "s3cret")


class TenderShaped(http.server.BaseHTTPRequestHandler):
    sessions: dict[str, str] = {}

    def log_message(self, *_):
        pass

    def _session(self):
        c = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        sid = c["sid"].value if "sid" in c else ""
        if sid in self.sessions:
            return sid, self.sessions[sid], False
        sid, tok = secrets.token_hex(6), secrets.token_urlsafe(12)
        self.sessions[sid] = tok
        return sid, tok, True

    def do_GET(self):
        if self.path != "/login":
            self.send_response(404); self.end_headers(); return
        sid, tok, fresh = self._session()
        body = (f'<html><form method="post" action="/login"><input type="hidden" name="csrf_token" value="{tok}">'
                f'<input id="email" name="email" type="email"><input name="password" type="password">'
                f'<button>Log in</button></form></html>').encode()
        self.send_response(200)
        if fresh:
            self.send_header("Set-Cookie", f"sid={sid}; Path=/")
        self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        f = dict(urllib.parse.parse_qsl(self.rfile.read(n).decode()))
        sid, tok, fresh = self._session()
        if fresh or f.get("csrf_token") != tok:
            self.send_response(403); self.end_headers(); return
        if (f.get("email"), f.get("password")) == ACCOUNT:
            self.send_response(303); self.send_header("Location", "/conversations"); self.end_headers()
        else:
            self.send_response(401); self.end_headers()


class MissionControlShaped(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b'<form method="post"><input name="username"><input name="password" type="password"></form>')

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        f = dict(urllib.parse.parse_qsl(self.rfile.read(n).decode()))
        if (f.get("username"), f.get("password")) == ACCOUNT:
            self.send_response(303); self.send_header("Location", "/"); self.end_headers()
        else:
            self.send_response(200); self.end_headers(); self.wfile.write(b"<form>bad login</form>")


def serve(handler):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


class Probe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tender, cls.tender_url = serve(TenderShaped)
        cls.mc, cls.mc_url = serve(MissionControlShaped)

    @classmethod
    def tearDownClass(cls):
        cls.tender.shutdown(); cls.mc.shutdown()

    def test_tender_form_csrf_and_email_field_are_taken_from_the_page(self):
        r = qp.probe(self.tender_url, *ACCOUNT)
        self.assertEqual((r["get"], r["post"], r["user_field"], r["accepted"]), (200, 303, "email", True), r)
        self.assertEqual(r["hidden_fields"], ["csrf_token"])
        r = qp.probe(self.tender_url, ACCOUNT[0], "wrong")
        self.assertEqual((r["post"], r["accepted"]), (401, False), r)

    def test_mission_control_form_still_works_and_a_rerender_is_a_rejection(self):
        r = qp.probe(self.mc_url, *ACCOUNT)
        self.assertEqual((r["post"], r["user_field"], r["accepted"]), (303, "username", True), r)
        r = qp.probe(self.mc_url, ACCOUNT[0], "wrong")
        self.assertEqual((r["post"], r["accepted"]), (200, False), r)

    def test_unreachable_target_is_an_error_not_a_rejection(self):
        r = qp.probe("http://127.0.0.1:9", *ACCOUNT, timeout=3)
        self.assertFalse(r["accepted"])
        self.assertIn("error", r)

    def test_plan_login_defaults_when_the_page_has_no_recognisable_form(self):
        hidden, user_field, pw_field, action = qp.plan_login("<html><p>no form</p></html>")
        self.assertEqual((hidden, user_field, pw_field, action), ({}, "username", "password", None))
        hidden, user_field, pw_field, action = qp.plan_login(
            '<form action="/auth/session"><input type="hidden" name="_t" value="1"><input name="login">'
            '<input type="password" name="pw"></form>')
        self.assertEqual((hidden, user_field, pw_field, action), ({"_t": "1"}, "login", "pw", "/auth/session"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
