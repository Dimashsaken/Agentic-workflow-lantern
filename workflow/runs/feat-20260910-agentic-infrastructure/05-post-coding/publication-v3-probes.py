"""Independent production callback/ledger controls with in-memory DB and GitHub.

Real pipeline callbacks and execution_leases request checks run; SQL storage,
ownership assertions and provider effects are explicitly injected, not live proof.
"""
import asyncio
from contextlib import asynccontextmanager, ExitStack
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools/azure-runner"))
import execution_leases as leases
import execution_runtime as ownership
import github_publication as github
import pipeline
from test_github_publication import Provider, REQUEST


class Rows:
    def __init__(self):
        self.rows = {}
        self.lose_after_pr_intent = False

    async def fetchrow(self, sql, *args):
        key = args[0]
        if "INSERT INTO execution_effects" in sql:
            if key in self.rows:
                return None
            self.rows[key] = dict(operation_key=key, run_id=args[1], stage_execution_id=args[2],
                                  lease_fence=args[3], kind=args[4], request_sha256=args[5],
                                  status="intended", result=args[6], external_ref=None)
            if self.lose_after_pr_intent and key.endswith(":pr"):
                self.lose_after_pr_intent = False
                raise OSError("lost response after durable PR intent")
            return dict(self.rows[key])
        if "SELECT * FROM execution_effects" in sql:
            return dict(self.rows[key]) if key in self.rows else None
        if "UPDATE execution_effects" in sql:
            self.rows[key].update(status=args[1], external_ref=args[2], result=args[3])
            return dict(self.rows[key])
        raise AssertionError(sql)


class ProductionCallbacks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.provider = Provider(None)
        self.request = github.prepare_request(self.provider.api, REQUEST, 3)
        self.rows = Rows()
        self.live = True
        self.handoff = {"head_sha": REQUEST["head_sha"], "branch": REQUEST["branch"]}
        self.lease = leases.Lease("run", "owner", 1, 42, 3)
        self.key = "publish-v3:run:" + REQUEST["head_sha"]
        self.token = ownership.STAGE.set(ownership.Ownership(self.lease, AsyncMock()))

    async def asyncTearDown(self):
        ownership.STAGE.reset(self.token)

    @asynccontextmanager
    async def transaction(self, *args, **kwargs):
        if not self.live:
            raise leases.LeaseLost("injected stale ownership")
        yield

    async def run_publication(self):
        def publish(*args):
            return github.publish_split(self.provider.api, self.provider.git, "fixture", "fixture",
                                        self.request, "title", "body", check_current=args[6],
                                        begin_effect=args[7], complete_effect=args[8])
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"LANTERN_EXECUTION_LEASES": "1"}))
            stack.enter_context(patch.object(ownership, "mutation", self.transaction))
            stack.enter_context(patch.object(leases, "fenced_transaction", self.transaction))
            stack.enter_context(patch.object(pipeline, "product_target", AsyncMock(return_value=(REQUEST["repo"], REQUEST["base"]))))
            stack.enter_context(patch.object(pipeline, "product_work_branch", AsyncMock(return_value=REQUEST["work"])))
            stack.enter_context(patch.object(pipeline, "_read_handoff", side_effect=lambda *args: self.handoff))
            stack.enter_context(patch.object(pipeline, "_publish_branch", publish))
            return await pipeline._publish_coding_branch(self.rows, "run", self.request)

    def inject(self, action, *, kind=None, request=None):
        action_request = request or github.action_request(self.request, action)
        self.rows.rows[self.key + ":" + action] = dict(
            operation_key=self.key + ":" + action, run_id="run", stage_execution_id=42,
            lease_fence=1, kind=kind or "publish_" + action,
            request_sha256=leases.request_hash(action_request), status="intended",
            result=json.dumps(action_request), external_ref=None)

    def writes(self):
        return [call[0] for call in self.provider.calls if call[0] != "GET"]

    async def test_actual_callbacks_reject_wrong_kind_and_request_before_provider_effect(self):
        for action in ("branch", "pr"):
            for mismatch in ("kind", "hash"):
                with self.subTest(action=action, mismatch=mismatch):
                    self.rows.rows.clear()
                    self.provider.head = REQUEST["head_sha"] if action == "pr" else None
                    if mismatch == "kind":
                        self.inject(action, kind="different_effect")
                    else:
                        changed = github.action_request({**self.request, "base": "release"}, action)
                        self.inject(action, request=changed)
                    with self.assertRaises(leases.EffectConflict):
                        await self.run_publication()
                    self.assertEqual(self.writes(), [])

    async def test_durable_missing_pr_response_never_authorizes_post_on_retry(self):
        self.rows.lose_after_pr_intent = True
        with self.assertRaisesRegex(OSError, "durable PR intent"):
            await self.run_publication()
        self.assertEqual(self.writes(), ["git"])
        self.assertEqual(self.rows.rows[self.key + ":pr"]["status"], "intended")
        with self.assertRaisesRegex(github.PublicationHeld, "refusing POST replay"):
            await self.run_publication()
        self.assertEqual(self.writes(), ["git"])

    async def test_stale_owner_after_push_cannot_confirm_or_create_pr_intent(self):
        original_git = self.provider.git
        def push(*args, **kwargs):
            result = original_git(*args, **kwargs)
            self.live = False
            return result
        self.provider.git = push
        with self.assertRaises(leases.LeaseLost):
            await self.run_publication()
        self.assertEqual(self.writes(), ["git"])
        self.assertEqual(self.rows.rows[self.key + ":branch"]["status"], "intended")
        self.assertNotIn(self.key + ":pr", self.rows.rows)

    async def test_target_change_after_push_prevents_receipt_and_missing_action(self):
        original_git = self.provider.git
        def push(*args, **kwargs):
            result = original_git(*args, **kwargs)
            self.handoff = {**self.handoff, "head_sha": "b" * 40}
            return result
        self.provider.git = push
        with self.assertRaisesRegex(github.PublicationHeld, "target or handoff changed"):
            await self.run_publication()
        self.assertEqual(self.writes(), ["git"])
        self.assertEqual(self.rows.rows[self.key + ":branch"]["status"], "intended")
        self.assertNotIn(self.key + ":pr", self.rows.rows)

    async def test_production_callbacks_repair_missing_action_and_reobserve_duplicates(self):
        self.provider.head = REQUEST["head_sha"]
        self.inject("branch")
        result = await self.run_publication()
        self.assertEqual(result["pr_number"], 7)
        self.assertEqual(self.writes(), ["POST"])
        self.assertEqual({row["status"] for row in self.rows.rows.values()}, {"confirmed"})
        await self.run_publication()
        self.assertEqual(self.writes(), ["POST"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
