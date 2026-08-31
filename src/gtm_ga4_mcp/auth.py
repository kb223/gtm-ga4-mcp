"""Google API clients via Application Default Credentials, scoped by safety tier.

Clients are built lazily on first use so the server starts (and `tools/list`
works, e.g. in CI or the MCP Inspector) without any Google credentials.

Thread safety: googleapiclient's httplib2 transport is NOT thread-safe, and
MCPServer runs sync tools in a worker threadpool — two concurrent tool calls
sharing one client corrupt the TLS connection (SSL RECORD_LAYER_FAILURE
observed in production). Each worker thread therefore gets its own service
cache via threading.local.
"""

from __future__ import annotations

import threading

from mcp.server.mcpserver.exceptions import ToolError

_lock = threading.Lock()
_scopes: tuple[str, ...] = ()
_generation = 0
_local = threading.local()


def configure(scopes: tuple[str, ...]) -> None:
    """Set the OAuth scopes for this process and invalidate every thread's cache."""
    global _scopes, _generation
    with _lock:
        _scopes = scopes
        _generation += 1


def _default_credentials(scopes: list[str]):
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError

    try:
        credentials, _project = google.auth.default(scopes=scopes)
        return credentials
    except DefaultCredentialsError as exc:
        scope_list = ",".join(scopes)
        raise ToolError(
            "No Google credentials found (Application Default Credentials). "
            "Run: gcloud auth application-default login "
            f"--scopes={scope_list},https://www.googleapis.com/auth/cloud-platform "
            "with an account that can access your GTM/GA4 accounts, then restart the server."
        ) from exc


def _build(api: str, version: str, credentials):
    from googleapiclient.discovery import build

    return build(api, version, credentials=credentials, cache_discovery=False)


def get_service(api: str, version: str):
    """Return this thread's cached googleapiclient service, building on first use."""
    with _lock:
        scopes, generation = _scopes, _generation

    if getattr(_local, "generation", None) != generation:
        _local.services = {}
        _local.generation = generation

    key = (api, version)
    if key not in _local.services:
        _local.services[key] = _build(api, version, _default_credentials(list(scopes)))
    return _local.services[key]
