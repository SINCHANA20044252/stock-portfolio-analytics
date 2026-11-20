"""Small in-memory sliding-window limiter. Per process: it resets on restart and is not shared between
workers. For several instances use Redis (see README). Good enough to blunt password guessing."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from . import config


def client_ip(request: Request) -> str:
    if config.TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class SlidingWindow:
    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = defaultdict(deque)

    def _trim(self, key: str, now: float) -> deque:
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        return len(self._trim(key, time.time())) >= self.limit

    def add(self, key: str) -> None:
        now = time.time()
        self._trim(key, now).append(now)

    def hit(self, key: str) -> bool:
        """Record an attempt; return False if over the limit."""
        now = time.time()
        q = self._trim(key, now)
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True

    def clear(self):
        self.hits.clear()


AUTH_IP = SlidingWindow(limit=10, window=60)            # any login/register attempt per IP
LOGIN_FAILS = SlidingWindow(limit=5, window=15 * 60)    # failed logins per email per 15 minutes
EXPENSIVE = SlidingWindow(limit=10, window=60)          # market refresh / AI questions per user


def limit_auth(request: Request):
    if not AUTH_IP.hit(client_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again in a minute.")


def limit_user(user_id: int, label: str):
    if not EXPENSIVE.hit(f"{label}:{user_id}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Please wait a minute.")


def reset_all():
    for w in (AUTH_IP, LOGIN_FAILS, EXPENSIVE):
        w.clear()
