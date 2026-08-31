"""Translate Google API errors into actionable MCP tool errors."""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError

_HINTS = {
    401: "Credentials are invalid or expired. Re-run: gcloud auth application-default login",
    403: (
        "Permission denied. Check that (a) the Tag Manager / Analytics APIs are enabled in "
        "your Google Cloud project, and (b) the authenticated account has access to this "
        "GTM account or GA4 property."
    ),
    404: "Not found. Check the path/ID — list the parent first to discover valid children.",
    429: (
        "Rate limit exceeded even after retries. The GTM API allows ~15 requests/minute "
        "per project by default; wait a minute before continuing."
    ),
}


def to_tool_error(exc: Exception) -> ToolError:
    from googleapiclient.errors import HttpError

    if isinstance(exc, HttpError):
        status = int(exc.resp.status)
        reason = exc.reason or ""
        hint = _HINTS.get(status, "")
        return ToolError(f"Google API error {status}: {reason} {hint}".strip())
    return ToolError(f"Unexpected error: {type(exc).__name__}: {exc}")
