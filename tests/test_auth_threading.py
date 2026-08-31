import threading

from gtm_ga4_mcp import auth


def _install_fakes(monkeypatch):
    builds = []

    def fake_credentials(scopes):
        return object()

    def fake_build(api, version, credentials):
        service = object()
        builds.append((api, version, threading.get_ident(), service))
        return service

    monkeypatch.setattr(auth, "_default_credentials", fake_credentials)
    monkeypatch.setattr(auth, "_build", fake_build)
    return builds


def test_same_thread_reuses_cached_service(monkeypatch):
    builds = _install_fakes(monkeypatch)
    auth.configure(("scope-a",))
    first = auth.get_service("tagmanager", "v2")
    second = auth.get_service("tagmanager", "v2")
    assert first is second
    assert len(builds) == 1


def test_each_thread_gets_its_own_client(monkeypatch):
    builds = _install_fakes(monkeypatch)
    auth.configure(("scope-a",))
    main_service = auth.get_service("analyticsdata", "v1beta")

    from_thread = {}

    def worker():
        from_thread["service"] = auth.get_service("analyticsdata", "v1beta")

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert from_thread["service"] is not main_service  # httplib2 is not thread-safe
    assert len(builds) == 2


def test_configure_invalidates_thread_caches(monkeypatch):
    builds = _install_fakes(monkeypatch)
    auth.configure(("scope-a",))
    before = auth.get_service("tagmanager", "v2")
    auth.configure(("scope-a", "scope-b"))
    after = auth.get_service("tagmanager", "v2")
    assert before is not after
    assert len(builds) == 2
