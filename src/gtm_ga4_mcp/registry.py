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


def all_specs() -> list[ToolSpec]:
    """Collect every tool spec, sorted by name for deterministic tools/list ordering."""
    from .tools import ga4_admin, ga4_data, gtm

    specs = [*gtm.SPECS, *ga4_admin.SPECS, *ga4_data.SPECS]
    names = [spec.name for spec in specs]
    if len(names) != len(set(names)):
        raise ValueError(f"Duplicate tool names in registry: {names}")
    return sorted(specs, key=lambda spec: spec.name)
