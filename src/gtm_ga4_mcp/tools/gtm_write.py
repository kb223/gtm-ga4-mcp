"""GTM write-tier tools: create and update (dry-run by default).

Available only with --allow-write. Every mutation defaults to dry_run=True,
which echoes the exact request without sending it — the agent shows the user
what would happen, then re-calls with dry_run=False to execute.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .. import auth
from ..config import Tier
from ..ratelimit import execute_gtm
from ..registry import ToolSpec, write_tool
from .gtm import _ENTITIES, _GET_CHAINS, GTM_API, GtmEntityType, _segments

# Entities that may be created/updated through the write tier. Accounts and
# containers are deliberately excluded (rare, high blast radius); versions are
# created via gtm_publish; user permissions via gtm_permissions (destructive).
_WRITABLE = {
    GtmEntityType.WORKSPACES,
    GtmEntityType.ENVIRONMENTS,
    GtmEntityType.TAGS,
    GtmEntityType.TRIGGERS,
    GtmEntityType.VARIABLES,
    GtmEntityType.FOLDERS,
    GtmEntityType.TEMPLATES,
    GtmEntityType.CLIENTS,
    GtmEntityType.TRANSFORMATIONS,
    GtmEntityType.ZONES,
}


def _resource(chain: tuple[str, ...]):
    resource = auth.get_service(*GTM_API)
    for attribute in chain:
        resource = getattr(resource, attribute)()
    return resource


def _require_writable(entity_type: GtmEntityType) -> None:
    if entity_type not in _WRITABLE:
        writable = ", ".join(sorted(entity.value for entity in _WRITABLE))
        raise ToolError(
            f"'{entity_type.value}' cannot be written through this tool. "
            f"Writable entity types: {writable}."
        )


def gtm_create(
    entity_type: Annotated[
        GtmEntityType,
        Field(description="Entity to create: tags, triggers, variables, workspaces, ..."),
    ],
    parent: Annotated[
        str,
        Field(
            description=(
                "Parent path: a container path for workspaces/environments, a workspace "
                "path for tags/triggers/variables/etc."
            ),
            min_length=1,
        ),
    ],
    body: Annotated[
        dict[str, Any],
        Field(
            description=(
                "Entity JSON per the GTM API, e.g. a tag: {'name': ..., 'type': 'gaawe', "
                "'parameter': [...], 'firingTriggerId': [...]}. Read a similar existing "
                "entity with gtm_get to see the expected shape."
            )
        ),
    ],
    dry_run: Annotated[
        bool,
        Field(description="True (default) echoes the request without sending it."),
    ] = True,
) -> dict[str, Any]:
    """Create a GTM entity in a workspace (or a new workspace/environment in a container).

    Defaults to dry-run: nothing is sent until called with dry_run=False.
    Changes land in the workspace only — nothing goes live without gtm_publish.
    """
    _require_writable(entity_type)
    entity = _ENTITIES[entity_type]
    if len(_segments(parent)) != entity.parent_segments:
        raise ToolError(
            f"gtm_create({entity_type.value}) needs parent matching "
            f"'{entity.parent_pattern}', got '{parent}'."
        )
    if dry_run:
        return {
            "dry_run": True,
            "would_call": f"tagmanager.{'.'.join(entity.chain)}.create",
            "parent": parent,
            "body": body,
            "note": "Nothing was sent. Re-call with dry_run=false to create this entity.",
        }
    created = execute_gtm(_resource(entity.chain).create(parent=parent, body=body))
    return {"created": created}


def gtm_update(
    path: Annotated[
        str,
        Field(
            description="Full path of the entity to update, from gtm_list/gtm_get.",
            min_length=1,
        ),
    ],
    body: Annotated[
        dict[str, Any],
        Field(
            description=(
                "COMPLETE entity JSON (the GTM API replaces the entity, not merges). "
                "Fetch with gtm_get, modify, and send the whole object back."
            )
        ),
    ],
    fingerprint: Annotated[
        str | None,
        Field(
            description=(
                "Optional optimistic-lock fingerprint from gtm_get; the update fails if "
                "someone changed the entity since."
            )
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="True (default) echoes the request without sending it."),
    ] = True,
) -> dict[str, Any]:
    """Update (replace) a GTM entity by path. Defaults to dry-run.

    GTM updates are full replacements — always start from gtm_get output.
    """
    segments = _segments(path)
    if len(segments) < 2 or len(segments) % 2 != 0:
        raise ToolError(f"'{path}' is not a valid GTM entity path.")
    collection = segments[-2]
    try:
        entity_type = GtmEntityType(collection)
    except ValueError:
        entity_type = None
    if entity_type is None or entity_type not in _WRITABLE:
        writable = ", ".join(sorted(entity.value for entity in _WRITABLE))
        raise ToolError(
            f"'{collection}' cannot be updated through this tool. Updatable: {writable}."
        )
    if dry_run:
        return {
            "dry_run": True,
            "would_call": f"tagmanager.{collection}.update",
            "path": path,
            "body": body,
            "note": "Nothing was sent. Re-call with dry_run=false to apply this update.",
        }
    kwargs: dict[str, Any] = {"path": "/".join(segments), "body": body}
    if fingerprint:
        kwargs["fingerprint"] = fingerprint
    updated = execute_gtm(_resource(_GET_CHAINS[collection]).update(**kwargs))
    return {"updated": updated}


SPECS = [
    ToolSpec(gtm_create, "gtm_create", Tier.WRITE, write_tool("Create GTM Entity")),
    ToolSpec(gtm_update, "gtm_update", Tier.WRITE, write_tool("Update GTM Entity")),
]
