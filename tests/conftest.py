import pytest

from gtm_ga4_mcp import auth, confirm, ratelimit


@pytest.fixture(autouse=True)
def fast_gtm_limiter(monkeypatch):
    """Zero out the shared GTM rate limiter so tests don't sleep 4s per call."""
    monkeypatch.setattr(ratelimit, "_gtm_limiter", ratelimit.RateLimiter(0.0))

# Attribute names that are API methods (return a request); everything else is
# a sub-resource accessor (accounts(), containers(), properties(), ...).
_LEAF_METHODS = {
    "list",
    "get",
    "create",
    "update",
    "delete",
    "publish",
    "create_version",
    "patch",
    "archive",
    "getMetadata",
    "runReport",
    "runRealtimeReport",
}


class FakeRequest:
    def __init__(self, service, call, result):
        self._service = service
        self._call = call
        self._result = result

    def execute(self):
        self._service.calls.append(self._call)
        return self._result


class FakeResource:
    def __init__(self, service, prefix):
        self._service = service
        self._prefix = prefix

    def __getattr__(self, name):
        dotted = f"{self._prefix}.{name}" if self._prefix else name

        def invoke(**kwargs):
            if name in _LEAF_METHODS:
                return FakeRequest(
                    self._service, (dotted, kwargs), self._service.responses.get(dotted, {})
                )
            return FakeResource(self._service, dotted)

        return invoke


class FakeService(FakeResource):
    """Stand-in for a googleapiclient discovery service. Configure `responses`
    by dotted method path (e.g. 'accounts.containers.workspaces.tags.list');
    every executed call is recorded in `calls` as (dotted_path, kwargs)."""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}
        super().__init__(self, "")


@pytest.fixture
def fake_service(monkeypatch):
    service = FakeService()
    monkeypatch.setattr(auth, "get_service", lambda api, version: service)
    return service


@pytest.fixture
def no_service(monkeypatch):
    """Fail the test if any code path builds a Google client (dry-run tests)."""

    def explode(api, version):
        raise AssertionError(f"unexpected Google client build: {api} {version}")

    monkeypatch.setattr(auth, "get_service", explode)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def confirm_clock(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(confirm, "store", confirm.ConfirmationStore(clock=clock))
    return clock
