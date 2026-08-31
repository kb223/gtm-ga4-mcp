import pytest
from mcp.server.mcpserver.exceptions import ToolError

from gtm_ga4_mcp.tools.ga4_admin import normalize_property_id
from gtm_ga4_mcp.tools.ga4_data import shape_rows
from gtm_ga4_mcp.tools.gtm import GtmEntityType, _summarize, gtm_get, gtm_list


def test_gtm_summary_keeps_identity_fields_and_drops_bulk():
    tag = {
        "path": "accounts/1/containers/2/workspaces/3/tags/4",
        "accountId": "1",
        "containerId": "2",
        "workspaceId": "3",
        "tagId": "4",
        "name": "GA4 Config",
        "type": "gaawc",
        "parameter": [{"key": "measurementId", "value": "G-XXXX"}],
        "fingerprint": "1234567890",
        "monitoringMetadata": {"type": "map"},
    }
    summary = _summarize(tag)
    assert summary == {
        "path": "accounts/1/containers/2/workspaces/3/tags/4",
        "accountId": "1",
        "containerId": "2",
        "workspaceId": "3",
        "tagId": "4",
        "name": "GA4 Config",
        "type": "gaawc",
    }


def test_gtm_list_rejects_wrong_parent_shape_before_any_api_call():
    with pytest.raises(ToolError, match="accounts/\\{account_id\\}"):
        gtm_list(GtmEntityType.CONTAINERS, parent="")
    with pytest.raises(ToolError, match="parent"):
        gtm_list(GtmEntityType.TAGS, parent="accounts/1/containers/2")


def test_gtm_get_rejects_malformed_paths():
    with pytest.raises(ToolError, match="not a valid GTM entity path"):
        gtm_get("accounts/1/containers")
    with pytest.raises(ToolError, match="Unknown GTM collection"):
        gtm_get("accounts/1/gadgets/9")


def test_normalize_property_id_accepts_both_forms():
    assert normalize_property_id("123456") == "123456"
    assert normalize_property_id("properties/123456") == "123456"
    with pytest.raises(ToolError, match="not a valid GA4 property ID"):
        normalize_property_id("my-property")


def test_shape_rows_zips_headers_with_values():
    response = {
        "dimensionHeaders": [{"name": "date"}, {"name": "country"}],
        "metricHeaders": [{"name": "sessions", "type": "TYPE_INTEGER"}],
        "rows": [
            {
                "dimensionValues": [{"value": "20260830"}, {"value": "Canada"}],
                "metricValues": [{"value": "42"}],
            },
            {
                "dimensionValues": [{"value": "20260830"}, {"value": "US"}],
                "metricValues": [{"value": "1337"}],
            },
        ],
    }
    assert shape_rows(response) == [
        {"date": "20260830", "country": "Canada", "sessions": "42"},
        {"date": "20260830", "country": "US", "sessions": "1337"},
    ]


def test_shape_rows_handles_empty_response():
    assert shape_rows({}) == []
