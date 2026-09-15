"""Proof for the connected-repositories module (D27) — no database, no network.

    tools/azure-runner/.venv/Scripts/python tools/azure-runner/test_product_repos.py

What it pins down:

1. **One spelling per repository.** Every GitHub spelling (https, `.git`, a trailing
   slash, the scp and ssh forms, a pasted token) canonicalises to the same https URL and
   identity; credentials never survive; other hosts keep their path; a path resolves.
2. **The factory is recognised, and refused.** The factory checkout, a worktree and a
   clone of it, and its origin in any spelling are the factory; an unrelated repository
   is not. `verify_product_target` and `cmd_run` refuse it unless the caller says
   dogfood, and a run stores the canonical URL and registers the repository.
3. **The readiness checklist tells the truth.** Against real temporary repositories: the
   base branch, `lantern.toml` with and without a test command, agent docs, a checkout's
   in-place publishing. With a fake GitHub API: push permission, protection, a 404, a
   missing token, an unreachable repository, leased mode.
"""
import asyncio
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_repos as pr  # noqa: E402

PREFIXES = ("feat/", "fix/", "proto/")
GH = "https://github.com/Career-Hackers/careerhackers-ai-ats"


def git(*args, cwd):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr}")
    return r.stdout.strip()


def make_repo(path: Path, files=None, branch="main") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git("init", "-q", "-b", branch, cwd=path)
    git("config", "user.email", "test@example.invalid", cwd=path)
    git("config", "user.name", "test", cwd=path)
    git("config", "commit.gpgsign", "false", cwd=path)
    for name, text in (files or {"README.md": "# product\n"}).items():
        (path / name).write_text(text, encoding="utf-8")
    git("add", "-A", cwd=path)
    git("commit", "-q", "-m", "init", cwd=path)
    return path


def no_github(*_a, **_k):
    raise AssertionError("GitHub must not be asked about this target")


class FakeGitHub:
    def __init__(self, repo=(200, {"permissions": {"push": True}, "private": True}),
                 branch=(200, {"protected": True})):
        self.repo, self.branch, self.calls = repo, branch, []

    def __call__(self, method, path, data=None):
        self.calls.append((method, path))
        return self.branch if "/branches/" in path else self.repo


class TempDir(unittest.TestCase):
    def setUp(self):
        # A short path: long Windows paths break git worktrees and clones.
        self.tmp = Path(tempfile.mkdtemp(prefix="lpr-")).resolve()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class Spelling(unittest.TestCase):
    SPELLINGS = [
        GH, GH + ".git", GH + "/", f"  {GH}.git/  ", "https://GitHub.com/Career-Hackers/careerhackers-ai-ats",
        "git@github.com:Career-Hackers/careerhackers-ai-ats.git",
        "ssh://git@github.com/Career-Hackers/careerhackers-ai-ats",
        "https://x-access-token:ghp_secret123@github.com/Career-Hackers/careerhackers-ai-ats.git",
    ]

    def test_every_github_spelling_is_one_repository(self):
        ids = {pr.identity(s) for s in self.SPELLINGS}
        self.assertEqual(len(ids), 1)
        for s in self.SPELLINGS:
            with self.subTest(spelling=s):
                self.assertEqual(pr.canonical(s), GH)
                self.assertEqual(pr.kind(s), "github")
                self.assertEqual(pr.display_name(s), "Career-Hackers/careerhackers-ai-ats")
                self.assertEqual(pr.repo_id(s), pr.repo_id(GH))
        self.assertNotIn("ghp_secret123", pr.canonical(self.SPELLINGS[-1]))
        self.assertEqual(pr.identity("https://github.com/career-hackers/CAREERHACKERS-AI-ATS"),
                         pr.identity(GH), "GitHub names are case-insensitive")
        self.assertTrue(pr.repo_id(GH).startswith("career-hackers-careerhackers-ai-ats-"))

    def test_other_hosts_keep_their_path_but_compare_equal(self):
        self.assertEqual(pr.canonical("https://git.Example.com/team/app.git/"),
                         "https://git.example.com/team/app.git")
        self.assertEqual(pr.identity("https://git.example.com/team/app.git"),
                         pr.identity("https://GIT.example.com/team/app"))
        self.assertEqual(pr.canonical("https://bob:pw@git.example.com/team/app"),
                         "https://git.example.com/team/app")
        self.assertEqual(pr.kind("https://git.example.com/team/app"), "https")
        self.assertEqual(pr.kind("http://git.example.com/team/app"), "http")
        self.assertEqual(pr.kind("git@git.example.com:team/app.git"), "ssh")
        self.assertEqual(pr.kind("ssh://git@git.example.com/team/app"), "ssh")
        self.assertEqual(pr.display_name("git@git.example.com:team/app.git"), "team/app")

    def test_paths_resolve_and_non_references_are_nothing(self):
        for ref in ("/srv/app", "./app", "~/work/app", "C:\\work\\app", "C:/work/app"):
            with self.subTest(ref=ref):
                self.assertEqual(pr.kind(ref), "local")
        self.assertEqual(pr.canonical("."), str(Path(".").resolve()))
        self.assertEqual(pr.identity("."), pr.identity(str(Path(".").resolve()) + "/"))
        for ref in ("", "   ", "app", "github.com/o/r", "https://"):
            with self.subTest(ref=ref):
                self.assertEqual(pr.kind(ref), "")
        self.assertEqual(pr.repo_id(""), "")


class Factory(TempDir):
    def setUp(self):
        super().setUp()
        self.factory = make_repo(self.tmp / "factory")
        git("remote", "add", "origin", "https://github.com/Acme/Factory.git", cwd=self.factory)
        self._repo = pr.REPO
        pr.REPO = self.factory

    def tearDown(self):
        pr.REPO = self._repo
        super().tearDown()

    def test_the_checkout_its_worktree_clone_and_origin_are_the_factory(self):
        git("worktree", "add", "-q", str(self.tmp / "wt"), "-b", "wt", cwd=self.factory)
        clone = self.tmp / "clone"
        git("clone", "-q", str(self.factory), str(clone), cwd=self.tmp)
        mirror = self.tmp / "mirror.git"
        git("clone", "-q", "--mirror", str(self.factory), str(mirror), cwd=self.tmp)
        git("remote", "set-url", "origin", "https://github.com/acme/factory", cwd=mirror)
        for ref in (str(self.factory), str(self.factory) + "/", str(self.tmp / "wt"), str(clone),
                    str(mirror), "https://github.com/Acme/Factory", "git@github.com:acme/factory.git"):
            with self.subTest(ref=ref):
                self.assertTrue(pr.is_factory(ref))

    def test_a_list_of_checkouts_is_judged_without_starting_git(self):
        clone = self.tmp / "clone"
        git("clone", "-q", str(self.factory), str(clone), cwd=self.tmp)
        other = make_repo(self.tmp / "product")
        self.assertEqual(pr.identity(pr.origin_from_config(clone)), pr.identity(str(self.factory)))
        self.assertEqual(pr._config_value(r'"C:\\work\\app" ; note'), "C:\\work\\app")
        self.assertTrue(pr.looks_like_factory(str(clone)))
        self.assertTrue(pr.looks_like_factory(str(self.factory)))
        self.assertFalse(pr.looks_like_factory(str(other)))
        self.assertEqual(pr.origin_from_config(self.tmp / "missing"), "")

    def test_an_unrelated_repository_is_not(self):
        other = make_repo(self.tmp / "product")
        self.assertFalse(pr.is_factory(str(other)))
        self.assertFalse(pr.is_factory(GH))
        self.assertFalse(pr.is_factory(""))

    def test_verify_product_target_refuses_the_factory_unless_it_is_dogfood(self):
        import pipeline
        with self.assertRaises(pipeline.ProductTargetError) as cm:
            pipeline.verify_product_target(str(self.factory), "main")
        self.assertIn("factory's own repository", str(cm.exception))
        self.assertIn("--dogfood", str(cm.exception))
        info = pipeline.verify_product_target(str(self.factory), "main", allow_factory=True)
        self.assertEqual(len(info["base_sha"]), 40)
        other = make_repo(self.tmp / "product")
        self.assertEqual(len(pipeline.verify_product_target(str(other), "main")["base_sha"]), 40)

    def test_the_check_flags_the_factory(self):
        res = pr.check(str(self.factory), "", sync=Path, git=pr.run_git, gh_api=no_github,
                       token=False, leased=False, prefixes=PREFIXES)
        self.assertTrue(res["is_factory"])
        self.assertTrue(res["usable"])
        self.assertFalse(res["ready"])
        self.assertEqual(res["items"][0]["key"], "factory")
        self.assertEqual(pr.status(res), ("Factory · dogfood only", "warn"))
        self.assertIn("=> Factory - dogfood only", pr.render_text(res))
        pr.render_text(res).encode("ascii")          # prints on a cp1252 console


class RecordingConn:
    def __init__(self):
        self.executed = []

    async def execute(self, sql, *args):
        self.executed.append((" ".join(sql.split()), args))
        return "OK"

    async def fetchrow(self, sql, *args):
        return None

    async def fetch(self, sql, *args):
        return []

    async def fetchval(self, sql, *args):
        return None

    async def close(self):
        return None


class RunCreation(TempDir):
    """`pipeline.py run` is where the Tender briefs pointed runs at this repository."""

    def setUp(self):
        super().setUp()
        import pipeline
        self.p = pipeline
        self.factory = make_repo(self.tmp / "factory")
        self.saved = (pr.REPO, pipeline.REPO, pipeline.connect, pipeline.verify_product_target,
                      pipeline.render_runboard)
        pr.REPO = self.factory
        pipeline.REPO = self.tmp / "control"          # run folders land here, not in this repo
        self.brief = self.tmp / "brief.md"
        self.brief.write_text("# Feature Brief: x\n\n- **Base branch:** main\n", encoding="utf-8")

    def tearDown(self):
        (pr.REPO, self.p.REPO, self.p.connect, self.p.verify_product_target,
         self.p.render_runboard) = self.saved
        super().tearDown()

    def test_a_run_pointed_at_the_factory_is_refused_before_anything_is_written(self):
        async def no_db():
            raise AssertionError("refused runs must not reach the database")
        self.p.connect = no_db
        with self.assertRaises(SystemExit) as cm:
            asyncio.run(self.p.cmd_run(str(self.brief), "feat-20260915-x", "t", False, str(self.factory)))
        self.assertIn("factory's own repository", str(cm.exception))
        self.assertFalse((self.tmp / "control").exists())

    def test_dogfood_gets_past_the_guard(self):
        class Reached(Exception):
            pass

        async def stop():
            raise Reached()
        self.p.connect = stop
        with self.assertRaises(Reached):
            asyncio.run(self.p.cmd_run(str(self.brief), "feat-20260915-x", "t", False,
                                       str(self.factory), dogfood=True))

    def test_a_run_stores_the_canonical_url_and_registers_the_repository(self):
        conn = RecordingConn()

        async def fake_connect():
            return conn

        async def no_render(_conn):
            return None
        self.p.connect, self.p.render_runboard = fake_connect, no_render
        self.p.verify_product_target = lambda repo, base, working="", allow_factory=False: {
            "working": "", "base_sha": "0" * 40, "working_sha": None}
        asyncio.run(self.p.cmd_run(str(self.brief), "feat-20260915-x", "t", False,
                                   "git@github.com:Acme/App.git"))
        insert = next(a for s, a in conn.executed if s.startswith("INSERT INTO runs"))
        self.assertEqual(insert[5], "https://github.com/Acme/App")
        registry = [a for s, a in conn.executed if s.startswith("INSERT INTO product_repos")]
        self.assertEqual(len(registry), 1)
        self.assertEqual(registry[0][1], "https://github.com/Acme/App")
        self.assertEqual(registry[0][2], "Acme/App")


class LocalCheck(TempDir):
    def check(self, repo, base="", **kw):
        opts = dict(sync=Path, git=pr.run_git, gh_api=no_github, token=False, leased=False,
                    prefixes=PREFIXES)
        opts.update(kw)
        return pr.check(str(repo), base, **opts)

    def states(self, res):
        return {i["key"]: i["state"] for i in res["items"]}

    def test_a_ready_checkout(self):
        repo = make_repo(self.tmp / "app", {
            "lantern.toml": "[quality]\ntest = \"python -m pytest -q\"\n",
            "AGENTS.md": "# app\n", "README.md": "# app\n"})
        res = self.check(repo)
        self.assertTrue(res["reachable"] and res["base_exists"] and res["ready"] and res["auto_ready"])
        self.assertEqual(res["base"], "main")
        self.assertEqual(res["gate"]["test"], "python -m pytest -q")
        self.assertEqual(res["publish"], "in_place")
        self.assertEqual(self.states(res), {"access": "ok", "base": "ok", "gate": "ok", "docs": "ok",
                                            "publish": "warn"})
        self.assertIn("no pull request", res["items"][-1]["title"])
        self.assertEqual(pr.status(res), ("Ready", "ok"))
        self.assertIn("[ok  ] Base branch `main` exists", pr.render_text(res))

    def test_no_quality_gate_means_human_coding_only(self):
        res = self.check(make_repo(self.tmp / "app"))
        gate = next(i for i in res["items"] if i["key"] == "gate")
        self.assertEqual(gate["state"], "warn")
        self.assertIn("init-product", gate["fix"])
        self.assertTrue(res["ready"])
        self.assertFalse(res["auto_ready"])
        self.assertEqual(pr.status(res), ("Ready for human coding", "warn"))
        self.assertEqual(self.states(res)["docs"], "warn")

    def test_a_gate_without_a_test_command_is_not_enough(self):
        res = self.check(make_repo(self.tmp / "app", {"lantern.toml": "[quality]\nlint = \"x\"\n"}))
        self.assertTrue(res["gate"]["present"])
        self.assertEqual(next(i for i in res["items"] if i["key"] == "gate")["title"],
                         "lantern.toml has no test command")
        self.assertFalse(res["auto_ready"])

    def test_a_missing_base_branch_lists_what_exists(self):
        res = self.check(make_repo(self.tmp / "app"), "develop")
        base = next(i for i in res["items"] if i["key"] == "base")
        self.assertEqual(base["state"], "fail")
        self.assertIn("`main`", base["detail"])
        self.assertFalse(res["ready"])
        self.assertEqual(pr.status(res), ("Base branch missing", "blocked"))

    def test_the_default_branch_is_found_when_it_is_not_main(self):
        res = self.check(make_repo(self.tmp / "app", branch="trunk"))
        self.assertEqual((res["default_branch"], res["base"], res["base_exists"]), ("trunk", "trunk", True))

    def test_leased_publication_cannot_use_a_checkout(self):
        res = self.check(make_repo(self.tmp / "app"), leased=True)
        self.assertEqual(self.states(res)["publish"], "fail")
        self.assertEqual(pr.status(res), ("Needs attention", "blocked"))

    def test_something_that_is_not_a_repository(self):
        res = pr.check("not a repo", "", sync=no_github, git=no_github, gh_api=no_github,
                       token=False, leased=False, prefixes=PREFIXES)
        self.assertEqual(res["items"][0]["key"], "reference")
        self.assertEqual(pr.status(res), ("Not a repository", "blocked"))


class GitHubCheck(TempDir):
    def setUp(self):
        super().setUp()
        source = make_repo(self.tmp / "src", {"lantern.toml": "[quality]\ntest = \"npm test\"\n",
                                              "AGENTS.md": "# a\n"})
        self.mirror = self.tmp / "mirror.git"
        git("clone", "-q", "--mirror", str(source), str(self.mirror), cwd=self.tmp)

    def check(self, gh=None, token=True, sync=None, base="", ref=GH):
        return pr.check(ref, base, sync=sync or (lambda _c: self.mirror), git=pr.run_git,
                        gh_api=gh or FakeGitHub(), token=token, leased=False, prefixes=PREFIXES)

    def item(self, res, key):
        return next(i for i in res["items"] if i["key"] == key)

    def test_push_permission_and_protection_make_it_ready(self):
        gh = FakeGitHub()
        res = self.check(gh)
        self.assertEqual(res["publish"], "pull_request")
        self.assertEqual(self.item(res, "publish")["state"], "ok")
        self.assertIn("`feat/*`", self.item(res, "publish")["detail"])
        self.assertEqual(self.item(res, "protection")["state"], "ok")
        self.assertEqual(gh.calls, [("GET", "/repos/Career-Hackers/careerhackers-ai-ats"),
                                    ("GET", "/repos/Career-Hackers/careerhackers-ai-ats/branches/main")])
        self.assertEqual(pr.status(res), ("Ready", "ok"))

    def test_an_unprotected_base_is_a_warning_with_the_rule_to_add(self):
        res = self.check(FakeGitHub(branch=(200, {"protected": False})))
        self.assertEqual(self.item(res, "protection")["state"], "warn")
        self.assertIn("require a pull request", self.item(res, "protection")["fix"])

    def test_read_without_push_cannot_publish(self):
        res = self.check(FakeGitHub(repo=(200, {"permissions": {"pull": True, "push": False}})))
        self.assertEqual(self.item(res, "publish")["state"], "fail")
        self.assertFalse(res["auto_ready"])
        self.assertEqual(pr.status(res), ("Needs attention", "blocked"))

    def test_a_repository_github_hides_from_the_token(self):
        res = self.check(FakeGitHub(repo=(404, {"message": "Not Found"})))
        self.assertIn("lantern-bot", self.item(res, "publish")["fix"])
        self.assertIn("Career-Hackers/careerhackers-ai-ats", self.item(res, "publish")["fix"])

    def test_no_token_on_the_host(self):
        res = self.check(no_github, token=False)
        self.assertEqual(self.item(res, "publish")["title"], "No bot token on this host")

    def test_an_unreachable_repository_names_the_access_to_grant(self):
        def refused(_c):
            raise RuntimeError("product mirror clone failed: Cloning into bare repository "
                               "'C:\\Users\\x\\.lantern\\product-mirrors\\app.git'... remote: Write "
                               "access to repository not granted. fatal: unable to access: The requested "
                               "URL returned error: 403")
        res = self.check(no_github, sync=refused)
        self.assertFalse(res["reachable"])
        access = self.item(res, "access")
        self.assertEqual(access["state"], "fail")
        self.assertIn("403", access["detail"])
        self.assertTrue(access["detail"].startswith("remote: Write access"), access["detail"])
        self.assertIn("invite it as a collaborator", access["fix"])
        self.assertEqual(pr.status(res), ("Needs access", "blocked"))

    def test_non_github_hosts_push_without_a_pull_request_and_ssh_cannot_push(self):
        res = self.check(no_github, ref="https://git.example.com/team/app")
        self.assertEqual((res["publish"], self.item(res, "publish")["state"]), ("push", "warn"))
        res = self.check(no_github, ref="git@git.example.com:team/app.git")
        self.assertEqual(self.item(res, "publish")["state"], "fail")


class Registry(unittest.TestCase):
    def test_upsert_and_touch(self):
        conn = RecordingConn()
        res = {"id": pr.repo_id(GH), "repo": GH, "name": "Career-Hackers/careerhackers-ai-ats",
               "kind": "github", "base": "main", "is_factory": False, "items": []}
        self.assertEqual(asyncio.run(pr.upsert(conn, res, "dimash")), res["id"])
        sql, args = conn.executed[-1]
        self.assertIn("ON CONFLICT (id) DO UPDATE", sql)
        self.assertIn("archived = false", sql)
        self.assertEqual(args[:5], (res["id"], GH, res["name"], "github", "main"))
        asyncio.run(pr.touch(conn, GH + ".git", "main", "cli"))
        self.assertEqual(conn.executed[-1][1][1], GH)

    def test_touch_tolerates_a_database_without_the_table_only(self):
        class UndefinedTableError(Exception):
            pass

        class Broken(RecordingConn):
            def __init__(self, exc):
                super().__init__()
                self.exc = exc

            async def execute(self, sql, *args):
                raise self.exc

        asyncio.run(pr.touch(Broken(UndefinedTableError("no table")), GH, "main", "cli"))
        with self.assertRaises(ValueError):
            asyncio.run(pr.touch(Broken(ValueError("real bug")), GH, "main", "cli"))

    def test_a_stored_check_parses_from_text(self):
        self.assertEqual(pr.parse_check('{"a": 1}'), {"a": 1})
        self.assertIsNone(pr.parse_check("not json"))
        self.assertIsNone(pr.parse_check(None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
