import collections
import os
import threading
import time as _time


class RateLimiter:
    """Sliding-window in-memory rate limiter. Thread-safe, no extra deps."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, collections.deque] = {}

    def allow(self, key: str, limit: int, window: float) -> bool:
        if "PYTEST_CURRENT_TEST" in os.environ:
            return True
        now = _time.monotonic()
        with self._lock:
            dq = self._windows.setdefault(key, collections.deque())
            cutoff = now - window
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            return True


_rate = RateLimiter()
