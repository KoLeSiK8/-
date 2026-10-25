

from collections import deque
from threading import Lock
from time import monotonic

MAX_FAILURES = 5
WINDOW_SECONDS = 300


class LoginThrottle:
    def __init__(self, max_failures: int = MAX_FAILURES, window: float = WINDOW_SECONDS) -> None:
        self.max_failures = max_failures
        self.window = window
        self._failures: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        attempts = self._failures.setdefault(key, deque())
        while attempts and now - attempts[0] > self.window:
            attempts.popleft()
        return attempts

    def retry_after(self, key: str) -> int:

        now = monotonic()
        with self._lock:
            attempts = self._recent(key, now)
            if len(attempts) < self.max_failures:
                return 0
            return max(1, int(self.window - (now - attempts[0])) + 1)

    def failed(self, key: str) -> None:
        with self._lock:
            self._recent(key, monotonic()).append(monotonic())

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
