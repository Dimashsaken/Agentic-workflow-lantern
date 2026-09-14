#!/usr/bin/env python3
"""Seed the QA login on a running Tender instance, or prove it already works.

    python3 infra/ec2/tender-qa-account.py --base-url http://127.0.0.1:8000 \
        --env-file tools/azure-runner/.env --prefix LANTERN_QA_DEV

The qa-dev agent is told to type the provisioned credentials exactly and never to
invent any (orchestrator.qa_target_note), so the account must exist on the served
build before stage 4 starts. Tender's sign-up is a server-rendered form: GET /signup
sets a signed session cookie carrying a CSRF token, POST /signup with that token, the
email and the password answers 303 → /setup; a duplicate email answers 422. This
script does exactly that with the standard library, then proves the login works on a
fresh cookie jar. It never prints the password. Exit 0 = the QA agent can log in.

Found 2026-09-11 preparing stage 4 of the first Tender run (feat-20260911-tender-onboarding).
"""

from __future__ import annotations

import argparse
import http.cookiejar
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


class QaAccountError(Exception):
    pass


def read_login(env_file: Path, prefix: str) -> tuple[str, str]:
    """`<prefix>_USER` / `<prefix>_PASS` from a dotenv-style file (last definition wins)."""
    user = password = ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key.strip() == prefix + "_USER":
            user = value.strip()
        elif key.strip() == prefix + "_PASS":
            password = value.strip()
    if not user or not password:
        raise QaAccountError(f"{prefix}_USER / {prefix}_PASS are not both set in {env_file} "
                             "— run `pipeline.py qa-target` first")
    return user, password


class _HiddenInputs(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "input":
            return
        a = dict(attrs)
        if a.get("type") == "hidden" and a.get("name"):
            self.values[a["name"]] = a.get("value") or ""


def hidden_inputs(html: str) -> dict[str, str]:
    p = _HiddenInputs()
    p.feed(html)
    return p.values


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib hook
        return None  # surface 3xx as HTTPError so the caller reads Location itself


class Client:
    """One cookie jar = one browser session."""

    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar), _NoRedirect())

    def request(self, method: str, path: str, fields: dict[str, str] | None = None
                ) -> tuple[int, str, str]:
        data = urllib.parse.urlencode(fields).encode() if fields is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                return r.status, r.read().decode("utf-8", "replace"), r.headers.get("Location", "")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), e.headers.get("Location", "")

    def csrf_for(self, path: str) -> str:
        status, body, _ = self.request("GET", path)
        if status != 200:
            raise QaAccountError(f"GET {path} answered HTTP {status} — is the app up at {self.base}?")
        token = hidden_inputs(body).get("csrf_token")
        if not token:
            raise QaAccountError(f"GET {path} rendered no csrf_token hidden input — the form changed")
        return token


def login_works(base_url: str, user: str, password: str) -> bool:
    """A fresh session can log in: 303 to an authenticated page, never 401."""
    c = Client(base_url)
    token = c.csrf_for("/login")
    status, _, location = c.request("POST", "/login",
                                    {"csrf_token": token, "email": user, "password": password})
    if status in (302, 303) and location:
        return True
    if status == 401:
        return False
    raise QaAccountError(f"POST /login answered HTTP {status} (expected 303 or 401)")


def ensure_account(base_url: str, user: str, password: str) -> str:
    """Create the account, or accept that it exists. Returns 'created' | 'exists'."""
    c = Client(base_url)
    token = c.csrf_for("/signup")
    status, body, location = c.request("POST", "/signup",
                                       {"csrf_token": token, "email": user, "password": password})
    if status in (302, 303) and location:
        return "created"
    if status == 422 and "already" in body.lower():
        return "exists"
    if status == 403:
        raise QaAccountError("POST /signup rejected the CSRF token — the session cookie did not "
                             "round-trip (is the app behind a proxy that drops Set-Cookie?)")
    raise QaAccountError(f"POST /signup answered HTTP {status}: {body[:300]!r}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--prefix", default="LANTERN_QA_DEV", help="LANTERN_QA_DEV | LANTERN_QA_STAGING")
    a = ap.parse_args(argv)
    try:
        user, password = read_login(Path(a.env_file), a.prefix)
        outcome = ensure_account(a.base_url, user, password)
        if not login_works(a.base_url, user, password):
            print(f"NOT READY: `{user}` exists on {a.base_url} but the password in {a.env_file} "
                  f"({a.prefix}_PASS) does not open it. Tender has no password reset (a v0.1 "
                  "non-goal): reset the fixture instead — stop the unit, delete its tender.db, "
                  "start it, and run this again.", file=sys.stderr)
            return 2
    except (QaAccountError, OSError, urllib.error.URLError) as e:
        print(f"NOT READY: {e}", file=sys.stderr)
        return 1
    print(f"READY: QA account `{user}` {outcome} on {a.base_url}; login verified on a fresh session.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
