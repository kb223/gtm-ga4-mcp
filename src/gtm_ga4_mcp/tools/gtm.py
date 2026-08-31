"""Google Tag Manager read tools.

Instead of one tool per endpoint (~40 for GTM alone), the surface is two
consolidated tools: `gtm_list` walks the hierarchy level by level returning
trimmed summaries, and `gtm_get` fetches one entity's full JSON by its path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from ..auth import get_service
from ..config import Tier
from ..ratelimit import execute_gtm
from ..registry import ToolSpec, read_only

GTM_API = ("tagmanager", "v2")

# Fields worth keeping in list summaries; everything else is retrievable via gtm_get.
_SUMMARY_KEYS = {"path", "name", "type", "publicId", "usageContext"}


class GtmEntityType(str, Enum):
    ACCOUNTS = "accounts"
    CONTAINERS = "containers"
    DESTINATIONS = "destinations"
    ENVIRONMENTS = "environments"
    VERSIONS = "versions"
    WORKSPACES = "workspaces"
    BUILT_IN_VARIABLES = "built_in_variables"
    CLIENTS = "clients"
    FOLDERS = "folders"
    TAGS = "tags"
    TEMPLATES = "templates"
    TRANSFORMATIONS = "transformations"
    TRIGGERS = "triggers"
    VARIABLES = "variables"
    ZONES = "zones"


@dataclass(frozen=True)
class _Entity:
    chain: tuple[str, ...]  # attribute chain on the discovery service
    response_key: str  # key holding the item list in the API response
    parent_segments: int  # number of path segments the parent must have
    parent_pattern: str  # human-readable hint for error messages


_ACCOUNT = "accounts/{account_id}"
_CONTAINER = _ACCOUNT + "/containers/{container_id}"
_WORKSPACE = _CONTAINER + "/workspaces/{workspace_id}"

_ENTITIES: dict[GtmEntityType, _Entity] = {
    GtmEntityType.ACCOUNTS: _Entity(("accounts",), "account", 0, "(no parent)"),
    GtmEntityType.CONTAINERS: _Entity(("accounts", "containers"), "container", 2, _ACCOUNT),
    GtmEntityType.DESTINATIONS: _Entity(
        ("accounts", "containers", "destinations"), "destination", 4, _CONTAINER
    ),
    GtmEntityType.ENVIRONMENTS: _Entity(
        ("accounts", "containers", "environments"), "environment", 4, _CONTAINER
    ),
    GtmEntityType.VERSIONS: _Entity(
        ("accounts", "containers", "version_headers"), "containerVersionHeader", 4, _CONTAINER
    ),
    GtmEntityType.WORKSPACES: _Entity(
        ("accounts", "containers", "workspaces"), "workspace", 4, _CONTAINER
    ),
    GtmEntityType.BUILT_IN_VARIABLES: _Entity(
        ("accounts", "containers", "workspaces", "built_in_variables"),
        "builtInVariable",
        6,
        _WORKSPACE,
    ),
    GtmEntityType.CLIENTS: _Entity(
        ("accounts", "containers", "workspaces", "clients"), "client", 6, _WORKSPACE
    ),
    GtmEntityType.FOLDERS: _Entity(
        ("accounts", "containers", "workspaces", "folders"), "folder", 6, _WORKSPACE
    ),
    GtmEntityType.TAGS: _Entity(
        ("accounts", "containers", "workspaces", "tags"), "tag", 6, _WORKSPACE
    ),
    GtmEntityType.TEMPLATES: _Entity(
        ("accounts", "containers", "workspaces", "templates"), "template", 6, _WORKSPACE
    ),
    GtmEntityType.TRANSFORMATIONS: _Entity(
        ("accounts", "containers", "workspaces", "transformations"),
        "transformation",
        6,
        _WORKSPACE,
    ),
    GtmEntityType.TRIGGERS: _Entity(
        ("accounts", "containers", "workspaces", "triggers"), "trigger", 6, _WORKSPACE
    ),
    GtmEntityType.VARIABLES: _Entity(
        ("accounts", "containers", "workspaces", "variables"), "variable", 6, _WORKSPACE
    ),
    GtmEntityType.ZONES: _Entity(
        ("accounts", "containers", "workspaces", "zones"), "zone", 6, _WORKSPACE
    ),
}

# gtm_get dispatch: second-to-last path segment -> resource attribute chain.
_GET_CHAINS: dict[str, tuple[str, ...]] = {
    "accounts": ("accounts",),
    "containers": ("accounts", "containers"),
    "destinations": ("accounts", "containers", "destinations"),
    "environments": ("accounts", "containers", "environments"),
    "versions": ("accounts", "containers", "versions"),
    "workspaces": ("accounts", "containers", "workspaces"),
    "built_in_variables": ("accounts", "containers", "workspaces", "built_in_variables"),
    "clients": ("accounts", "containers", "workspaces", "clients"),
    "folders": ("accounts", "containers", "workspaces", "folders"),
    "tags": ("accounts", "containers", "workspaces", "tags"),
    "templates": ("accounts", "containers", "workspaces", "templates"),
    "transformations": ("accounts", "containers", "workspaces", "transformations"),
    "triggers": ("accounts", "containers", "workspaces", "triggers"),
    "variables": ("accounts", "containers", "workspaces", "variables"),
    "zones": ("accounts", "containers", "workspaces", "zones"),
}


def _segments(path: str) -> list[str]:
    return [segment for segment in path.split("/") if segment]


def _summarize(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key in _SUMMARY_KEYS or key.endswith("Id")
    }


def _resource(chain: tuple[str, ...]):
    resource = get_service(*GTM_API)
    for attribute in chain:
        resource = getattr(resource, attribute)()
    return resource


def gtm_list(
    entity_type: Annotated[
        GtmEntityType,
        Field(
            description=(
                "Which GTM entity to list. Walk the hierarchy: accounts -> containers "
                "-> workspaces -> tags/triggers/variables/..."
            )
        ),
    ],
    parent: Annotated[
        str,
        Field(
            description=(
                "Parent path from a previous result, e.g. '' for accounts, "
                "'accounts/123' for containers, 'accounts/123/containers/456' for "
                "workspaces/versions/environments, 'accounts/123/containers/456/workspaces/7' "
                "for tags/triggers/variables."
            )
        ),
    ] = "",
    page_token: Annotated[
        str | None, Field(description="Pagination token from a previous response.")
    ] = None,
    full: Annotated[
        bool,
        Field(
            description=(
                "Return complete entity JSON instead of trimmed summaries. "
                "Prefer gtm_get for a single entity."
            )
        ),
    ] = False,
) -> dict[str, Any]:
    """List Google Tag Manager entities one hierarchy level at a time.

    Returns trimmed summaries (path, name, type, IDs) to keep context small;
    each item's `path` feeds gtm_get (full detail) or a deeper gtm_list call.
    """
    entity = _ENTITIES[entity_type]
    if len(_segments(parent)) != entity.parent_segments:
        raise ToolError(
            f"gtm_list({entity_type.value}) needs parent matching '{entity.parent_pattern}', "
            f"got '{parent}'. List the parent level first to discover valid paths."
        )

    kwargs: dict[str, Any] = {}
    if entity.parent_segments:
        kwargs["parent"] = parent
    if page_token:
        kwargs["pageToken"] = page_token

    response = execute_gtm(_resource(entity.chain).list(**kwargs)) or {}
    items = response.get(entity.response_key, [])
    return {
        "entity_type": entity_type.value,
        "count": len(items),
        "items": items if full else [_summarize(item) for item in items],
        "next_page_token": response.get("nextPageToken"),
    }


def gtm_get(
    path: Annotated[
        str,
        Field(
            description=(
                "Full GTM entity path from a gtm_list result, e.g. "
                "'accounts/123/containers/456/workspaces/7/tags/8' or "
                "'accounts/123/containers/456/versions/42'."
            ),
            min_length=1,
        ),
    ],
) -> dict[str, Any]:
    """Fetch one GTM entity's complete JSON by its path (tag, trigger, variable, version, ...).

    Note: fetching a version returns the entire published container (large).
    """
    segments = _segments(path)
    if len(segments) < 2 or len(segments) % 2 != 0:
        raise ToolError(
            f"'{path}' is not a valid GTM entity path. Expected alternating "
            "collection/id segments, e.g. 'accounts/123/containers/456'."
        )
    collection = segments[-2]
    chain = _GET_CHAINS.get(collection)
    if chain is None:
        raise ToolError(
            f"Unknown GTM collection '{collection}'. "
            f"Valid collections: {', '.join(sorted(_GET_CHAINS))}."
        )
    return execute_gtm(_resource(chain).get(path="/".join(segments)))


SPECS = [
    ToolSpec(gtm_list, "gtm_list", Tier.READ, read_only("List GTM Entities")),
    ToolSpec(gtm_get, "gtm_get", Tier.READ, read_only("Get GTM Entity")),
]
