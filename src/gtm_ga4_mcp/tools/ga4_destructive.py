"""GA4 destructive-tier tools: delete / archive (two-phase confirmation)."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .. import auth, confirm
from ..config import Tier
from ..ratelimit import execute
from ..registry import ToolSpec, destructive_tool
from .ga4_admin import ADMIN_API

# collection segment in the resource name -> (service attr, verb).
# GA4 archives custom definitions (the API has no true delete for them) and
# deletes key events / data streams. Properties are excluded by design.
_OPERATIONS: dict[str, tuple[str, str]] = {
    "customDimensions": ("customDimensions", "archive"),
    "customMetrics": ("customMetrics", "archive"),
    "keyEvents": ("keyEvents", "delete"),
    "dataStreams": ("dataStreams", "delete"),
}


def ga4_admin_delete(
    name: Annotated[
        str,
        Field(
            description=(
                "Full resource name from a read tool, e.g. "
                "'properties/123/customDimensions/456' or 'properties/123/dataStreams/789'."
            ),
            min_length=1,
        ),
    ],
    confirm_token: Annotated[
        str | None,
        Field(
            description=(
                "Omit on the first call — it returns a token and a summary instead of "
                "deleting. Pass the token back (same name) to execute."
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """Delete or archive a GA4 entity by resource name. Two-phase.

    Custom dimensions/metrics are ARCHIVED (permanent — GA4 has no unarchive
    or true delete for them); key events and data streams are DELETED.
    Deleting a data stream stops collection for it. Properties cannot be
    deleted through this tool by design.
    """
    segments = [segment for segment in name.split("/") if segment]
    if len(segments) != 4 or segments[0] != "properties":
        raise ToolError(
            f"'{name}' is not a deletable GA4 resource name. Expected "
            "'properties/{{property_id}}/<collection>/{{id}}' from a read tool. "
            f"Supported collections: {', '.join(sorted(_OPERATIONS))}."
        )
    collection = segments[2]
    if collection not in _OPERATIONS:
        raise ToolError(
            f"'{collection}' cannot be deleted through this tool. "
            f"Supported: {', '.join(sorted(_OPERATIONS))}. Properties are excluded by design."
        )
    attribute, verb = _OPERATIONS[collection]
    args = {"name": "/".join(segments)}
    if confirm_token is None:
        return confirm.store.pending(
            "ga4_admin_delete",
            args,
            summary=f"PERMANENTLY {verb.upper()} GA4 resource '{name}'. "
            + (
                "Archived custom definitions cannot be restored."
                if verb == "archive"
                else "This cannot be undone through the API."
            ),
        )
    if not confirm.store.redeem("ga4_admin_delete", args, confirm_token):
        raise ToolError(
            "Invalid, expired, or already-used confirm_token for this exact operation. "
            "Call again without confirm_token to get a fresh one."
        )
    resource = getattr(auth.get_service(*ADMIN_API).properties(), attribute)()
    if verb == "archive":
        execute(resource.archive(name=args["name"], body={}))
    else:
        execute(resource.delete(name=args["name"]))
    return {verb + "d": args["name"]}


SPECS = [
    ToolSpec(
        ga4_admin_delete,
        "ga4_admin_delete",
        Tier.DESTRUCTIVE,
        destructive_tool("Delete/Archive GA4 Entity"),
    ),
]
