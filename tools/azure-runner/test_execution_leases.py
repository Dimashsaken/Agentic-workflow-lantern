"""Focused lease guard and request identity checks; live SQL proof is integration_leases.py."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import execution_leases as leases


class RequestIdentity(unittest.TestCase):
    def test_order_stable_but_values_distinct(self):
        self.assertEqual(leases.request_hash({'b': 2, 'a': 1}), leases.request_hash({'a': 1, 'b': 2}))
        self.assertNotEqual(leases.request_hash({'a': 1}), leases.request_hash({'a': 2}))

    def test_nonfinite_request_rejected(self):
        with self.assertRaises(ValueError):
            leases.request_hash({'a': float('nan')})

    def test_ttl_invalid_inputs(self):
        for value in (0, -1, float('nan'), float('inf'), True, '120'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                leases._ttl(value)


class Guard(unittest.IsolatedAsyncioTestCase):
    async def test_check_requires_transaction(self):
        class Connection:
            def is_in_transaction(self):
                return False
        with self.assertRaisesRegex(RuntimeError, 'transaction'):
            await leases.assert_current(Connection(), leases.Lease('run', 'owner', 1))

    async def test_heartbeat_loss_cancels_and_closes(self):
        conn = AsyncMock()
        renew = AsyncMock(side_effect=[None, leases.LeaseLost('lost')])
        with patch.object(leases, 'renew', renew):
            with self.assertRaises(leases.LeaseLost):
                async with leases.lease_guard(AsyncMock(return_value=conn), leases.Lease('r','o',1), ttl=1, interval=.001):
                    await asyncio.sleep(1)
        conn.close.assert_awaited_once()
        self.assertEqual(renew.await_count, 2)

    async def test_normal_exit_closes_and_joins(self):
        conn = AsyncMock()
        with patch.object(leases, 'renew', AsyncMock()) as renew:
            async with leases.lease_guard(AsyncMock(return_value=conn), leases.Lease('r','o',1)):
                renew.assert_awaited_once()
        conn.close.assert_awaited_once()

    async def test_initial_connection_failure_never_runs_body(self):
        with self.assertRaises(leases.LeaseLost):
            async with leases.lease_guard(AsyncMock(side_effect=OSError('offline')), leases.Lease('r','o',1)):
                self.fail('guard yielded without a connection')

    async def test_stop_is_idempotent_and_prevents_release_race(self):
        conn = AsyncMock()
        with patch.object(leases, 'renew', AsyncMock()) as renew:
            async with leases.lease_guard(AsyncMock(return_value=conn), leases.Lease('r','o',1), ttl=1, interval=.001) as guard:
                await guard.stop()
                await guard.stop()
                renew.side_effect = leases.LeaseLost('released')
                await asyncio.sleep(.01)
                renew.assert_awaited_once()
        conn.close.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
