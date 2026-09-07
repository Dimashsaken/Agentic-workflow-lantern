"""Proof that the codebase-connection write route is fail-closed and confined (D15).

    ..\\..\\tools\\azure-runner\\.venv\\Scripts\\python -m unittest test_repo_routes -v

`POST /run/{id}/repo` is only the second write route Mission Control has ever had (the
first is the gate decision), and it is the more dangerous one: it decides which
directory on this host becomes a run's product tree. The route is called directly here
rather than over HTTP because the venv has no httpx, so no TestClient — the same
approach test_status_json.py takes with pipeline.connect.

Four properties:
1. **Auth is checked FIRST.** An unauthenticated caller gets 401 whatever the payload
   says — never a 400 that reveals whether the path exists.
2. **Only workspace.contains() admits a path.** A real git repo outside the roots is
   still refused, and the refusal names the boundary rather than 404-ing silently.
3. **A finished run is not retargetable**, and neither is a run past coding — every
   report already written names paths in the old tree.
4. **A save writes all three columns and leaves an audit event**, with the actor and
   the channel the gate route uses.
"""

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

os.environ.setdefault("LANTERN_DATABASE_URL",
                      "postgresql+asyncpg://lantern:none@localhost:5432/lantern")

import app as mc  # noqa: E402
import workspace  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class StubRequest:
    """Enough of a Request for current_user(); the real one only reads cookies."""

    def __init__(self, cookies=None):
        self.cookies = cookies or {}


class FakeConn:
    def __init__(self, run_row):
        self.run_row = run_row
        self.executed = []          # (sql, args)

    async def fetchrow(self, sql, *a):
        return self.run_row

    async def fetchval(self, sql, *a):
        return 1

    async def execute(self, sql, *a):
        self.executed.append((" ".join(sql.split()), a))
        return "UPDATE 1"

    # `async with pool.acquire() as conn`
    def acquire(self):
        conn = self

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False
        return _Ctx()


def make_git_repo(path: Path) -> Path:
    """A real git repo — verify_product_target runs actual git against it."""
    import subprocess
    path.mkdir(parents=True, exist_ok=True)

    def g(*args):
        subprocess.run(["git", *args], cwd=path, capture_output=True, check=True)
    g("init", "-q", "-b", "main")
    g("config", "user.name", "t")
    g("config", "user.email", "t@example.invalid")
    (path / "README.md").write_text("# x\n", encoding="utf-8")
    g("add", "-A")
    g("commit", "-q", "-m", "init")
    return path


class RepoRouteTest(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("LANTERN_WORKSPACE_ROOTS",)}
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name).resolve()
        self.root = self.tmp / "roots"
        self.repo = make_git_repo(self.root / "product")
        self.outside = make_git_repo(self.tmp / "elsewhere" / "private")
        os.environ["LANTERN_WORKSPACE_ROOTS"] = str(self.root)
        workspace._cache.clear()

        self.run_row = {"id": "feat-20260907-x", "status": "running",
                        "current_stage": "02-pre-coding", "product_repo": None,
                        "product_branch": None, "product_working_branch": None}
        self.conn = FakeConn(self.run_row)

        self._real_pool, self._real_user, self._real_log = (
            mc.get_pool, mc.current_user, mc.log_event)
        self.events = []

        async def fake_pool():
            return self.conn

        async def fake_log(conn, run_id, actor, typ, data):
            self.events.append((run_id, actor, typ, data))

        mc.get_pool = fake_pool
        mc.log_event = fake_log
        mc.current_user = lambda req: getattr(req, "_user", None)

    def tearDown(self):
        mc.get_pool, mc.current_user, mc.log_event = (
            self._real_pool, self._real_user, self._real_log)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._td.cleanup()
        workspace._cache.clear()

    def post(self, user="dimash", **kw):
        req = StubRequest()
        req._user = user
        params = {"action": "save", "local_path": "", "remote_url": "",
                  "base_branch": "main", "working_branch": ""}
        params.update(kw)
        return run(mc.set_repo("feat-20260907-x", req, **params))

    # 1. auth
    def test_unauthenticated_post_is_401_before_anything_else(self):
        with self.assertRaises(HTTPException) as e:
            self.post(user=None, local_path=str(self.repo))
        self.assertEqual(e.exception.status_code, 401)

    def test_unauthenticated_post_with_a_bad_path_is_still_401_not_400(self):
        with self.assertRaises(HTTPException) as e:
            self.post(user=None, local_path=str(self.outside))
        self.assertEqual(e.exception.status_code, 401,
                         "auth must be decided before the path is even looked at")

    # 2. confinement
    def test_path_outside_the_roots_is_400_naming_the_boundary(self):
        with self.assertRaises(HTTPException) as e:
            self.post(local_path=str(self.outside))
        self.assertEqual(e.exception.status_code, 400)
        self.assertIn("LANTERN_WORKSPACE_ROOTS", e.exception.detail)

    def test_a_non_repo_inside_a_root_is_refused(self):
        plain = self.root / "just-a-folder"
        plain.mkdir()
        with self.assertRaises(HTTPException) as e:
            self.post(local_path=str(plain))
        self.assertEqual(e.exception.status_code, 400)

    def test_both_local_and_remote_is_refused(self):
        with self.assertRaises(HTTPException) as e:
            self.post(local_path=str(self.repo), remote_url="https://github.com/o/r")
        self.assertEqual(e.exception.status_code, 400)

    def test_neither_is_refused(self):
        with self.assertRaises(HTTPException) as e:
            self.post()
        self.assertEqual(e.exception.status_code, 400)

    def test_a_remote_that_is_not_a_clone_url_is_refused(self):
        with self.assertRaises(HTTPException) as e:
            self.post(remote_url="/etc/passwd")
        self.assertEqual(e.exception.status_code, 400)

    # 3. run state
    def test_a_finished_run_is_not_retargetable(self):
        self.run_row["status"] = "done"
        with self.assertRaises(HTTPException) as e:
            self.post(local_path=str(self.repo))
        self.assertEqual(e.exception.status_code, 409)

    def test_repointing_a_run_past_coding_at_a_new_repo_is_refused(self):
        self.run_row["product_repo"] = str(self.outside)
        self.run_row["current_stage"] = "05-post-coding"
        with self.assertRaises(HTTPException) as e:
            self.post(local_path=str(self.repo))
        self.assertEqual(e.exception.status_code, 409)
        self.assertIn("invalidate", e.exception.detail)

    def test_the_same_repo_past_coding_is_still_allowed(self):
        """Changing only the branch on a late-stage run must not be blocked."""
        self.run_row["product_repo"] = str(self.repo)
        self.run_row["current_stage"] = "05-post-coding"
        r = self.post(local_path=str(self.repo))
        self.assertEqual(r.status_code, 303)

    # 4. the write
    def test_save_writes_all_three_columns_and_logs_the_event(self):
        r = self.post(local_path=str(self.repo), base_branch="main")
        self.assertEqual(r.status_code, 303)
        self.assertTrue(r.headers["location"].endswith("/run/feat-20260907-x"))
        sql, args = self.conn.executed[-1]
        self.assertIn("product_repo", sql)
        self.assertIn("product_branch", sql)
        self.assertIn("product_working_branch", sql)
        self.assertEqual(args[0], str(self.repo))
        self.assertEqual(args[1], "main")
        self.assertIsNone(args[2], "an unset working branch must be NULL, not ''")
        self.assertEqual(len(self.events), 1)
        run_id, actor, typ, data = self.events[0]
        self.assertEqual(typ, "product_target_set")
        self.assertEqual(actor, "human:dimash")
        self.assertEqual(data["channel"], "web")

    def test_inspect_does_not_write(self):
        r = self.post(action="inspect", local_path=str(self.repo))
        self.assertEqual(r.status_code, 303)
        self.assertIn("/repo?repo=", r.headers["location"])
        self.assertEqual(self.conn.executed, [], "inspect must be read-only")
        self.assertEqual(self.events, [])

    def test_a_working_branch_outside_the_push_namespace_is_refused(self):
        """D6 bounds what an agent may push to. Refusing here beats refusing three
        stages later at handoff, and the user is sent back with the reason."""
        r = self.post(local_path=str(self.repo), working_branch="develop")
        self.assertEqual(r.status_code, 303)
        self.assertIn("error=", r.headers["location"])
        self.assertEqual(self.conn.executed, [], "a refused target must not be saved")

    def test_a_missing_base_branch_is_refused_with_the_branch_list(self):
        r = self.post(local_path=str(self.repo), base_branch="nope")
        self.assertEqual(r.status_code, 303)
        self.assertIn("error=", r.headers["location"])
        self.assertIn("branches", r.headers["location"])
        self.assertEqual(self.conn.executed, [])

    def test_a_working_branch_in_the_namespace_is_saved_even_when_it_is_new(self):
        r = self.post(local_path=str(self.repo), working_branch="feat/brand-new")
        self.assertEqual(r.status_code, 303)
        _sql, args = self.conn.executed[-1]
        self.assertEqual(args[2], "feat/brand-new",
                         "a branch that does not exist yet is created at first commit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
