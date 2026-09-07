"""Run against a dedicated Redis container with TRADER_TEST_REDIS_URL set."""

from concurrent.futures import ProcessPoolExecutor
import hashlib
import multiprocessing
import os
import time
import unittest
import uuid

from pipeline.services.redis_rate_limit import RedisRateLimiter


def _reserve_in_process(arguments):
    url, account = arguments
    limiter = RedisRateLimiter.from_url(url)
    limiter.acquire(account, {"test": [(100, 3), (10000, 100)]})


@unittest.skipUnless(os.getenv("TRADER_TEST_REDIS_URL"), "requires isolated Redis")
class RedisRateLimitTests(unittest.TestCase):
    def setUp(self):
        from redis import Redis
        self.url = os.environ["TRADER_TEST_REDIS_URL"]
        self.client = Redis.from_url(self.url, decode_responses=True)
        self.account = "test-" + uuid.uuid4().hex
        self.prefix = "trader:dhan:{" + hashlib.sha256(self.account.encode()).hexdigest()[:24] + "}:"
        self.limiter = RedisRateLimiter(self.client, wait_seconds=0.05)

    def tearDown(self):
        keys = list(self.client.scan_iter(match=self.prefix + "*"))
        if keys:
            self.client.delete(*keys)
        self.client.close()

    def test_independent_processes_share_rolling_windows(self):
        with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
            list(pool.map(_reserve_in_process, [(self.url, self.account)] * 12))
        rows = self.client.zrange(self.prefix + "test", 0, -1, withscores=True)
        self.assertEqual(len(rows), 12)
        scores = [score for _, score in rows]
        for score in scores:
            self.assertLessEqual(sum(score - 100 < other <= score for other in scores), 3)

    def test_failed_compound_reservation_does_not_consume_data(self):
        self.limiter.acquire(self.account, {"options": [(1000, 1)]})
        with self.assertRaises(TimeoutError):
            self.limiter.acquire(self.account, {"data": [(1000, 4)], "options": [(1000, 1)]})
        self.assertEqual(self.client.zcard(self.prefix + "data"), 0)
        self.limiter.acquire(self.account, {"quotes": [(1000, 1)]})
        self.assertEqual(self.client.zcard(self.prefix + "quotes"), 1)

    def test_new_client_does_not_reset_budget_and_expiry_reopens_window(self):
        self.limiter.acquire(self.account, {"data": [(100, 1)]})
        second = RedisRateLimiter(self.client, wait_seconds=0)
        with self.assertRaises(TimeoutError):
            second.acquire(self.account, {"data": [(100, 1)]})
        time.sleep(0.11)
        second.acquire(self.account, {"data": [(100, 1)]})
        self.assertGreater(self.client.pttl(self.prefix + "data"), 0)

    def test_long_window_blocks_even_when_short_window_is_available(self):
        self.limiter.acquire(self.account, {"orders": [(10, 1), (1000, 1)]})
        time.sleep(0.02)
        with self.assertRaises(TimeoutError):
            self.limiter.acquire(self.account, {"orders": [(10, 1), (1000, 1)]})

    def test_unavailable_redis_fails_closed(self):
        from redis import Redis
        from redis.exceptions import ConnectionError
        client = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.1,
                       socket_timeout=0.1, retry_on_error=[])
        with self.assertRaises(ConnectionError):
            RedisRateLimiter(client).acquire(self.account, {"data": [(1000, 1)]})
        client.close()
