"""Optional cross-process Dhan admission using atomic rolling windows."""

import hashlib
import time
import uuid
from typing import Any

_RESERVE = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local policy = cjson.decode(ARGV[1])
local retry = 0
for i, windows in ipairs(policy) do
    local maximum = windows[#windows][1]
    redis.call('ZREMRANGEBYSCORE', KEYS[i], '-inf', now - maximum)
    for _, window in ipairs(windows) do
        local cutoff = now - window[1]
        local count = redis.call('ZCOUNT', KEYS[i], '(' .. cutoff, '+inf')
        if count >= window[2] then
            local oldest = redis.call('ZRANGEBYSCORE', KEYS[i], '(' .. cutoff,
                                      '+inf', 'WITHSCORES', 'LIMIT', count - window[2], 1)
            retry = math.max(retry, tonumber(oldest[2]) + window[1] - now)
        end
    end
end
if retry > 0 then return retry end
for i, windows in ipairs(policy) do
    redis.call('ZADD', KEYS[i], now, ARGV[2])
    redis.call('PEXPIRE', KEYS[i], windows[#windows][1] + 60000)
end
return 0
"""


class RedisRateLimiter:
    def __init__(self, client: Any, *, wait_seconds: float = 30) -> None:
        self.client = client
        self.script = client.register_script(_RESERVE)
        self.wait_seconds = wait_seconds

    @classmethod
    def from_url(cls, url: str) -> "RedisRateLimiter":
        from redis import Redis
        return cls(Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2,
                                 max_connections=32, decode_responses=True))

    def acquire(self, client_id: str, categories: dict[str, list[tuple[int, int]]]) -> None:
        import json
        identity = hashlib.sha256(client_id.encode()).hexdigest()[:24]
        keys = [f"trader:dhan:{{{identity}}}:{category}" for category in categories]
        policies = []
        for windows in categories.values():
            if not windows or any(window < 1 or limit < 1 for window, limit in windows):
                raise ValueError("Rate windows and limits must be positive")
            policies.append(sorted(windows))
        if not keys:
            raise ValueError("At least one rate category is required")
        deadline = time.monotonic() + self.wait_seconds
        payload = json.dumps(policies, separators=(",", ":"))
        while True:
            retry_ms = int(self.script(keys=keys, args=[payload, uuid.uuid4().hex]))
            if retry_ms == 0:
                return
            remaining = deadline - time.monotonic()
            if retry_ms / 1000 > remaining:
                raise TimeoutError(f"Dhan request budget unavailable for {retry_ms / 1000:.3f}s")
            time.sleep(retry_ms / 1000)
