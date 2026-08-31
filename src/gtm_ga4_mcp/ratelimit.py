"""Rate limiting + retry for Google API calls.

The GTM API's default quota is ~15 requests/minute per Cloud project, which an
agent will blow through instantly without pacing. All GTM calls go through a
shared token-interval limiter plus retry-with-backoff on 429/5xx.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from .errors import to_tool_error

# 15 requests/minute => one request every 4 seconds.
GTM_MIN_INTERVAL_SECONDS = 4.0
MAX_RETRIES = 4


class RateLimiter:
    """Enforce a minimum interval between calls. Thread-safe (tools run in worker threads)."""

    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_at = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            wait = self._next_at - now
            if wait > 0:
                self._sleep(wait)
                now = self._next_at
            self._next_at = now + self._min_interval


_gtm_limiter = RateLimiter(GTM_MIN_INTERVAL_SECONDS)


def _retry_after_seconds(exc) -> float | None:
    value = exc.resp.get("retry-after")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def execute(
    request,
    *,
    limiter: RateLimiter | None = None,
    retries: int = MAX_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
):
    """Execute a googleapiclient request with pacing and backoff on 429/5xx."""
    from googleapiclient.errors import HttpError

    for attempt in range(retries + 1):
        if limiter is not None:
            limiter.acquire()
        try:
            return request.execute()
        except HttpError as exc:
            status = int(exc.resp.status)
            if status in (429, 500, 503) and attempt < retries:
                delay = _retry_after_seconds(exc) or float(2**attempt)
                sleep(delay)
                continue
            raise to_tool_error(exc) from exc
        except Exception as exc:  # noqa: BLE001 - normalize to actionable ToolError
            raise to_tool_error(exc) from exc
    raise AssertionError("unreachable")


def execute_gtm(request, **kwargs):
    """Execute a GTM request through the shared GTM limiter."""
    return execute(request, limiter=_gtm_limiter, **kwargs)
