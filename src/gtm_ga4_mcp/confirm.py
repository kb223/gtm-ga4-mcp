"""Confirmation handles for destructive operations (MRTR pattern, MCP spec 2026-07-28).

A destructive tool called WITHOUT a token does nothing except mint a one-time
token bound to that exact operation (tool + arguments) and return a
human-readable summary. The operation only executes when the tool is called
again with the token. Because the token is fingerprinted to the arguments,
a confirmation for "delete tag X" can never authorize "delete tag Y".

Tokens are single-use, expire after 10 minutes, and live in process memory —
appropriate for a local stdio server (one process per client session). The
protocol itself stays stateless; this is application state, like a database.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from collections.abc import Callable
from typing import Any

TTL_SECONDS = 600.0


def _fingerprint(tool_name: str, args: dict[str, Any]) -> str:
    canonical = json.dumps({"tool": tool_name, "args": args}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class ConfirmationStore:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[str, float]] = {}  # token -> (fingerprint, expires_at)

    def pending(self, tool_name: str, args: dict[str, Any], summary: str) -> dict[str, Any]:
        """Mint a token for this exact operation and describe what confirming will do."""
        token = secrets.token_urlsafe(9)
        with self._lock:
            self._prune()
            self._pending[token] = (_fingerprint(tool_name, args), self._clock() + TTL_SECONDS)
        return {
            "status": "confirmation_required",
            "summary": summary,
            "confirm_token": token,
            "expires_in_seconds": int(TTL_SECONDS),
            "instruction": (
                "Nothing was changed. Show the summary to the user; if they approve, call this "
                "tool again with identical arguments plus this confirm_token to execute."
            ),
        }

    def redeem(self, tool_name: str, args: dict[str, Any], token: str) -> bool:
        """Consume the token. True only for an unexpired token minted for these exact args."""
        with self._lock:
            self._prune()
            entry = self._pending.pop(token, None)
        return entry is not None and entry[0] == _fingerprint(tool_name, args)

    def _prune(self) -> None:
        now = self._clock()
        expired = [token for token, (_, expires) in self._pending.items() if expires <= now]
        for token in expired:
            del self._pending[token]


store = ConfirmationStore()
