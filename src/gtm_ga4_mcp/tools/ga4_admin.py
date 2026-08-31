"""GA4 Admin API read tools (accounts, properties, and property sub-entities)."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from ..auth import get_service
from ..config import Tier
from ..ratelimit import execute
from ..registry import ToolSpec, read_only

ADMIN_API = ("analyticsadmin", "v1beta")


class Ga4AdminEntityType(str, Enum):
    DATA_STREAMS = "data_streams"
    KEY_EVENTS = "key_events"
    CUSTOM_DIMENSIONS = "custom_dimensions"
    CUSTOM_METRICS = "custom_metrics"
    GOOGLE_ADS_LINKS = "google_ads_links"
    FIREBASE_LINKS = "firebase_links"

# entity -> (service attribute, response list key)
_ADMIN_RESOURCES: dict[Ga4AdminEntityType, tuple[str, str]] = {
    Ga4AdminEntityType.DATA_STREAMS: ("dataStreams", "dataStreams"),
    Ga4AdminEntityType.KEY_EVENTS: ("keyEvents", "keyEvents"),
    Ga4AdminEntityType.CUSTOM_DIMENSIONS: ("customDimensions", "customDimensions"),
    Ga4AdminEntityType.CUSTOM_METRICS: ("customMetrics", "customMetrics"),
    Ga4AdminEntityType.GOOGLE_ADS_LINKS: ("googleAdsLinks", "googleAdsLinks"),
    Ga4AdminEntityType.FIREBASE_LINKS: ("firebaseLinks", "firebaseLinks"),
}


def normalize_property_id(property_id: str) -> str:
    """Accept '123456' or 'properties/123456'; return the bare numeric ID."""
    bare = property_id.strip().removeprefix("properties/")
    if not bare.isdigit():
        raise ToolError(
            f"'{property_id}' is not a valid GA4 property ID. Expected a numeric ID like "
            "'123456' or 'properties/123456' — find IDs via ga4_account_summaries."
        )
    return bare


def ga4_account_summaries(
    page_token: Annotated[
        str | None, Field(description="Pagination token from a previous response.")
    ] = None,
) -> dict[str, Any]:
    """List every GA4 account and property the authenticated user can access.

    This is the entry point for all GA4 work — it returns the property IDs the
    other ga4_* tools need.
    """
    kwargs: dict[str, Any] = {"pageSize": 200}
    if page_token:
        kwargs["pageToken"] = page_token
    service = get_service(*ADMIN_API)
    response = execute(service.accountSummaries().list(**kwargs)) or {}
    summaries = [
        {
            "account": item.get("account"),
            "account_display_name": item.get("displayName"),
            "properties": [
                {
                    "property": prop.get("property"),
                    "display_name": prop.get("displayName"),
                    "property_type": prop.get("propertyType"),
                }
                for prop in item.get("propertySummaries", [])
            ],
        }
        for item in response.get("accountSummaries", [])
    ]
    return {
        "count": len(summaries),
        "accounts": summaries,
        "next_page_token": response.get("nextPageToken"),
    }


def ga4_property_get(
    property_id: Annotated[
        str, Field(description="GA4 property ID, e.g. '123456' or 'properties/123456'.")
    ],
) -> dict[str, Any]:
    """Fetch one GA4 property's full configuration (timezone, currency, industry, service level)."""
    bare = normalize_property_id(property_id)
    service = get_service(*ADMIN_API)
    return execute(service.properties().get(name=f"properties/{bare}"))


def ga4_admin_list(
    entity_type: Annotated[
        Ga4AdminEntityType,
        Field(description="Which property sub-entity to list."),
    ],
    property_id: Annotated[
        str, Field(description="GA4 property ID, e.g. '123456' or 'properties/123456'.")
    ],
    page_token: Annotated[
        str | None, Field(description="Pagination token from a previous response.")
    ] = None,
) -> dict[str, Any]:
    """List a GA4 property's sub-entities.

    Covers data streams, key events, custom dimensions/metrics, Google Ads
    links, and Firebase links.
    """
    bare = normalize_property_id(property_id)
    attribute, response_key = _ADMIN_RESOURCES[entity_type]
    kwargs: dict[str, Any] = {"parent": f"properties/{bare}"}
    if page_token:
        kwargs["pageToken"] = page_token
    service = get_service(*ADMIN_API)
    resource = getattr(service.properties(), attribute)()
    response = execute(resource.list(**kwargs)) or {}
    items = response.get(response_key, [])
    return {
        "entity_type": entity_type.value,
        "property": f"properties/{bare}",
        "count": len(items),
        "items": items,
        "next_page_token": response.get("nextPageToken"),
    }


SPECS = [
    ToolSpec(
        ga4_account_summaries,
        "ga4_account_summaries",
        Tier.READ,
        read_only("List GA4 Accounts & Properties"),
    ),
    ToolSpec(ga4_property_get, "ga4_property_get", Tier.READ, read_only("Get GA4 Property")),
    ToolSpec(ga4_admin_list, "ga4_admin_list", Tier.READ, read_only("List GA4 Property Entities")),
]
