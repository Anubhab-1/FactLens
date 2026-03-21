from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import secrets
import threading
import time


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        now = time.monotonic()

        with self._lock:
            bucket = self._requests[key]
            while bucket and now - bucket[0] >= window_seconds:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                return RateLimitDecision(
                    allowed=False,
                    limit=limit,
                    remaining=0,
                    retry_after=retry_after,
                )

            bucket.append(now)
            return RateLimitDecision(
                allowed=True,
                limit=limit,
                remaining=max(limit - len(bucket), 0),
                retry_after=0,
            )


def create_session_id() -> str:
    return secrets.token_urlsafe(18)


def get_client_identifier(request, session_id: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{client_host}:{session_id}"


def get_rate_limit_for_request(request, settings) -> int | None:
    path = request.url.path

    if request.method == "OPTIONS" or path == "/health":
        return None
    if path == "/analyze":
        return settings.rate_limit_analyze_requests
    if request.method in {"POST", "PATCH", "DELETE"}:
        return settings.rate_limit_write_requests
    return settings.rate_limit_read_requests
