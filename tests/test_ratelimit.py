import httplib2
import pytest
from googleapiclient.errors import HttpError
from mcp.server.mcpserver.exceptions import ToolError

from gtm_ga4_mcp.ratelimit import RateLimiter, execute


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _http_error(status: int, retry_after: str | None = None) -> HttpError:
    headers = {"status": str(status)}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    return HttpError(httplib2.Response(headers), b"{}")


class FakeRequest:
    """request.execute() that fails `failures` times, then returns `result`."""

    def __init__(self, result, failures=0, error_status=429, retry_after=None):
        self.result = result
        self.remaining_failures = failures
        self.error_status = error_status
        self.retry_after = retry_after
        self.calls = 0

    def execute(self):
        self.calls += 1
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise _http_error(self.error_status, self.retry_after)
        return self.result


def test_limiter_spaces_out_calls():
    clock = FakeClock()
    limiter = RateLimiter(4.0, clock=clock, sleep=clock.sleep)
    limiter.acquire()  # first call is free
    limiter.acquire()
    limiter.acquire()
    assert clock.sleeps == [4.0, 4.0]


def test_execute_retries_transient_429_then_succeeds():
    clock = FakeClock()
    request = FakeRequest({"ok": True}, failures=2)
    assert execute(request, sleep=clock.sleep) == {"ok": True}
    assert request.calls == 3
    assert clock.sleeps == [1.0, 2.0]  # exponential backoff


def test_execute_honors_retry_after_header():
    clock = FakeClock()
    request = FakeRequest({"ok": True}, failures=1, retry_after="7")
    assert execute(request, sleep=clock.sleep) == {"ok": True}
    assert clock.sleeps == [7.0]


def test_execute_raises_actionable_error_when_retries_exhausted():
    clock = FakeClock()
    request = FakeRequest({"ok": True}, failures=99)
    with pytest.raises(ToolError, match="Rate limit"):
        execute(request, retries=2, sleep=clock.sleep)
    assert request.calls == 3


def test_execute_does_not_retry_permanent_errors():
    clock = FakeClock()
    request = FakeRequest({"ok": True}, failures=1, error_status=403)
    with pytest.raises(ToolError, match="403"):
        execute(request, sleep=clock.sleep)
    assert request.calls == 1
    assert clock.sleeps == []
