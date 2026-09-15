"""Proof for the Repositories pages, Start work and the run page's destination card (D27).

    ..\\azure-runner\\.venv\\Scripts\\python -m unittest test_repos_routes -v

Stdlib only: routes are called as coroutines (the venv has no httpx, so no TestClient)
against fakes.FakePool, which records every write. The readiness check is replaced by a
recorder where a test needs a remote repository, and pipeline.py's `run` command by a
recorder in the Start work tests: no network, no fetch, no database.

What must hold:

1. **Auth first, on every write.** An anonymous POST is 401 whatever it carries.
2. **Connecting is confined and honest.** A path outside LANTERN_WORKSPACE_ROOTS is 400;
   the factory's own repository is refused unless the dogfood box is ticked; every
   spelling of a URL is checked as one canonical URL; a repository the host cannot read is
   still recorded, so its page can say which access to grant; the write is an upsert plus
   a `repo_connected` event from the signed-in human.
3. **Starting work is repo-first and goes through pipeline.py.** No usable repository, the
   factory without dogfood, and the coding agent on a repository it cannot publish to are
   refused on the form, which keeps what was typed; a good form writes the brief and calls
   `cmd_run` with the repository's canonical URL, as the signed-in human.
4. **The pages say where code lands.** /repos lists connected repositories and the ones runs
   point at without a connection; /repos/<id> shows the checklist and each run's branch and
   pull request; the per-run picker offers connected repositories first; the run page shows
   the destination card with the pull request.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ["LANTERN_WEB_USERS"] = "tester:pw,dimash:pw,justin:pw"   # same set as test_routes_v3
os.environ.setdefault("LANTERN_DATABASE_URL", "postgresql+asyncpg://lantern:none@localhost:5432/lantern")

import app as mc  # noqa: E402
import product_repos  # noqa: E402
import workspace  # noqa: E402
from fakes import NOW, FakePool, Req, approval_row, body_of, get, repo_row, run_row, signed  # noqa: E402
from fastapi import HTTPException  # noqa: E402

GH = "https://github.com/Career-Hackers/careerhackers-ai-ats"


def make_repo(path: Path, files=None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.invalid"),
                 ("config", "user.name", "t"), ("config", "commit.gpgsign", "false")):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)
    for name, text in (files or {"README.md": "# app\n"}).items():
        (path / name).write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True, capture_output=True)
    return path


def ready_check(url=GH, **over) -> dict:
    res = {"ref": url, "repo": url, "kind": product_repos.kind(url), "name": product_repos.display_name(url),
           "id": product_repos.repo_id(url), "is_factory": False, "reachable": True, "error": None,
           "branches": ["feat/20260901-old", "main"], "branch_count": 2, "default_branch": "main",
           "base": "main", "base_exists": True, "base_sha": "a" * 40,
           "gate": {"present": True, "test": "npm test", "error": None}, "docs": ["AGENTS.md"],
           "github": None, "publish": "pull_request", "usable": True, "ready": True, "auto_ready": True,
           "items": [{"key": "access", "state": "ok", "title": "Reachable from this host", "detail": "2 branches.", "fix": ""},
                     {"key": "publish", "state": "ok", "title": "Pull requests open automatically", "detail": "", "fix": ""}],
           "checked_at": "2026-09-15T08:00:00+00:00"}
    res.update(over)
    return res


class Base(unittest.TestCase):
    def setUp(self):
        # A short path: long Windows paths break git.
        self.tmp = Path(tempfile.mkdtemp(prefix="lrr-")).resolve()
        self.root = self.tmp / "roots"
        self.root.mkdir()
        self.saved = (os.environ.get("LANTERN_WORKSPACE_ROOTS"), product_repos.check,
                      product_repos.REPO, mc.cmd_run, mc.BRIEFS_DIR)
        os.environ["LANTERN_WORKSPACE_ROOTS"] = str(self.root)
        workspace._cache.clear()
        # The factory in these tests is a throwaway repository outside the roots.
        product_repos.REPO = make_repo(self.tmp / "factory-home")
        mc.BRIEFS_DIR = self.tmp / "briefs"
        self.checks = []

    def tearDown(self):
        env, product_repos.check, product_repos.REPO, mc.cmd_run, mc.BRIEFS_DIR = self.saved
        if env is None:
            os.environ.pop("LANTERN_WORKSPACE_ROOTS", None)
        else:
            os.environ["LANTERN_WORKSPACE_ROOTS"] = env
        workspace._cache.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_check(self, answer):
        def check(ref, base=""):
            self.checks.append((ref, base))
            return answer(ref, base)
        product_repos.check = check

    @staticmethod
    def writes(pool, table):
        return [(s, a) for s, a in pool.executed if table in s]


class Connect(Base):
    def post(self, user="dimash", **form):
        params = {"remote_url": "", "local_path": "", "base_branch": "", "dogfood": ""}
        params.update(form)
        self.pool = FakePool()
        return get(mc.connect_repo, signed(user) if user else Req(), pool=self.pool, **params)

    def test_anonymous_is_401_before_the_input_is_read(self):
        with self.assertRaises(HTTPException) as cm:
            self.post(user=None, local_path="/definitely/not/here")
        self.assertEqual(cm.exception.status_code, 401)

    def test_a_path_outside_the_roots_is_400_naming_the_boundary(self):
        outside = make_repo(self.tmp / "elsewhere")
        with self.assertRaises(HTTPException) as cm:
            self.post(local_path=str(outside))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("LANTERN_WORKSPACE_ROOTS", cm.exception.detail)

    def test_nothing_both_or_something_that_is_not_a_url_is_400(self):
        repo = make_repo(self.root / "app")
        for form in ({}, {"local_path": str(repo), "remote_url": GH}, {"remote_url": "/etc/passwd"},
                     {"remote_url": "careerhackers"}):
            with self.subTest(form=form), self.assertRaises(HTTPException) as cm:
                self.post(**form)
            self.assertEqual(cm.exception.status_code, 400)

    def test_a_checkout_in_the_roots_is_checked_for_real_and_recorded(self):
        repo = make_repo(self.root / "app", {"lantern.toml": "[quality]\ntest = \"pytest -q\"\n"})
        r = self.post(local_path=str(repo))
        rid = product_repos.repo_id(str(repo))
        self.assertEqual((r.status_code, r.headers["location"]), (303, f"/repos/{rid}"))
        (_sql, args), = self.writes(self.pool, "INSERT INTO product_repos")
        self.assertEqual((args[0], args[1], args[3], args[5], args[7]), (rid, str(repo), "local", False, "dimash"))
        stored = json.loads(args[6])
        self.assertTrue(stored["usable"])
        self.assertEqual(stored["gate"]["test"], "pytest -q")
        (_esql, event), = self.writes(self.pool, "INSERT INTO events")
        self.assertEqual((event[0], event[1], event[2]), (None, "human:dimash", "repo_connected"))
        self.assertEqual(json.loads(event[3])["channel"], "web")

    def test_the_factory_needs_the_dogfood_box(self):
        factory = make_repo(self.root / "lantern")
        product_repos.REPO = factory
        r = self.post(local_path=str(factory))
        self.assertEqual(r.status_code, 303)
        self.assertTrue(r.headers["location"].startswith("/repos?error="))
        self.assertIn("factory's own repository", unquote(r.headers["location"]))
        self.assertEqual(self.pool.executed, [], "a refused repository is not recorded")
        self.post(local_path=str(factory), dogfood="1")
        (_sql, args), = self.writes(self.pool, "INSERT INTO product_repos")
        self.assertTrue(args[5], "recorded as the factory")

    def test_every_spelling_is_one_url_and_an_unreachable_repository_is_still_recorded(self):
        self.fake_check(lambda ref, base: ready_check(
            ref, reachable=False, usable=False, ready=False, auto_ready=False, base_exists=False,
            items=[{"key": "access", "state": "fail", "title": "This host cannot read the repository",
                    "detail": "403", "fix": "invite lantern-bot"}]))
        r = self.post(remote_url="git@github.com:Career-Hackers/careerhackers-ai-ats.git")
        self.assertEqual(self.checks, [(GH, "")])
        self.assertEqual(r.headers["location"], f"/repos/{product_repos.repo_id(GH)}")
        (_sql, args), = self.writes(self.pool, "INSERT INTO product_repos")
        self.assertEqual(args[1], GH)
        self.assertFalse(json.loads(args[6])["reachable"])

    def test_a_named_base_branch_that_does_not_exist_goes_back_with_the_branches(self):
        self.fake_check(lambda ref, base: ready_check(ref, base=base, base_exists=False, usable=False))
        r = self.post(remote_url=GH, base_branch="develop")
        self.assertIn("error=", r.headers["location"])
        self.assertIn("feat/20260901-old", unquote(r.headers["location"]))
        self.assertEqual(self.pool.executed, [])


class RepoWrites(Base):
    def test_recheck_and_archive_are_auth_first_and_404_for_an_unknown_repository(self):
        for route in (mc.recheck_repo, mc.archive_repo):
            with self.subTest(route=route.__name__):
                with self.assertRaises(HTTPException) as cm:
                    get(route, "x", Req(), pool=FakePool())
                self.assertEqual(cm.exception.status_code, 401)
                with self.assertRaises(HTTPException) as cm:
                    get(route, "x", signed(), pool=FakePool())
                self.assertEqual(cm.exception.status_code, 404)

    def test_recheck_replaces_the_stored_check(self):
        row = repo_row(url=GH, check=ready_check(reachable=False, usable=False))
        self.fake_check(lambda ref, base: ready_check(ref))
        pool = FakePool(repos=[row])
        r = get(mc.recheck_repo, row["id"], signed(), pool=pool)
        self.assertEqual(r.headers["location"], f"/repos/{row['id']}")
        self.assertEqual(self.checks, [(GH, "main")])
        (_sql, args), = self.writes(pool, "UPDATE product_repos SET check_result")
        self.assertTrue(json.loads(args[0])["usable"])

    def test_archive_hides_the_repository_and_leaves_an_event(self):
        row = repo_row(url=GH, check=ready_check())
        pool = FakePool(repos=[row])
        r = get(mc.archive_repo, row["id"], signed("justin"), pool=pool)
        self.assertEqual(r.headers["location"], "/repos")
        self.assertEqual(len(self.writes(pool, "SET archived = true")), 1)
        (_sql, event), = self.writes(pool, "INSERT INTO events")
        self.assertEqual((event[1], event[2]), ("human:justin", "repo_archived"))


class StartWork(Base):
    def setUp(self):
        super().setUp()
        self.calls = []

        async def fake_run(brief, run_id, by, follow, repo, base, mode, working, design, dogfood=False):
            self.calls.append({"brief": brief, "run_id": run_id, "by": by, "repo": repo, "base": base,
                               "mode": mode, "working": working, "design": design, "dogfood": dogfood})
        mc.cmd_run = fake_run
        self.row = repo_row(url=GH, check=ready_check())

    def post(self, rows=None, user="dimash", **form):
        params = {"repo_id": self.row["id"], "title": "Bulk export", "problem": "Recruiters copy rows by hand.",
                  "must_haves": "CSV\nXLSX", "base_branch": "main", "working_branch": "",
                  "coding_mode": "auto", "design_mode": "html", "dogfood": ""}
        params.update(form)
        self.pool = FakePool(repos=rows if rows is not None else [self.row])
        return get(mc.start_work, signed(user) if user else Req(), pool=self.pool, **params)

    def test_anonymous_is_401(self):
        with self.assertRaises(HTTPException) as cm:
            self.post(user=None)
        self.assertEqual(cm.exception.status_code, 401)

    def test_a_good_form_writes_the_brief_and_starts_the_run_on_the_repository(self):
        r = self.post()
        self.assertEqual(r.status_code, 303)
        (call,) = self.calls
        self.assertRegex(call["run_id"], r"^feat-\d{8}-bulk-export$")
        self.assertEqual(r.headers["location"], f"/run/{call['run_id']}")
        self.assertEqual((call["repo"], call["base"], call["mode"], call["design"], call["by"], call["dogfood"]),
                         (GH, "main", "auto", "html", "dimash", False))
        brief = Path(call["brief"]).read_text(encoding="utf-8")
        for line in (f"- **Product repo:** {GH}", "- **Base branch:** main", "- **Coding mode:** auto",
                     "- **Design mode:** html", "- **Assigned developer:** dimash", "- CSV", "- XLSX"):
            self.assertIn(line, brief)

    def test_refusals_keep_what_was_typed_and_start_nothing(self):
        unusable = repo_row(url=GH, check=ready_check(reachable=False, usable=False))
        factory_url = "https://github.com/Acme/Lantern"
        factory = repo_row(url=factory_url, is_factory=True, check=ready_check(factory_url, is_factory=True))
        no_push = repo_row(url=GH, check=ready_check(items=[{"key": "publish", "state": "fail",
                                                             "title": "The bot token can read but not push",
                                                             "detail": "", "fix": ""}]))
        cases = [
            ({"repo_id": "nope"}, None, "Pick one of the connected repositories"),
            ({"title": ""}, None, "Missing a title"),
            ({}, [unusable], "is not usable yet"),
            ({"repo_id": factory["id"]}, [factory], "factory&#x27;s own repository"),
            ({}, [no_push], "could not publish"),
            ({"coding_mode": "robot"}, None, "Coding mode must be one of"),
        ]
        for form, rows, needle in cases:
            with self.subTest(needle=needle):
                self.calls.clear()
                r = self.post(rows=rows, **form)
                html = body_of(r)
                self.assertEqual(r.status_code, 400)
                self.assertIn(needle, html)
                self.assertIn("Recruiters copy rows by hand.", html, "the form keeps what was typed")
                self.assertEqual(self.calls, [])

    def test_the_factory_with_dogfood_starts_a_dogfood_run(self):
        factory_url = "https://github.com/Acme/Lantern"
        factory = repo_row(url=factory_url, is_factory=True, check=ready_check(factory_url, is_factory=True))
        self.post(rows=[factory], repo_id=factory["id"], dogfood="1", coding_mode="human")
        (call,) = self.calls
        self.assertEqual((call["repo"], call["dogfood"], call["mode"]), (factory_url, True, "human"))

    def test_a_pipeline_refusal_is_shown_on_the_form(self):
        async def refuse(*a, **k):
            raise SystemExit("branch 'main' not found in https://github.com/Career-Hackers/careerhackers-ai-ats")
        mc.cmd_run = refuse
        r = self.post()
        self.assertEqual(r.status_code, 400)
        self.assertIn("branch &#x27;main&#x27; not found", body_of(r))


class Pages(Base):
    def test_repositories_lists_connected_and_unconnected_repositories(self):
        pool = FakePool(repos=[repo_row(url=GH, check=ready_check())],
                        runs=[run_row(id="feat-20260915-a", product_repo=GH + ".git"),
                              run_row(id="feat-20260915-b", product_repo="https://github.com/Dimashsaken/tender-whatsapp")])
        html = body_of(get(mc.repos_page, signed(), pool=pool))
        self.assertIn("Career-Hackers/careerhackers-ai-ats", html)
        self.assertIn("1 run", html, "the .git spelling is the same repository")
        self.assertIn("Used by runs, not connected", html)
        self.assertIn("Dimashsaken/tender-whatsapp", html)
        self.assertIn("How work reaches a repository", html)
        self.assertIn(">Ready<", html)
        self.assertIn("href='/repos' class=on aria-current=page", html)

    def test_a_clone_of_the_factory_in_the_list_is_not_offered_as_one_click_connect(self):
        factory = make_repo(self.tmp / "lantern-main")
        product_repos.REPO = factory
        clone = self.tmp / "lantern-clone"
        subprocess.run(["git", "clone", "-q", str(factory), str(clone)], check=True, capture_output=True)
        pool = FakePool(runs=[run_row(id="feat-20260915-c", product_repo=str(clone))])
        html = body_of(get(mc.repos_page, signed(), pool=pool))
        self.assertIn("Factory repository: connect it below with the dogfood box ticked", html)
        self.assertNotIn(f"value='{clone}'><button", html)

    def test_a_repository_page_shows_its_checklist_and_where_each_run_is(self):
        check = ready_check(reachable=False, usable=False, items=[
            {"key": "access", "state": "fail", "title": "This host cannot read the repository",
             "detail": "403", "fix": "Give the bot account `lantern-bot` access."}])
        row = repo_row(url=GH, check=check)
        run_id = "feat-20260915-a"
        pool = FakePool(
            repos=[row],
            runs=[run_row(id=run_id, product_repo=GH, product_branch="main", coding_mode="auto",
                          current_stage="04-qa-dev", status="running")],
            events=[{"run_id": run_id, "actor": "orchestrator", "type": "branch_published", "at": NOW,
                     "data": json.dumps({"branch": "feat/20260915-a", "pushed": True,
                                         "pr_url": GH + "/pull/7", "head_sha": "b" * 40})}],
            approvals=[approval_row(run_id=run_id, gate="code_complete", status="approved",
                                    payload=json.dumps({"pr_url": GH + "/pull/7", "pr_number": 7}))])
        html = body_of(get(mc.repo_page, row["id"], signed(), pool=pool))
        self.assertIn("Needs access", html)
        self.assertIn("<code>lantern-bot</code>", html)
        self.assertIn("<code>feat/20260915-a</code>", html)
        self.assertIn(GH + "/pull/7", html)
        self.assertIn("aria-disabled='true'", html, "no Start work on an unusable repository")
        with self.assertRaises(HTTPException) as cm:
            get(mc.repo_page, "nope", signed(), pool=pool)
        self.assertEqual(cm.exception.status_code, 404)

    def test_start_work_preselects_the_repository_and_previews_the_branch(self):
        other = repo_row(url="https://github.com/Dimashsaken/tender-whatsapp", check=ready_check(
            "https://github.com/Dimashsaken/tender-whatsapp", branches=["main", "feat/20260911-tender-onboarding"]))
        row = repo_row(url=GH, check=ready_check())
        html = body_of(get(mc.new_work_page, signed(), pool=FakePool(repos=[other, row]), repo=row["id"]))
        self.assertIn(f"<option value='{row['id']}' selected>", html)
        self.assertIn("id='pv-branch'>feat/", html)
        self.assertIn("<option>feat/20260901-old</option>", html, "continuing a branch is offered")
        self.assertIn("newwork-data", html)
        self.assertNotIn("</script><script>", html.split("newwork-data", 1)[1].split("</script>", 1)[0])

    def test_the_run_picker_offers_connected_repositories_first(self):
        repo = make_repo(self.root / "app")
        row = repo_row(url=str(repo), check=ready_check(str(repo)))
        pool = FakePool(runs=[run_row(id="feat-20260915-p", status="running", current_stage="02-pre-coding")],
                        repos=[row])
        html = body_of(get(mc.repo_picker, "feat-20260915-p", signed(), pool=pool))
        self.assertIn("Connected repositories", html)
        self.assertIn(f"name='connected' value='{row['id']}'", html)

    def test_saving_a_connected_repository_points_the_run_at_it(self):
        repo = make_repo(self.root / "app")
        row = repo_row(url=str(repo), check=ready_check(str(repo)))
        pool = FakePool(runs=[run_row(id="feat-20260915-p", status="running", current_stage="02-pre-coding")],
                        repos=[row])
        r = get(mc.set_repo, "feat-20260915-p", signed(), pool=pool, action="save", local_path="",
                remote_url="", base_branch="main", working_branch="", connected=row["id"], dogfood="")
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/run/feat-20260915-p"))
        (_sql, update), = self.writes(pool, "UPDATE runs SET product_repo")
        self.assertEqual(update[:2], (str(repo), "main"))
        (_sql, event), = self.writes(pool, "INSERT INTO events")
        data = json.loads(event[3])
        self.assertEqual((data["repo"], data["branch"], data["previous_repo"], data["channel"]),
                         (str(repo), "main", None, "web"))
        self.assertEqual(len(self.writes(pool, "INSERT INTO product_repos")), 1)

    def test_the_factory_can_be_inspected_but_not_saved_without_dogfood(self):
        factory = make_repo(self.root / "lantern")
        product_repos.REPO = factory
        form = {"local_path": str(factory), "remote_url": "", "base_branch": "main",
                "working_branch": "", "connected": ""}
        pool = FakePool(runs=[run_row(id="feat-20260915-p", status="running", current_stage="02-pre-coding")])
        r = get(mc.set_repo, "feat-20260915-p", signed(), pool=pool, action="inspect", dogfood="", **form)
        self.assertNotIn("error=", r.headers["location"])
        r = get(mc.set_repo, "feat-20260915-p", signed(), pool=pool, action="save", dogfood="", **form)
        self.assertIn("factory's own repository", unquote(r.headers["location"]))
        self.assertEqual(pool.executed, [])
        get(mc.set_repo, "feat-20260915-p", signed(), pool=pool, action="save", dogfood="1", **form)
        self.assertEqual(len(self.writes(pool, "UPDATE runs SET product_repo")), 1)

    def test_the_run_page_says_where_the_code_goes(self):
        run_id = "feat-20260915-dest"
        row = repo_row(url=GH, check=ready_check())
        pool = FakePool(
            runs=[run_row(id=run_id, status="running", current_stage="04-qa-dev", product_repo=GH,
                          product_branch="main", coding_mode="auto")],
            events=[{"run_id": run_id, "actor": "orchestrator", "type": "branch_published", "at": NOW,
                     "data": json.dumps({"branch": "feat/20260915-dest", "head_sha": "c" * 40,
                                         "pushed": True, "pr_url": GH + "/pull/12"})}],
            approvals=[approval_row(run_id=run_id, gate="code_complete", status="approved",
                                    decided_at=NOW, decided_by="justin",
                                    payload=json.dumps({"pr_url": GH + "/pull/12", "pr_number": 12}))],
            repos=[row])
        html = body_of(get(mc.run_page, run_id, signed(), pool=pool))
        self.assertIn("Where the code goes", html)
        self.assertIn("Code lands in", html)
        self.assertIn(f"href='/repos/{row['id']}'", html)
        self.assertIn("<code>feat/20260915-dest</code>", html)
        self.assertIn(GH + "/pull/12", html)
        self.assertIn("babysitter", html)
        self.assertIn(">Repository</a>", html, "the run tab says what it is")


if __name__ == "__main__":
    unittest.main(verbosity=2)
