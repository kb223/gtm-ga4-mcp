"""GA4 Data API read tools (reports, realtime, metadata)."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from ..auth import get_service
from ..config import Tier
from ..ratelimit import execute
from ..registry import ToolSpec, read_only
from .ga4_admin import normalize_property_id

DATA_API = ("analyticsdata", "v1beta")


def shape_rows(response: dict[str, Any]) -> list[dict[str, str]]:
    """Convert the Data API's parallel-array rows into one dict per row."""
    dimension_names = [h["name"] for h in response.get("dimensionHeaders", [])]
    metric_names = [h["name"] for h in response.get("metricHeaders", [])]
    rows = []
    for row in response.get("rows", []):
        shaped: dict[str, str] = {}
        for name, value in zip(dimension_names, row.get("dimensionValues", []), strict=False):
            shaped[name] = value.get("value", "")
        for name, value in zip(metric_names, row.get("metricValues", []), strict=False):
            shaped[name] = value.get("value", "")
        rows.append(shaped)
    return rows


def ga4_run_report(
    property_id: Annotated[
        str, Field(description="GA4 property ID, e.g. '123456' or 'properties/123456'.")
    ],
    metrics: Annotated[
        list[str],
        Field(
            description=(
                "Metric API names, e.g. ['sessions', 'conversions', 'totalRevenue']. "
                "Discover names via ga4_metadata."
            ),
            min_length=1,
        ),
    ],
    dimensions: Annotated[
        list[str] | None,
        Field(description="Dimension API names, e.g. ['date', 'sessionDefaultChannelGroup']."),
    ] = None,
    start_date: Annotated[
        str,
        Field(description="Start date: 'YYYY-MM-DD', 'NdaysAgo', 'yesterday', or 'today'."),
    ] = "28daysAgo",
    end_date: Annotated[
        str, Field(description="End date: 'YYYY-MM-DD', 'NdaysAgo', 'yesterday', or 'today'.")
    ] = "today",
    limit: Annotated[int, Field(description="Maximum rows to return.", ge=1, le=250)] = 50,
) -> dict[str, Any]:
    """Run a GA4 report over a date range and return one dict per row.

    Rows are keyed by the requested dimension/metric API names. `row_count` is
    the total available on the server; raise `limit` or refine dimensions if
    rows were truncated.
    """
    bare = normalize_property_id(property_id)
    body: dict[str, Any] = {
        "dateRanges": [{"startDate": start_date, "endDate": end_date}],
        "metrics": [{"name": name} for name in metrics],
        "dimensions": [{"name": name} for name in (dimensions or [])],
        "limit": limit,
    }
    service = get_service(*DATA_API)
    response = execute(
        service.properties().runReport(property=f"properties/{bare}", body=body)
    ) or {}
    return {
        "property": f"properties/{bare}",
        "date_range": {"start_date": start_date, "end_date": end_date},
        "row_count": response.get("rowCount", 0),
        "rows": shape_rows(response),
    }


def ga4_run_realtime_report(
    property_id: Annotated[
        str, Field(description="GA4 property ID, e.g. '123456' or 'properties/123456'.")
    ],
    metrics: Annotated[
        list[str],
        Field(
            description="Realtime metric API names, e.g. ['activeUsers', 'eventCount'].",
            min_length=1,
        ),
    ],
    dimensions: Annotated[
        list[str] | None,
        Field(description="Realtime dimension API names, e.g. ['eventName', 'country']."),
    ] = None,
    limit: Annotated[int, Field(description="Maximum rows to return.", ge=1, le=250)] = 50,
) -> dict[str, Any]:
    """Run a GA4 realtime report (last 30 minutes) — e.g. to verify events are firing now."""
    bare = normalize_property_id(property_id)
    body: dict[str, Any] = {
        "metrics": [{"name": name} for name in metrics],
        "dimensions": [{"name": name} for name in (dimensions or [])],
        "limit": limit,
    }
    service = get_service(*DATA_API)
    response = execute(
        service.properties().runRealtimeReport(property=f"properties/{bare}", body=body)
    ) or {}
    return {
        "property": f"properties/{bare}",
        "row_count": response.get("rowCount", 0),
        "rows": shape_rows(response),
    }


def ga4_metadata(
    property_id: Annotated[
        str, Field(description="GA4 property ID, e.g. '123456' or 'properties/123456'.")
    ],
    search: Annotated[
        str | None,
        Field(description="Optional case-insensitive filter on API/UI names, e.g. 'revenue'."),
    ] = None,
) -> dict[str, Any]:
    """List the dimension/metric API names available on a property (standard + custom).

    Use this before ga4_run_report to find exact API names.
    """
    bare = normalize_property_id(property_id)
    service = get_service(*DATA_API)
    response = execute(
        service.properties().getMetadata(name=f"properties/{bare}/metadata")
    ) or {}

    def trim(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        trimmed = [
            {
                "api_name": item.get("apiName"),
                "ui_name": item.get("uiName"),
                "custom": bool(item.get("customDefinition")),
            }
            for item in items
        ]
        if search:
            needle = search.lower()
            trimmed = [
                item
                for item in trimmed
                if needle in (item["api_name"] or "").lower()
                or needle in (item["ui_name"] or "").lower()
            ]
        return trimmed

    dimensions = trim(response.get("dimensions", []))
    metrics = trim(response.get("metrics", []))
    return {
        "property": f"properties/{bare}",
        "dimension_count": len(dimensions),
        "metric_count": len(metrics),
        "dimensions": dimensions,
        "metrics": metrics,
    }


SPECS = [
    ToolSpec(ga4_run_report, "ga4_run_report", Tier.READ, read_only("Run GA4 Report")),
    ToolSpec(
        ga4_run_realtime_report,
        "ga4_run_realtime_report",
        Tier.READ,
        read_only("Run GA4 Realtime Report"),
    ),
    ToolSpec(ga4_metadata, "ga4_metadata", Tier.READ, read_only("List GA4 Dimensions & Metrics")),
]
