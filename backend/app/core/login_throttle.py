from __future__ import annotations

import threading
import time

# Per-account brute-force protection, complementing the per-IP slowapi limit
# on /auth/login (an attacker rotating IPs against one account is not stopped
# by an IP-keyed limit alone). In-memory like the rate limiter: acceptable for
# the current single-instance deployment, and it fails open on restart rather
# than locking real users out.
MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60

_lock = threading.Lock()
_failures: dict[str, list[float]] = {}


def _key(email: str) -> str:
    return email.strip().lower()


def _recent(key: str, now: float) -> list[float]:
    recent = [t for t in _failures.get(key, []) if now - t < WINDOW_SECONDS]
    if recent:
        _failures[key] = recent
    else:
        _failures.pop(key, None)
    return recent


def is_locked(email: str) -> bool:
    with _lock:
        return len(_recent(_key(email), time.monotonic())) >= MAX_FAILURES


def record_failure(email: str) -> None:
    with _lock:
        key = _key(email)
        now = time.monotonic()
        recent = _recent(key, now)
        recent.append(now)
        _failures[key] = recent


def record_success(email: str) -> None:
    with _lock:
        _failures.pop(_key(email), None)


def reset() -> None:
    """Clear all state (used by tests)."""
    with _lock:
        _failures.clear()
