"""Proof for Mission Control's QA video links: /media signs, redirects and refuses.

    ..\\azure-runner\\.venv\\Scripts\\python -m unittest test_media_route -v

The artifact bucket blocks all public access, so an `s3://` href does nothing in a
browser. `/media/<artifact id>`, and `/media?uri=<s3 uri>` for a media-manifest.json entry
(which names the object, not its row), finds the object's artifacts row, signs a
15-minute GET with the host's own AWS identity and answers 302. Stdlib only: routes are
called as coroutines against fakes.FakePool (the venv has no httpx), and the
`aws s3 presign` subprocess is replaced by a recorder, so no AWS call is made.

What must hold:

1. **Sign in first.** An anonymous, forged or expired session goes to /login before the
   database or the signer is touched.
2. **Only recorded objects under s3://$LANTERN_ARTIFACT_BUCKET/lantern/ are signed.**
   Another bucket, another prefix, a dot or empty segment, a query, a non-s3 artifact, an
   unset bucket: 403, and nothing is signed. An unknown id, or a URI that no artifacts row
   records (a planted manifest): 404.
3. **The signed URL goes into the Location header and nowhere else**: a 302 marked
   no-store carries it byte for byte. It is never printed, logged or rendered, and it is
   not in the 502 that a failed signing returns.
4. **The signer is `aws s3 presign <uri> --expires-in 900`**, killed on timeout. Anything
   but one https URL on stdout is a failure, and the error never repeats stdout.
5. **Pages link through /media and sign nothing while rendering.** The run page's artifact
   rows link /media/<id>, a review's staging videos link /media?uri=…, and no page carries
   an s3:// href.
"""
import asyncio
import contextlib
import io
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ["LANTERN_WEB_USERS"] = "tester:pw,dimash:pw,justin:pw"   # same set as test_routes_v3

import app as mc  # noqa: E402
import factory  # noqa: E402
from fakes import NOW, FakePool, Req, approval_row, body_of, exec_row, get, run_row, signed  # noqa: E402
from fastapi import HTTPException  # noqa: E402

BUCKET = "lantern-artifacts-test"
RUN = "feat-20260911-tender-onboarding"
VIDEO = f"s3://{BUCKET}/lantern/{RUN}/07-qa-staging/attempt-2/{RUN}--07-qa-staging--session-1.webm"
OTHER = VIDEO.replace("session-1", "session-2")
# The shape an instance role's presign has: percent-escapes a redirect must not re-encode.
SIGNED = (f"https://{BUCKET}.s3.amazonaws.com/lantern/{RUN}/07-qa-staging/attempt-2/"
          f"{RUN}--07-qa-staging--session-1.webm?X-Amz-Algorithm=AWS4-HMAC-SHA256"
          "&X-Amz-Credential=ASIAEXAMPLEEXAMPLE%2F20260916%2Fus-east-1%2Fs3%2Faws4_request"
          "&X-Amz-Date=20260916T120000Z&X-Amz-Expires=900&X-Amz-SignedHeaders=host"
          "&X-Amz-Security-Token=IQoJb3JpZ2luX2VjEXAMPLE%2B%2Fexample%3D%3D"
          "&X-Amz-Signature=" + "5f" * 32)
MANIFEST_HREF = "/media?uri=" + quote(VIDEO, safe="")


def art(id, uri=VIDEO, run_id=RUN, stage="07-qa-staging", kind="qa_video") -> dict:
    return {"id": id, "run_id": run_id, "stage": stage, "kind": kind, "uri": uri}


class Signer:
    """Stands in for app.presign_media: records each call, returns SIGNED or fails."""

    def __init__(self):
        self.calls: list[tuple[str, int]] = []
        self.fail: str | None = None

    async def __call__(self, uri, ttl):
        self.calls.append((uri, ttl))
        if self.fail:
            raise mc.MediaUnavailable(self.fail)
        return SIGNED


class _Records(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(record.getMessage())


@contextlib.contextmanager
def everything_emitted():
    """stdout, stderr and every log record of every logger, collected once the block ends."""
    root, records = logging.getLogger(), _Records()
    level, out, err = root.level, io.StringIO(), io.StringIO()
    seen: list[str] = []
    root.addHandler(records)
    root.setLevel(logging.DEBUG)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            yield seen
    finally:
        root.removeHandler(records)
        root.setLevel(level)
        seen.extend([out.getvalue(), err.getvalue(), *records.lines])


class Media(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"LANTERN_ARTIFACT_BUCKET": BUCKET})
        env.start()
        self.addCleanup(env.stop)
        self.signer = Signer()
        signer = patch.object(mc, "presign_media", self.signer)
        signer.start()
        self.addCleanup(signer.stop)

    def refused(self, status, route, *args, pool, **kw) -> str:
        with self.assertRaises(HTTPException) as cm:
            get(route, *args, pool=pool, **kw)
        self.assertEqual(cm.exception.status_code, status, (args, kw))
        return cm.exception.detail


class SignedRedirect(Media):
    def test_a_recorded_video_redirects_to_its_signed_url(self):
        with everything_emitted() as seen:
            resp = get(mc.media_by_id, 17, signed(), pool=FakePool(arts=[art(17)]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers["location"], SIGNED)             # byte for byte
        self.assertEqual(resp.headers["cache-control"], "no-store")
        self.assertEqual(resp.body, b"")
        self.assertEqual(self.signer.calls, [(VIDEO, 900)])            # 15 minutes
        self.assertNotIn("X-Amz", "".join(seen))                       # never printed or logged

    def test_a_manifest_uri_signs_the_object_its_row_records(self):
        pool = FakePool(arts=[art(17), art(18, OTHER)])
        resp = get(mc.media_by_uri, signed(), pool=pool, uri=OTHER)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers["location"], SIGNED)
        self.assertEqual(self.signer.calls, [(OTHER, 900)])


class Refusals(Media):
    def test_anonymous_callers_go_to_login_before_anything_is_read(self):
        pool = FakePool(arts=[art(17)])
        payload = f"tester|{int(time.time()) - 60}"
        expired = Req({mc.SESSION_COOKIE: f"{payload}|{mc._sign(payload)}"})
        forged = Req({mc.SESSION_COOKIE: f"tester|{int(time.time()) + 3600}|{'0' * 64}"})
        for req in (Req(), expired, forged):
            for resp in (get(mc.media_by_id, 17, req, pool=pool),
                         get(mc.media_by_uri, req, pool=pool, uri=VIDEO)):
                self.assertEqual(resp.status_code, 303)
                self.assertEqual(resp.headers["location"], "/login")
        self.assertEqual(pool.queries, [])
        self.assertEqual(self.signer.calls, [])

    def test_objects_outside_the_bucket_prefix_are_refused(self):
        outside = (
            f"s3://other-bucket/lantern/{RUN}/07-qa-staging/attempt-1/x.webm",   # another bucket
            f"s3://{BUCKET}-copy/lantern/{RUN}/x.webm",                          # a name that shares the prefix
            f"s3://{BUCKET}/backups/lantern.sql.gz",                             # another prefix
            f"s3://{BUCKET}/lantern", f"s3://{BUCKET}/lantern/", f"s3://{BUCKET}/",
            f"s3://{BUCKET}/lantern/../backups/lantern.sql.gz",
            f"s3://{BUCKET}/lantern/./x.webm", f"s3://{BUCKET}/lantern//x.webm",
            f"s3://{BUCKET}/lantern/x.webm?versionId=1", f"s3://{BUCKET}/lantern/x.webm#t=5",
            f"s3://{BUCKET}/lantern/x.webm\n", f"s3://{BUCKET}/lantern/x%2F..%2Fy.webm",
            f"s3://{BUCKET}/lantern/x y.webm", f"S3://{BUCKET}/lantern/x.webm",
            f"s3:/{BUCKET}/lantern/x.webm",
            f"https://{BUCKET}.s3.amazonaws.com/lantern/x.webm",                 # not an s3:// URI
            f"workflow/runs/{RUN}/07-qa-staging/report.md", "",
        )
        for n, uri in enumerate(outside, start=100):
            self.refused(403, mc.media_by_id, n, signed(), pool=FakePool(arts=[art(n, uri)]))
            pool = FakePool(arts=[art(n, uri)])
            self.refused(403, mc.media_by_uri, signed(), pool=pool, uri=uri)
            self.assertEqual(pool.queries, [], uri)                          # refused before the lookup
        self.assertEqual(self.signer.calls, [])

    def test_no_bucket_on_this_host_signs_nothing(self):
        with patch.dict(os.environ):
            os.environ.pop("LANTERN_ARTIFACT_BUCKET")
            detail = self.refused(403, mc.media_by_id, 17, signed(), pool=FakePool(arts=[art(17)]))
            self.assertIn("LANTERN_ARTIFACT_BUCKET is not set", detail)
            os.environ["LANTERN_ARTIFACT_BUCKET"] = " "
            self.refused(403, mc.media_by_uri, signed(), pool=FakePool(arts=[art(17)]), uri=VIDEO)
            # the host's bucket decides, not the one a row names
            os.environ["LANTERN_ARTIFACT_BUCKET"] = "other-bucket"
            self.refused(403, mc.media_by_id, 17, signed(), pool=FakePool(arts=[art(17)]))
        self.assertEqual(self.signer.calls, [])

    def test_a_missing_artifact_is_404(self):
        pool = FakePool(arts=[art(17)])
        self.refused(404, mc.media_by_id, 18, signed(), pool=pool)
        # the right place in the bucket, but no artifacts row records it (a planted manifest)
        self.refused(404, mc.media_by_uri, signed(), pool=pool, uri=VIDEO.replace("session-1", "session-9"))
        # ids no bigserial column holds are 404 without a query (asyncpg would raise)
        edge = FakePool(arts=[art(17)])
        for artifact_id in (0, -1, 2 ** 63):
            self.refused(404, mc.media_by_id, artifact_id, signed(), pool=edge)
        self.assertEqual(edge.queries, [])
        self.assertEqual(self.signer.calls, [])

    def test_a_failed_signing_is_a_502_that_points_at_the_log(self):
        self.signer.fail = "aws s3 presign exited 255: Unable to locate credentials"
        with everything_emitted() as seen:
            detail = self.refused(502, mc.media_by_id, 17, signed(), pool=FakePool(arts=[art(17)]))
        log = "".join(seen)
        self.assertIn("artifact 17", log)
        self.assertIn("Unable to locate credentials", log)       # the reason goes to the journal
        self.assertNotIn("credentials", detail)                  # the response names where to look
        self.assertIn("journalctl -u lantern-mission-control", detail)


class FakeProc:
    def __init__(self, stdout=b"", stderr=b"", returncode=0, hang=False):
        self.stdout, self.stderr, self.exit, self.hang = stdout, stderr, returncode, hang
        self.returncode = None
        self.killed = False

    async def communicate(self):
        if self.hang:
            await asyncio.sleep(3600)
        self.returncode = self.exit
        return self.stdout, self.stderr

    def kill(self):
        self.killed, self.returncode = True, -9

    async def wait(self):
        return self.returncode


class PresignCommand(unittest.TestCase):
    """The real signer, with only the subprocess replaced."""

    def presign(self, proc=None, error=None):
        self.calls = []

        async def fake_exec(*argv, **kw):
            self.calls.append((argv, kw))
            if error:
                raise error
            return proc

        with patch.object(mc.asyncio, "create_subprocess_exec", fake_exec):
            return asyncio.run(mc.presign_media(VIDEO, 900))

    def test_it_runs_aws_s3_presign_with_the_expiry(self):
        with everything_emitted() as seen:
            url = self.presign(FakeProc(stdout=SIGNED.encode() + b"\n", stderr=b"a CLI warning\n"))
        self.assertEqual(url, SIGNED)
        (argv, kw), = self.calls
        self.assertEqual(argv, ("aws", "s3", "presign", VIDEO, "--expires-in", "900"))
        self.assertEqual((kw["stdout"], kw["stderr"]), (asyncio.subprocess.PIPE, asyncio.subprocess.PIPE))
        emitted = "".join(seen)
        self.assertNotIn("X-Amz", emitted)
        self.assertNotIn("a CLI warning", emitted)                  # stderr is read only on failure

    def test_a_cli_error_is_reported_from_stderr_only(self):
        proc = FakeProc(stdout=b"https://half-a-url?X-Amz-Signature=abc",
                        stderr=b"\naws: [ERROR]: Unable to locate credentials\n", returncode=255)
        with self.assertRaises(mc.MediaUnavailable) as cm:
            self.presign(proc)
        self.assertIn("exited 255: aws: [ERROR]: Unable to locate credentials", str(cm.exception))
        self.assertNotIn("X-Amz", str(cm.exception))

    def test_anything_but_one_https_url_is_a_failure(self):
        for out in (b"", b"\n", b"presigned\n", SIGNED.replace("https://", "http://").encode(),
                    f"{SIGNED}\n{SIGNED}\n".encode(), f"{SIGNED} extra".encode()):
            with self.assertRaises(mc.MediaUnavailable, msg=out) as cm:
                self.presign(FakeProc(stdout=out))
            self.assertIn("no https URL on stdout", str(cm.exception))
            self.assertNotIn("X-Amz", str(cm.exception))

    def test_a_missing_cli_is_unavailable_not_a_crash(self):
        with self.assertRaises(mc.MediaUnavailable) as cm:
            self.presign(error=FileNotFoundError(2, "No such file or directory", "aws"))
        self.assertIn("cannot run the aws CLI", str(cm.exception))

    def test_a_hung_cli_is_killed(self):
        proc = FakeProc(hang=True)
        with patch.object(mc, "PRESIGN_TIMEOUT_S", 0.05), self.assertRaises(mc.MediaUnavailable) as cm:
            self.presign(proc)
        self.assertTrue(proc.killed)
        self.assertIn("did not answer", str(cm.exception))


class PagesLinkThroughMedia(Media):
    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="mc-media-"))
        repo, frepo = mc.REPO, factory.REPO
        mc.REPO = factory.REPO = self.tmp

        def restore():
            mc.REPO, factory.REPO = repo, frepo
            shutil.rmtree(self.tmp, ignore_errors=True)

        self.addCleanup(restore)
        stage = self.tmp / "workflow" / "runs" / RUN / "07-qa-staging"
        stage.mkdir(parents=True)
        (stage / "media-manifest.json").write_text(json.dumps({"uploaded": [
            {"uri": VIDEO, "session": 1, "attempt": 2, "at": "2026-09-12T10:00:00+00:00"}]}),
            encoding="utf-8")
        (stage / "report.md").write_text("# Staging QA\n\n- **Status:** PASS\n", encoding="utf-8")
        self.approval = approval_row(id=12, run_id=RUN, gate="prod_signoff",
                                     payload=json.dumps({"stage": "07-qa-staging"}))

    def test_art_href_sends_bucket_objects_through_media(self):
        self.assertEqual(mc.art_href(VIDEO, 17), "/media/17")
        self.assertEqual(mc.art_href(VIDEO), MANIFEST_HREF)
        self.assertEqual(mc.art_href("https://example.com/v.webm", 3), "https://example.com/v.webm")
        self.assertEqual(mc.art_href(f"workflow/runs/{RUN}/x.png"), f"/file/workflow/runs/{RUN}/x.png")

    def test_the_prod_signoff_review_links_its_staging_videos_through_media(self):
        run = run_row(id=RUN, status="waiting_gate", current_stage="07-qa-staging")
        html = mc.gate_card(self.approval, run, NOW)
        self.assertIn(f"<a href='{MANIFEST_HREF}' target='_blank'>🎬 session 1 · attempt 2</a>", html)
        self.assertNotIn("href='s3:", html)

    def test_the_run_page_links_every_video_through_media_and_signs_nothing(self):
        pool = FakePool(runs=[run_row(id=RUN, status="waiting_gate", current_stage="07-qa-staging")],
                        execs=[exec_row(1, RUN, "07-qa-staging")], approvals=[self.approval],
                        arts=[art(17)])
        html = body_of(get(mc.run_page, RUN, signed(), pool=pool))
        self.assertIn("<a href='/media/17' target='_blank'>🎬 qa_video</a>", html)     # the artifacts row
        self.assertEqual(html.count(f"<a href='{MANIFEST_HREF}' target='_blank'>"), 2)  # review + stage folder
        self.assertNotIn("href='s3:", html)
        self.assertEqual(self.signer.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
