"""Safety-tier configuration.

Every tool belongs to a tier (READ / WRITE / DESTRUCTIVE). Two enforcement
layers derive from the same config:

1. Tools above the configured tier are never registered, so they are invisible
   to the model — not merely erroring at call time.
2. The OAuth scopes requested from Google are the union of the enabled tiers'
   scopes, so a read-only process holds a token that cannot mutate anything
   even if the application code misbehaves.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum


class Tier(IntEnum):
    READ = 0
    WRITE = 1
    DESTRUCTIVE = 2


_TRUTHY = {"1", "true", "yes", "on"}

GTM_READ_SCOPE = "https://www.googleapis.com/auth/tagmanager.readonly"
GA4_READ_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
GTM_EDIT_SCOPE = "https://www.googleapis.com/auth/tagmanager.edit.containers"
GTM_VERSIONS_SCOPE = "https://www.googleapis.com/auth/tagmanager.edit.containerversions"
GA4_EDIT_SCOPE = "https://www.googleapis.com/auth/analytics.edit"
GTM_DELETE_SCOPE = "https://www.googleapis.com/auth/tagmanager.delete.containers"
GTM_PUBLISH_SCOPE = "https://www.googleapis.com/auth/tagmanager.publish"
GTM_MANAGE_USERS_SCOPE = "https://www.googleapis.com/auth/tagmanager.manage.users"

_SCOPES_BY_TIER: dict[Tier, tuple[str, ...]] = {
    Tier.READ: (GTM_READ_SCOPE, GA4_READ_SCOPE),
    Tier.WRITE: (GTM_EDIT_SCOPE, GTM_VERSIONS_SCOPE, GA4_EDIT_SCOPE),
    Tier.DESTRUCTIVE: (GTM_DELETE_SCOPE, GTM_PUBLISH_SCOPE, GTM_MANAGE_USERS_SCOPE),
}


@dataclass(frozen=True)
class ServerConfig:
    max_tier: Tier = Tier.READ
    denylist: frozenset[str] = frozenset()

    def allows(self, tool_name: str, tier: Tier) -> bool:
        return tier <= self.max_tier and tool_name not in self.denylist

    @property
    def scopes(self) -> tuple[str, ...]:
        scopes: list[str] = []
        for tier in Tier:
            if tier <= self.max_tier:
                scopes.extend(_SCOPES_BY_TIER[tier])
        return tuple(scopes)


def parse_config(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> ServerConfig:
    """Build config from CLI flags and environment. Flags win; either can enable a tier.

    --allow-destructive implies --allow-write.
    """
    if env is None:
        env = os.environ

    parser = argparse.ArgumentParser(
        prog="gtm-ga4-mcp",
        description="MCP server for Google Tag Manager + GA4 with tiered safety controls.",
    )
    parser.add_argument(
        "--allow-write",
        action="store_true",
        help="Enable write-tier tools (create/update). Default: read-only.",
    )
    parser.add_argument(
        "--allow-destructive",
        action="store_true",
        help="Enable destructive-tier tools (delete/publish/permissions). Implies --allow-write.",
    )
    parser.add_argument(
        "--deny",
        action="append",
        default=[],
        metavar="TOOL",
        help="Disable a specific tool by name (repeatable).",
    )
    args = parser.parse_args(argv)

    def env_flag(name: str) -> bool:
        return env.get(name, "").strip().lower() in _TRUTHY

    allow_write = args.allow_write or env_flag("GTM_GA4_MCP_ALLOW_WRITE")
    allow_destructive = args.allow_destructive or env_flag("GTM_GA4_MCP_ALLOW_DESTRUCTIVE")

    if allow_destructive:
        max_tier = Tier.DESTRUCTIVE
    elif allow_write:
        max_tier = Tier.WRITE
    else:
        max_tier = Tier.READ

    denylist = {t.strip() for t in env.get("GTM_GA4_MCP_DENY", "").split(",") if t.strip()}
    denylist.update(args.deny)

    return ServerConfig(max_tier=max_tier, denylist=frozenset(denylist))
