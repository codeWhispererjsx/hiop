from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException, status


class FailedLoginLimiter:
    """Small single-process limiter for failed authentication attempts."""

    def __init__(self, limit: int = 10, window_seconds: int = 300):
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, client: str) -> None:
        now = monotonic()
        with self._lock:
            attempts = self._prune(client, now)
            if len(attempts) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (now - attempts[0])))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many failed sign-in attempts. Try again later.",
                    headers={"Retry-After": str(retry_after)},
                )

    def failure(self, client: str) -> None:
        now = monotonic()
        with self._lock:
            self._prune(client, now).append(now)

    def success(self, client: str) -> None:
        with self._lock:
            self._attempts.pop(client, None)

    def _prune(self, client: str, now: float) -> deque[float]:
        attempts = self._attempts[client]
        cutoff = now - self.window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if not attempts:
            self._attempts.pop(client, None)
            attempts = self._attempts[client]
        return attempts


login_limiter = FailedLoginLimiter()
