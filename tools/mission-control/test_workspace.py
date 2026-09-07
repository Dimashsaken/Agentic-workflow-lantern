"""Proof that the repo picker's filesystem boundary holds (D15).

    ..\\..\\tools\\azure-runner\\.venv\\Scripts\\python -m unittest test_workspace -v

This is the security test of the codebase-connection feature. A repo picker on a web
UI is a filesystem-read primitive: whatever path it admits gets cloned by the host,
bind-mounted into a sandbox, read by agents through `read_file('product/…')`, and has
its own AGENTS.md pasted into a system prompt. Three properties have to hold, and each
is a way that could go wrong quietly:

1. **Unset fails CLOSED.** No configured roots must mean "offer nothing", never
   "offer everything". An over-broad default would hand the whole filesystem to
   anyone who can reach the login page.
2. **`contains()` cannot be walked out of.** Not with `..`, not with a symlink
   pointing outside a root — which is why both sides are resolved before comparing.
3. **The walk is bounded and total.** Depth, count and an unreadable subdirectory
   must not turn a page render into a hang or a traceback.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import workspace  # noqa: E402


def make_repo(path: Path) -> Path:
    """A directory that reads as a git repo — the picker never runs git to decide."""
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir()
    (path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    return path


class WorkspaceRootsTest(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("LANTERN_WORKSPACE_ROOTS")
        workspace._cache.clear()

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("LANTERN_WORKSPACE_ROOTS", None)
        else:
            os.environ["LANTERN_WORKSPACE_ROOTS"] = self._saved
        workspace._cache.clear()

    def test_unset_offers_nothing_when_there_is_no_home_work_dir(self):
        os.environ.pop("LANTERN_WORKSPACE_ROOTS", None)
        home_work = Path.home() / workspace.DEFAULT_ROOT_NAME
        roots = workspace.workspace_roots()
        if home_work.is_dir():
            self.assertEqual(roots, [home_work.resolve()],
                             "unset must fall back to ~/work and nothing else")
        else:
            self.assertEqual(roots, [], "unset with no ~/work must offer NOTHING")

    def test_nonexistent_and_empty_entries_are_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            real = Path(td) / "real"
            real.mkdir()
            os.environ["LANTERN_WORKSPACE_ROOTS"] = os.pathsep.join(
                [str(real), "", str(Path(td) / "does-not-exist")])
            self.assertEqual(workspace.workspace_roots(), [real.resolve()])

    def test_multiple_roots_are_all_honoured(self):
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td) / "a", Path(td) / "b"
            a.mkdir(); b.mkdir()
            os.environ["LANTERN_WORKSPACE_ROOTS"] = os.pathsep.join([str(a), str(b)])
            self.assertEqual(set(workspace.workspace_roots()), {a.resolve(), b.resolve()})


class ContainsTest(unittest.TestCase):
    """contains() is the ONLY admission point a write route may use."""

    def setUp(self):
        self._saved = os.environ.get("LANTERN_WORKSPACE_ROOTS")
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name).resolve()
        self.root = self.tmp / "roots"
        self.repo = make_repo(self.root / "myrepo")
        self.outside = make_repo(self.tmp / "outside" / "secret")
        os.environ["LANTERN_WORKSPACE_ROOTS"] = str(self.root)
        workspace._cache.clear()

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("LANTERN_WORKSPACE_ROOTS", None)
        else:
            os.environ["LANTERN_WORKSPACE_ROOTS"] = self._saved
        self._td.cleanup()
        workspace._cache.clear()

    def test_admits_a_repo_inside_a_root(self):
        self.assertEqual(workspace.contains(str(self.repo)), self.repo.resolve())

    def test_refuses_a_repo_outside_every_root(self):
        self.assertIsNone(workspace.contains(str(self.outside)))

    def test_refuses_a_dot_dot_traversal(self):
        escape = str(self.root / "myrepo" / ".." / ".." / "outside" / "secret")
        self.assertIsNone(workspace.contains(escape))

    def test_refuses_a_directory_that_is_not_a_repo(self):
        plain = self.root / "notarepo"
        plain.mkdir()
        self.assertIsNone(workspace.contains(str(plain)))

    def test_refuses_empty_and_whitespace(self):
        for bad in ("", "   ", None and ""):
            self.assertIsNone(workspace.contains(bad or ""))

    @unittest.skipUnless(hasattr(os, "symlink"), "no symlink support")
    def test_refuses_a_symlink_inside_a_root_pointing_outside(self):
        link = self.root / "sneaky"
        try:
            os.symlink(self.outside, link, target_is_directory=True)
        except (OSError, NotImplementedError) as e:
            self.skipTest(f"symlink creation not permitted here: {e}")
        # The link IS inside a root and IS a git repo. It must still be refused:
        # resolving both sides is what makes that true.
        self.assertIsNone(workspace.contains(str(link)),
                          "a symlink out of a root is the classic bypass")

    def test_unset_roots_admits_nothing(self):
        os.environ["LANTERN_WORKSPACE_ROOTS"] = str(self.tmp / "nowhere")
        self.assertIsNone(workspace.contains(str(self.repo)))


class DiscoverTest(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("LANTERN_WORKSPACE_ROOTS")
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name).resolve()
        os.environ["LANTERN_WORKSPACE_ROOTS"] = str(self.root)
        workspace._cache.clear()

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("LANTERN_WORKSPACE_ROOTS", None)
        else:
            os.environ["LANTERN_WORKSPACE_ROOTS"] = self._saved
        self._td.cleanup()
        workspace._cache.clear()

    def names(self):
        return {r["name"] for r in workspace.discover_repos(use_cache=False)}

    def test_finds_repos_and_reads_their_branch(self):
        make_repo(self.root / "alpha")
        (self.root / "beta").mkdir()
        make_repo(self.root / "beta" / "nested")
        (self.root / "beta" / "nested" / ".git" / "HEAD").write_text(
            "ref: refs/heads/feat/thing\n", encoding="utf-8")
        found = {r["name"]: r for r in workspace.discover_repos(use_cache=False)}
        self.assertEqual(set(found), {"alpha", "nested"})
        self.assertEqual(found["nested"]["head_branch"], "feat/thing")

    def test_a_repo_is_a_leaf_and_is_not_descended_into(self):
        make_repo(self.root / "outer")
        make_repo(self.root / "outer" / "vendored")
        self.assertEqual(self.names(), {"outer"},
                         "descending into a repo would surface vendored submodules")

    def test_skips_expensive_and_hidden_directories(self):
        make_repo(self.root / "node_modules" / "pkg")
        make_repo(self.root / ".hidden" / "repo")
        make_repo(self.root / "real")
        self.assertEqual(self.names(), {"real"})

    def test_respects_max_depth(self):
        make_repo(self.root / "a" / "b" / "c" / "d" / "deep")
        self.assertEqual(
            workspace.discover_repos(max_depth=2, use_cache=False), [],
            "a repo below the depth cap must not be surfaced")

    def test_a_root_that_is_itself_a_repo_counts(self):
        make_repo(self.root)
        self.assertEqual(len(workspace.discover_repos(use_cache=False)), 1)

    def test_detached_head_is_reported_not_crashed_on(self):
        r = make_repo(self.root / "detached")
        (r / ".git" / "HEAD").write_text("a" * 40 + "\n", encoding="utf-8")
        found = workspace.discover_repos(use_cache=False)
        self.assertIn("detached", found[0]["head_branch"])

    def test_a_git_FILE_is_a_repo_too(self):
        """Linked worktrees carry a .git FILE. Missing that case would make every
        worktree on a developer's machine invisible to the picker."""
        wt = self.root / "worktree"
        wt.mkdir()
        (wt / ".git").write_text("gitdir: /somewhere/else/.git/worktrees/x\n",
                                 encoding="utf-8")
        self.assertEqual(self.names(), {"worktree"})

    def test_unreadable_subdirectory_does_not_break_the_walk(self):
        make_repo(self.root / "fine")
        blocked = self.root / "blocked"
        blocked.mkdir()
        real_scandir = os.scandir

        def fake_scandir(path):
            if str(path) == str(blocked):
                raise PermissionError("nope")
            return real_scandir(path)

        os.scandir = fake_scandir
        try:
            self.assertEqual(self.names(), {"fine"})
        finally:
            os.scandir = real_scandir

    def test_no_roots_means_no_results(self):
        os.environ["LANTERN_WORKSPACE_ROOTS"] = str(self.root / "nope")
        self.assertEqual(workspace.discover_repos(use_cache=False), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
