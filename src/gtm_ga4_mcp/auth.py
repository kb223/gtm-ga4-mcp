"""Google API clients via Application Default Credentials, scoped by safety tier.

Clients are built lazily on first use so the server starts (and `tools/list`
works, e.g. in CI or the MCP Inspector) without any Google credentials.
"""

from __future__ import annotations

import threading

from mcp.server.mcpserver.exceptions import ToolError

_lock = threading.Lock()
_services: dict[tuple[str, str], object] = {}
_scopes: tuple[str, ...] = ()


def configure(scopes: tuple[str, ...]) -> None:
    """Set the OAuth scopes for this process and drop any cached clients."""
    global _scopes
    with _lock:
        _scopes = scopes
        _services.clear()


def get_service(api: str, version: str):
    """Return a cached googleapiclient service, building it on first use."""
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError
    from googleapiclient.discovery import build

    key = (api, version)
    with _lock:
        if key in _services:
            return _services[key]
        try:
            credentials, _project = google.auth.default(scopes=list(_scopes))
        except DefaultCredentialsError as exc:
            scope_list = ",".join(_scopes)
            raise ToolError(
                "No Google credentials found (Application Default Credentials). "
                "Run: gcloud auth application-default login "
                f"--scopes={scope_list},https://www.googleapis.com/auth/cloud-platform "
                "with an account that can access your GTM/GA4 accounts, then restart the server."
            ) from exc
        service = build(api, version, credentials=credentials, cache_discovery=False)
        _services[key] = service
        return service
