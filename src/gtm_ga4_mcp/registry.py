"""Tool registry: every tool declares its safety tier and annotations here."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mcp.types import ToolAnnotations

from .config import Tier


@dataclass(frozen=True)
class ToolSpec:
    fn: Callable
    name: str
    tier: Tier
    annotations: ToolAnnotations


def read_only(title: str) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    )


def write_tool(title: str) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    )


def destructive_tool(title: str) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    )


def all_specs() -> list[ToolSpec]:
    """Collect every tool spec, sorted by name for deterministic tools/list ordering."""
    from .tools import (
        ga4_admin,
        ga4_data,
        ga4_destructive,
        ga4_write,
        gtm,
        gtm_destructive,
        gtm_write,
    )

    specs = [
        *gtm.SPECS,
        *gtm_write.SPECS,
        *gtm_destructive.SPECS,
        *ga4_admin.SPECS,
        *ga4_data.SPECS,
        *ga4_write.SPECS,
        *ga4_destructive.SPECS,
    ]
    names = [spec.name for spec in specs]
    if len(names) != len(set(names)):
        raise ValueError(f"Duplicate tool names in registry: {names}")
    return sorted(specs, key=lambda spec: spec.name)
