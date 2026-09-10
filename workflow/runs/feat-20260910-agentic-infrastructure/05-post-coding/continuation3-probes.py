"""Independent review controls; injected GitHub/DB, no external writes."""
from pathlib import Path
from types import SimpleNamespace
import os
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/azure-runner"))
import github_publication as publication
import review
from test_github_publication import Provider, REQUEST


class ContinuationReview(unittest.TestCase):
    def test_leased_review_never_sends_unledgered_provider_post(self):
        api = Mock(return_value=(201, {"id": 17, "html_url": "https://github.com/owner/product/pull/7#review-17"}))
        deps = SimpleNamespace(gh_api=api, public_url="")
        with patch.dict(os.environ, {"LANTERN_EXECUTION_LEASES": "1"}):
            result = review._post_review_for(
                {"pr_url": "https://github.com/owner/product/pull/7"},
                {"round": 1, "verdict": "approve", "findings": [], "must_fix": []}, "run", deps)
        api.assert_not_called()
        self.assertFalse(result["posted"])

    def test_lost_fence_between_push_and_pr_create_stops_second_effect(self):
        provider = Provider(None)
        request = publication.prepare_request(provider.api, REQUEST)
        checks = []
        def current():
            checks.append(True)
            if len(checks) == 2:
                raise RuntimeError("lease lost after push")
        with self.assertRaisesRegex(RuntimeError, "lease lost after push"):
            publication.publish(provider.api, provider.git, "fixture", "fixture", request,
                                "title", "body", check_current=current)
        self.assertEqual(provider.head, REQUEST["head_sha"])
        self.assertEqual(len(checks), 2)
        self.assertEqual([call[0] for call in provider.calls if call[0] != "GET"], ["git"])
        with self.assertRaises(publication.PublicationHeld):
            publication.reconcile(provider.api, request)
        self.assertEqual([call[0] for call in provider.calls if call[0] != "GET"], ["git"])

    def test_legacy_review_still_posts_advisory_comment_once(self):
        api = Mock(return_value=(201, {"id": 17, "html_url": "https://github.com/owner/product/pull/7#review-17"}))
        deps = SimpleNamespace(gh_api=api, public_url="")
        with patch.dict(os.environ, {"LANTERN_EXECUTION_LEASES": "0"}):
            result = review._post_review_for(
                {"pr_url": "https://github.com/owner/product/pull/7"},
                {"round": 1, "verdict": "approve", "findings": [], "must_fix": []}, "run", deps)
        self.assertTrue(result["posted"])
        api.assert_called_once()
        self.assertEqual(api.call_args.args[2]["event"], "COMMENT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
