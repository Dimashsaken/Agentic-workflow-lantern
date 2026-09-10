"""Mocked GitHub observations plus actual disposable local Git CAS controls."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

import github_publication as publication
import execution_leases as leases


REQUEST = {"run_id": "run", "repo": "https://github.com/owner/product.git",
           "branch": "feat/example", "work": "feat/example", "base": "main", "head_sha": "a" * 40}


def pr(head="a" * 40, number=7):
    return {"number": number, "html_url": f"https://github.com/owner/product/pull/{number}",
            "state": "open", "head": {"sha": head, "ref": "feat/example", "repo": {"full_name": "owner/product", "id": 123}},
            "base": {"ref": "main", "sha": "c" * 40, "repo": {"full_name": "owner/product", "id": 123}}}


class Provider:
    def __init__(self, head="a" * 40, prs=None):
        self.head, self.prs, self.calls = head, prs or [], []
        self.post_error = None
        self.pages = None
        self.repository_id, self.base_sha = 123, "c" * 40

    def api(self, method, path, data=None):
        self.calls.append((method, path, data))
        if path == "/repos/owner/product":
            return 200, {"id": self.repository_id, "full_name": "owner/product"}
        if path.endswith("/git/ref/heads/main"):
            return 200, {"ref": "refs/heads/main", "object": {"type": "commit", "sha": self.base_sha}}
        if method == "POST":
            self.prs = [pr(self.head)]
            if self.post_error:
                raise self.post_error
            return 201, self.prs[0]
        if "/git/ref/" in path:
            return ((404, {}) if self.head is None else
                    (200, {"ref": "refs/heads/feat/example", "object": {"type": "commit", "sha": self.head}}))
        if self.pages is not None:
            from urllib.parse import parse_qs, urlparse
            page = int(parse_qs(urlparse(path).query)["page"][0])
            return 200, self.pages.get(page, [])
        return 200, self.prs

    def git(self, *args, cwd=None):
        self.calls.append(("git", args, cwd))
        self.head = REQUEST["head_sha"]
        if self.prs:
            self.prs[0]["head"]["sha"] = self.head
        return subprocess.CompletedProcess(args, 0)


class Reconciliation(unittest.TestCase):
    def test_contradictory_merge_and_noninteger_repository_ids_hold(self):
        provider = Provider(prs=[pr()])
        request = publication.prepare_request(provider.api, REQUEST)
        provider.prs[0]["merged_at"] = "2026-09-10T00:00:00Z"
        with self.assertRaises(publication.PublicationHeld):
            publication.reconcile(provider.api, request)
        for side in ("head", "base"):
            provider.prs = [pr()]
            provider.prs[0][side]["repo"]["id"] = 123.0
            with self.assertRaises(publication.PublicationHeld):
                publication.reconcile(provider.api, request)

    def test_v2_request_captures_provider_identity_and_old_ref(self):
        provider = Provider("b" * 40)
        request = publication.prepare_request(provider.api, REQUEST)
        self.assertEqual(request["repository_id"], 123)
        self.assertEqual(request["base_sha"], "c" * 40)
        self.assertEqual(request["expected_remote_sha"], "b" * 40)
        self.assertEqual(request["version"], 2)

    def test_v2_repository_replacement_and_base_movement_hold(self):
        provider = Provider(prs=[pr()])
        request = publication.prepare_request(provider.api, REQUEST)
        for repository_id, base_sha in ((124, "c" * 40), (123, "d" * 40)):
            provider.repository_id, provider.base_sha = repository_id, base_sha
            with self.assertRaisesRegex(publication.PublicationHeld, "repository or base revision changed"):
                publication.reconcile(provider.api, request)

    def test_v2_pr_repository_id_and_base_revision_mismatch_hold(self):
        provider = Provider(prs=[pr()])
        request = publication.prepare_request(provider.api, REQUEST)
        for side in ("head", "base"):
            provider.prs = [pr()]
            provider.prs[0][side]["repo"]["id"] = 124
            with self.assertRaises(publication.PublicationHeld):
                publication.reconcile(provider.api, request)
        provider.prs = [pr()]
        provider.prs[0]["base"]["sha"] = "d" * 40
        with self.assertRaises(publication.PublicationHeld):
            publication.reconcile(provider.api, request)

    def test_v2_old_remote_is_durable_cas_constraint(self):
        provider = Provider("b" * 40)
        request = publication.prepare_request(provider.api, REQUEST)
        provider.head = "d" * 40
        with self.assertRaisesRegex(publication.PublicationHeld, "remote revision changed"):
            publication.publish(provider.api, provider.git, "remote", "mirror", request, "title", "body")
        self.assertTrue(all(call[0] == "GET" for call in provider.calls))

    def test_interrupted_complete_effect_reconciles_only_reads(self):
        provider = Provider(prs=[pr()])
        receipt = publication.reconcile(provider.api, REQUEST)
        self.assertEqual(receipt["publication_request"], REQUEST)
        self.assertEqual(receipt["pr_number"], 7)
        self.assertEqual(len(receipt["request_sha256"]), 64)
        self.assertTrue(receipt["observed_at"])
        self.assertTrue(all(call[0] == "GET" for call in provider.calls))
        self.assertIn("state=all", provider.calls[1][1])

    def test_confirmed_duplicate_is_reobserved(self):
        provider = Provider(prs=[pr()])
        previous = publication.reconcile(provider.api, REQUEST)
        provider.calls.clear()
        publication.reconcile(provider.api, REQUEST, previous)
        self.assertEqual(len(provider.calls), 2)

    def test_absent_partial_and_moved_effects_hold_without_writes(self):
        for head, prs in [(None, []), ("a" * 40, []), ("b" * 40, [pr("b" * 40)])]:
            with self.subTest(head=head, prs=prs):
                provider = Provider(head, prs)
                with self.assertRaises(publication.PublicationHeld):
                    publication.reconcile(provider.api, REQUEST)
                self.assertTrue(all(call[0] == "GET" for call in provider.calls))

    def test_confirmed_receipt_cannot_hide_changed_provider(self):
        provider = Provider(prs=[pr()])
        previous = publication.reconcile(provider.api, REQUEST)
        for head, prs in [("b" * 40, [pr("b" * 40)]), ("a" * 40, [pr(number=8)]), (None, [])]:
            with self.subTest(head=head, prs=prs):
                provider.head, provider.prs = head, prs
                with self.assertRaises(publication.PublicationHeld):
                    publication.reconcile(provider.api, REQUEST, previous)

    def test_legacy_unbound_or_changed_receipts_hold(self):
        provider = Provider(prs=[pr()])
        for previous in ({}, {"pr_url": "old"}, {"publication_request": {**REQUEST, "base": "other"}}):
            with self.assertRaises(publication.PublicationHeld):
                publication.reconcile(provider.api, REQUEST, previous)
        self.assertFalse(provider.calls)

    def test_wrong_destination_base_revision_closed_and_malformed_prs(self):
        variants = []
        for side in ("base", "head"):
            value = pr()
            value[side]["repo"]["full_name"] = "attacker/product"
            variants.append(value)
        for field, value in (("state", "closed"), ("html_url", "https://attacker.invalid"), ("number", True)):
            item = pr()
            item[field] = value
            variants.append(item)
        for side, field, value in (("base", "ref", "release"), ("head", "ref", "feat/other"), ("head", "sha", "b" * 40)):
            item = pr()
            item[side][field] = value
            variants.append(item)
        variants.extend([{}, None, "bad"])
        for value in variants:
            with self.subTest(pr=value), self.assertRaises(publication.PublicationHeld):
                publication.observe(Provider(prs=[value]).api, REQUEST)

    def test_multiple_prs_hold(self):
        with self.assertRaisesRegex(publication.PublicationHeld, "multiple"):
            publication.observe(Provider(prs=[pr(), pr(number=8)]).api, REQUEST)

    def test_pagination_reads_next_page_and_refuses_partial_results(self):
        provider = Provider()
        provider.pages = {1: [pr(number=n) for n in range(1, 101)], 2: [pr(number=101)]}
        with self.assertRaisesRegex(publication.PublicationHeld, "multiple"):
            publication.observe(provider.api, REQUEST)
        self.assertIn("page=2", provider.calls[-1][1])
        with self.assertRaisesRegex(publication.PublicationHeld, "pagination incomplete"):
            publication.observe(provider.api, REQUEST, max_pages=1)

    def test_unavailable_and_malformed_observations_hold(self):
        for result in [(403, {}), (500, {}), (200, []), (200, {"ref": "refs/heads/other", "object": {"sha": "a" * 40}})]:
            with self.subTest(result=result), self.assertRaises(publication.PublicationHeld):
                publication.observe(Mock(return_value=result), REQUEST)
        for result in [(503, []), (200, {}), (200, None)]:
            api = Mock(side_effect=[(404, {}), result])
            with self.assertRaises(publication.PublicationHeld):
                publication.observe(api, REQUEST)

    def test_invalid_destinations_and_refs_hold(self):
        for field, value in [("repo", "https://github.com.evil/owner/product"), ("repo", "https://github.com/../product"),
                             ("branch", "main"), ("branch", "feat/../other"), ("branch", "feat/x?bad"),
                             ("base", "-unsafe"), ("head_sha", "short")]:
            with self.subTest(field=field, value=value), self.assertRaises(publication.PublicationHeld):
                publication.destination({**REQUEST, field: value})


class FreshPublication(unittest.TestCase):
    def test_new_branch_and_pr_publish_once(self):
        provider = Provider(None)
        checks = []
        receipt = publication.publish(provider.api, provider.git, "remote", "mirror", REQUEST, "title", "body",
                                      check_current=lambda: checks.append(len(provider.calls)))
        self.assertEqual(receipt["pr_number"], 7)
        self.assertEqual(len(checks), 2)
        writes = [call for call in provider.calls if call[0] != "GET"]
        self.assertEqual([call[0] for call in writes], ["git", "POST"])
        self.assertIn("--force-with-lease=refs/heads/feat/example:", writes[0][1])
        self.assertIn("a" * 40 + ":refs/heads/feat/example", writes[0][1])

    def test_existing_pr_is_reused_without_comments_or_post(self):
        provider = Provider("b" * 40, [pr("b" * 40)])
        result = publication.publish(provider.api, provider.git, "remote", "mirror", REQUEST, "title", "body")
        self.assertTrue(result["pr_reused"])
        self.assertEqual(len([call for call in provider.calls if call[0] == "POST"]), 0)
        push = next(call for call in provider.calls if call[0] == "git")
        self.assertIn("--force-with-lease=refs/heads/feat/example:" + "b" * 40, push[1])

    def test_post_timeout_reconciles_without_retry(self):
        provider = Provider()
        provider.post_error = TimeoutError("connection lost after create")
        publication.publish(provider.api, provider.git, "remote", "mirror", REQUEST, "title", "body")
        self.assertEqual(len([call for call in provider.calls if call[0] == "POST"]), 1)

    def test_rejected_or_unknown_post_holds_without_retry(self):
        provider = Provider()
        def api(method, path, data=None):
            if method == "POST":
                provider.calls.append((method, path, data))
                return 422, {"message": "unknown"}
            return provider.api(method, path, data)
        with self.assertRaises(publication.PublicationHeld):
            publication.publish(api, provider.git, "remote", "mirror", REQUEST, "title", "body")
        self.assertEqual(len([call for call in provider.calls if call[0] == "POST"]), 1)

    def test_lost_fence_prevents_external_writes(self):
        for head in (None, "a" * 40):
            provider = Provider(head)
            def lost():
                raise RuntimeError("fence lost")
            with self.assertRaisesRegex(RuntimeError, "fence lost"):
                publication.publish(provider.api, provider.git, "remote", "mirror", REQUEST, "title", "body", check_current=lost)
            self.assertTrue(all(call[0] == "GET" for call in provider.calls))

    def test_closed_pr_holds_before_any_write(self):
        item = pr()
        item["state"] = "closed"
        provider = Provider(prs=[item])
        with self.assertRaises(publication.PublicationHeld):
            publication.publish(provider.api, provider.git, "remote", "mirror", REQUEST, "title", "body")
        self.assertTrue(all(call[0] == "GET" for call in provider.calls))


class SplitPublication(unittest.TestCase):
    class Crash(BaseException):
        pass

    def setUp(self):
        self.provider = Provider(None)
        self.request = publication.prepare_request(self.provider.api, REQUEST, 3)
        self.effects = {}
        self.live = True
        self.crash_before_confirmation = None
        self.crash_before_intent = None

    def check_current(self):
        if not self.live:
            raise leases.LeaseLost("stale owner")

    def begin(self, action):
        self.check_current()
        if self.crash_before_intent == action:
            raise self.Crash(action)
        if action in self.effects:
            effect = self.effects[action]
            return leases.Effect(False, effect.status, effect.external_ref, effect.result)
        effect = leases.Effect(True, "intended", None, publication.action_request(self.request, action))
        self.effects[action] = effect
        return effect

    def complete(self, action, effect, external_ref, result):
        self.check_current()
        if self.crash_before_confirmation == action:
            raise self.Crash(action)
        self.effects[action] = leases.Effect(False, "confirmed", external_ref, result)

    def publish(self):
        return publication.publish_split(self.provider.api, self.provider.git, "remote", "mirror", self.request,
                                         "title", "body", check_current=self.check_current,
                                         begin_effect=self.begin, complete_effect=self.complete)

    def writes(self, kind):
        return [call for call in self.provider.calls if call[0] == kind]

    def test_crash_after_branch_before_confirmation_resumes_only_missing_pr(self):
        self.crash_before_confirmation = "branch"
        with self.assertRaises(self.Crash):
            self.publish()
        self.assertEqual(self.effects["branch"].status, "intended")
        self.assertNotIn("pr", self.effects)
        self.assertEqual(len(self.writes("git")), 1)
        self.assertEqual(len(self.writes("POST")), 0)
        self.crash_before_confirmation = None
        result = self.publish()
        self.assertEqual(result["pr_number"], 7)
        self.assertEqual(len(self.writes("git")), 1)
        self.assertEqual(len(self.writes("POST")), 1)
        self.assertEqual([effect.status for effect in self.effects.values()], ["confirmed", "confirmed"])

    def test_crash_after_confirmed_branch_before_pr_intent_resumes_pr(self):
        self.crash_before_intent = "pr"
        with self.assertRaises(self.Crash):
            self.publish()
        self.assertEqual(self.effects["branch"].status, "confirmed")
        self.assertNotIn("pr", self.effects)
        self.crash_before_intent = None
        self.publish()
        self.assertEqual(len(self.writes("git")), 1)
        self.assertEqual(len(self.writes("POST")), 1)

    def test_crash_after_pr_post_reobserves_without_duplicate_post(self):
        self.crash_before_confirmation = "pr"
        with self.assertRaises(self.Crash):
            self.publish()
        self.assertEqual(self.effects["pr"].status, "intended")
        self.crash_before_confirmation = None
        self.publish()
        self.publish()
        self.assertEqual(len(self.writes("git")), 1)
        self.assertEqual(len(self.writes("POST")), 1)

    def test_preexisting_uncertain_pr_with_no_provider_result_never_replays(self):
        self.provider.head = REQUEST["head_sha"]
        for status in ("intended", "uncertain", "confirmed"):
            self.effects["pr"] = leases.Effect(False, status, None, publication.action_request(self.request, "pr"))
            with self.assertRaisesRegex(publication.PublicationHeld, "refusing POST replay"):
                self.publish()
        self.assertFalse(self.writes("POST"))

    def test_preexisting_branch_without_desired_result_never_replays(self):
        for status in ("intended", "uncertain", "confirmed"):
            self.effects["branch"] = leases.Effect(False, status, None, publication.action_request(self.request, "branch"))
            with self.assertRaisesRegex(publication.PublicationHeld, "refusing push replay"):
                self.publish()
        self.assertFalse(self.writes("git"))
        self.assertNotIn("pr", self.effects)

    def test_stale_owner_cannot_create_missing_pr_intent(self):
        self.crash_before_intent = "pr"
        with self.assertRaises(self.Crash):
            self.publish()
        self.crash_before_intent = None
        self.live = False
        with self.assertRaises(leases.LeaseLost):
            self.publish()
        self.assertNotIn("pr", self.effects)
        self.assertFalse(self.writes("POST"))

    def test_newer_owner_winning_pr_intent_race_prevents_post(self):
        original_begin = self.begin
        def competing_begin(action):
            if action == "pr":
                self.effects[action] = leases.Effect(False, "intended", None, publication.action_request(self.request, action))
            return original_begin(action)
        self.begin = competing_begin
        with self.assertRaisesRegex(publication.PublicationHeld, "refusing POST replay"):
            self.publish()
        self.assertFalse(self.writes("POST"))

    def test_legacy_request_cannot_enter_split_protocol(self):
        self.request["version"] = 2
        with self.assertRaisesRegex(publication.PublicationHeld, "bound host effect callbacks"):
            self.publish()
        self.assertFalse(self.effects)
        self.assertFalse(self.writes("git"))


class ActualLocalGitCAS(unittest.TestCase):
    def test_compare_and_swap_refuses_concurrent_update_and_creation(self):
        with tempfile.TemporaryDirectory(prefix="lantern-publication-cas-") as temp:
            root = Path(temp)
            seed, remote = root / "seed", root / "remote.git"
            seed.mkdir()
            def git(*args, cwd=seed):
                return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
            def checked(*args):
                result = git(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout.strip()
            checked("init", "-q", "-b", "main")
            checked("config", "user.name", "publication-test")
            checked("config", "user.email", "publication@example.invalid")
            heads = []
            for index in range(3):
                (seed / "file.txt").write_text(str(index))
                checked("add", ".")
                checked("commit", "-qm", f"revision {index}")
                heads.append(checked("rev-parse", "HEAD"))
            checked("init", "-q", "--bare", str(remote))
            publication.push_cas(git, str(remote), "feat/example", heads[0], None, seed)
            publication.push_cas(git, str(remote), "feat/example", heads[1], heads[0], seed)
            for expected in (None, heads[0]):
                with self.assertRaises(publication.PublicationHeld):
                    publication.push_cas(git, str(remote), "feat/example", heads[2], expected, seed)
            self.assertEqual(checked("--git-dir", str(remote), "rev-parse", "refs/heads/feat/example"), heads[1])
            publication.push_cas(git, str(remote), "feat/example", heads[2], heads[1], seed)
            self.assertEqual(checked("--git-dir", str(remote), "rev-parse", "refs/heads/feat/example"), heads[2])


if __name__ == "__main__":
    unittest.main()
