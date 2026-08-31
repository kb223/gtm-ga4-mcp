"""GA4 Admin write-tier tools: create and update (dry-run by default)."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .. import auth
from ..config import Tier
from ..ratelimit import execute
from ..registry import ToolSpec, write_tool
from .ga4_admin import ADMIN_API, normalize_property_id


class Ga4WriteEntityType(str, Enum):
    CUSTOM_DIMENSIONS = "custom_dimensions"
    CUSTOM_METRICS = "custom_metrics"
    KEY_EVENTS = "key_events"
    DATA_STREAMS = "data_streams"
    PROPERTY = "property"  # update only


_ATTRS: dict[Ga4WriteEntityType, str] = {
    Ga4WriteEntityType.CUSTOM_DIMENSIONS: "customDimensions",
    Ga4WriteEntityType.CUSTOM_METRICS: "customMetrics",
    Ga4WriteEntityType.KEY_EVENTS: "keyEvents",
    Ga4WriteEntityType.DATA_STREAMS: "dataStreams",
}


def _resource(entity_type: Ga4WriteEntityType):
    service = auth.get_service(*ADMIN_API)
    if entity_type is Ga4WriteEntityType.PROPERTY:
        return service.properties()
    return getattr(service.properties(), _ATTRS[entity_type])()


def ga4_admin_create(
    entity_type: Annotated[
        Ga4WriteEntityType,
        Field(
            description=(
                "What to create: custom_dimensions, custom_metrics, key_events, or data_streams."
            )
        ),
    ],
    property_id: Annotated[
        str, Field(description="GA4 property ID, e.g. '123456' or 'properties/123456'.")
    ],
    body: Annotated[
        dict[str, Any],
        Field(
            description=(
                "Entity JSON per the Admin API, e.g. a custom dimension: "
                "{'parameterName': 'lead_type', 'displayName': 'Lead Type', 'scope': 'EVENT'}."
            )
        ),
    ],
    dry_run: Annotated[
        bool,
        Field(description="True (default) echoes the request without sending it."),
    ] = True,
) -> dict[str, Any]:
    """Create a GA4 custom dimension, custom metric, key event, or data stream on a property.

    Defaults to dry-run: nothing is sent until called with dry_run=False.
    """
    if entity_type is Ga4WriteEntityType.PROPERTY:
        raise ToolError("Properties cannot be created here — use ga4_admin_update to modify one.")
    bare = normalize_property_id(property_id)
    if dry_run:
        return {
            "dry_run": True,
            "would_call": f"analyticsadmin.properties.{_ATTRS[entity_type]}.create",
            "parent": f"properties/{bare}",
            "body": body,
            "note": "Nothing was sent. Re-call with dry_run=false to create this entity.",
        }
    created = execute(_resource(entity_type).create(parent=f"properties/{bare}", body=body))
    return {"created": created}


def ga4_admin_update(
    entity_type: Annotated[
        Ga4WriteEntityType,
        Field(description="What to update, including 'property' for the property itself."),
    ],
    name: Annotated[
        str,
        Field(
            description=(
                "Full resource name from a read tool, e.g. "
                "'properties/123/customDimensions/456' or 'properties/123' for the property."
            ),
            min_length=1,
        ),
    ],
    body: Annotated[
        dict[str, Any],
        Field(description="Fields to change, e.g. {'displayName': 'New name'}."),
    ],
    update_mask: Annotated[
        str,
        Field(
            description=(
                "Comma-separated field names being updated (e.g. 'displayName,description'), "
                "or '*' to update every field present in body."
            ),
            min_length=1,
        ),
    ],
    dry_run: Annotated[
        bool,
        Field(description="True (default) echoes the request without sending it."),
    ] = True,
) -> dict[str, Any]:
    """Update a GA4 entity (or the property itself) by resource name. Defaults to dry-run.

    Unlike GTM, GA4 updates are partial: only fields named in update_mask change.
    """
    if not name.startswith("properties/"):
        raise ToolError(
            f"'{name}' is not a GA4 resource name. Expected e.g. "
            "'properties/123/customDimensions/456' — copy it from a read tool result."
        )
    if dry_run:
        return {
            "dry_run": True,
            "would_call": "analyticsadmin patch",
            "name": name,
            "update_mask": update_mask,
            "body": body,
            "note": "Nothing was sent. Re-call with dry_run=false to apply this update.",
        }
    updated = execute(
        _resource(entity_type).patch(name=name, updateMask=update_mask, body=body)
    )
    return {"updated": updated}


SPECS = [
    ToolSpec(ga4_admin_create, "ga4_admin_create", Tier.WRITE, write_tool("Create GA4 Entity")),
    ToolSpec(ga4_admin_update, "ga4_admin_update", Tier.WRITE, write_tool("Update GA4 Entity")),
]
