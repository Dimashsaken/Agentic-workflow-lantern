"""Can the provisioned QA login actually get in? Asked the way a browser would.

    QA_BASE_URL=http://host:8000 QA_USER=... QA_PASS=... python qa_login_probe.py

`pipeline.py qa-preflight` runs this INSIDE a sandbox container (the repo is mounted
read-only, as it is for every stage), because reachability is not readiness: the first
daemon-driven stage 4 (2026-09-07) reached the login page and still could not get in.
Until 2026-09-11 the probe posted `username`/`password` blind, which only fits Mission
Control's form; Tender's login carries a CSRF token in a signed session cookie and
names its field `email`, so a working login was reported as REJECTED.

The probe GETs the login page on a fresh cookie jar, keeps every hidden input, picks the
credential fields from the form itself (an `email`-typed input, else a name such as
`username`/`email`/`login`; the `password`-typed input), POSTs, and treats a redirect as
accepted — a re-rendered page (200) or 401/403 is a rejection. Standard library only.
Prints one JSON line; exit 0 accepted, 1 rejected, 2 unreachable or unparseable.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

USER_FIELD_NAMES = ("username", "email", "user", "login", "user_email", "login_email")


class _Inputs(HTMLParser):
    """Inputs of the FIRST form that has a password field (the login form)."""

    def __init__(self) -> None:
        super().__init__()
        self._depth = 0
        self._current: list[dict[str, str]] = []
        self.login_form: list[dict[str, str]] | None = None
        self.action: str | None = None
        self._current_action: str | None = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "form":
            self._depth += 1
            self._current, self._current_action = [], a.get("action")
        elif tag == "input" and self._depth:
            self._current.append(a)

    def handle_endtag(self, tag):
        if tag == "form" and self._depth:
            self._depth -= 1
            if self.login_form is None and any(i.get("type") == "password" for i in self._current):
                self.login_form, self.action = self._current, self._current_action
            self._current = []


def plan_login(html: str) -> tuple[dict[str, str], str, str, str | None]:
    """(hidden fields to carry, user field name, password field name, form action)."""
    p = _Inputs()
    p.feed(html)
    inputs = p.login_form or []
    hidden = {i["name"]: i.get("value", "") for i in inputs if i.get("type") == "hidden" and i.get("name")}
    user_field = next((i["name"] for i in inputs if i.get("type") == "email" and i.get("name")), "")
    if not user_field:
        user_field = next((i["name"] for i in inputs
                           if i.get("name", "").lower() in USER_FIELD_NAMES), "username")
    pw_field = next((i["name"] for i in inputs if i.get("type") == "password" and i.get("name")), "password")
    return hidden, user_field, pw_field, p.action


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe(base_url: str, user: str, password: str, timeout: float = 30.0) -> dict:
    base = base_url.rstrip("/")
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), _NoRedirect())

    def call(method: str, url: str, fields: dict[str, str] | None = None) -> tuple[int, str, str]:
        data = urllib.parse.urlencode(fields).encode() if fields is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with opener.open(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace"), r.headers.get("Location", "")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), e.headers.get("Location", "")

    result: dict = {"base": base, "get": None, "post": None, "user_field": None, "accepted": False}
    try:
        status, body, _ = call("GET", base + "/login")
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        result["error"] = f"GET /login failed: {e}"
        return result
    result["get"] = status
    if status != 200:
        result["error"] = f"GET /login answered HTTP {status}"
        return result
    hidden, user_field, pw_field, action = plan_login(body)
    result["user_field"] = user_field
    result["hidden_fields"] = sorted(hidden)
    fields = dict(hidden)
    fields[user_field] = user
    fields[pw_field] = password
    target = urllib.parse.urljoin(base + "/login", action or "/login")
    try:
        status, _, location = call("POST", target, fields)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        result["error"] = f"POST {target} failed: {e}"
        return result
    result["post"] = status
    result["accepted"] = 300 <= status < 400 and bool(location)
    return result


def main() -> int:
    base, user, pw = (os.environ.get(k, "") for k in ("QA_BASE_URL", "QA_USER", "QA_PASS"))
    if not (base and user and pw):
        print(json.dumps({"error": "QA_BASE_URL, QA_USER and QA_PASS must all be set", "accepted": False}))
        return 2
    r = probe(base, user, pw)
    print(json.dumps(r))
    if r.get("accepted"):
        return 0
    return 2 if r.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
