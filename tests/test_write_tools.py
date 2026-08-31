import pytest
from mcp.server.mcpserver.exceptions import ToolError

from gtm_ga4_mcp.tools.ga4_write import Ga4WriteEntityType, ga4_admin_create, ga4_admin_update
from gtm_ga4_mcp.tools.gtm import GtmEntityType
from gtm_ga4_mcp.tools.gtm_write import gtm_create, gtm_update

WORKSPACE = "accounts/1/containers/2/workspaces/3"
TAG_BODY = {"name": "GA4 Config", "type": "gaawc"}


def test_gtm_create_dry_run_by_default_never_builds_a_client(no_service):
    result = gtm_create(GtmEntityType.TAGS, parent=WORKSPACE, body=TAG_BODY)
    assert result["dry_run"] is True
    assert result["body"] == TAG_BODY
    assert "tags.create" in result["would_call"]


def test_gtm_create_executes_when_dry_run_disabled(fake_service):
    fake_service.responses["accounts.containers.workspaces.tags.create"] = {"tagId": "9"}
    result = gtm_create(GtmEntityType.TAGS, parent=WORKSPACE, body=TAG_BODY, dry_run=False)
    assert result == {"created": {"tagId": "9"}}
    assert fake_service.calls == [
        ("accounts.containers.workspaces.tags.create", {"parent": WORKSPACE, "body": TAG_BODY})
    ]


def test_gtm_create_rejects_non_writable_entities(no_service):
    with pytest.raises(ToolError, match="cannot be written"):
        gtm_create(GtmEntityType.ACCOUNTS, parent="", body={})
    with pytest.raises(ToolError, match="cannot be written"):
        gtm_create(GtmEntityType.VERSIONS, parent="accounts/1/containers/2", body={})


def test_gtm_create_validates_parent_shape(no_service):
    with pytest.raises(ToolError, match="parent"):
        gtm_create(GtmEntityType.TAGS, parent="accounts/1", body=TAG_BODY)


def test_gtm_update_dry_run_by_default(no_service):
    result = gtm_update(path=f"{WORKSPACE}/tags/4", body=TAG_BODY)
    assert result["dry_run"] is True


def test_gtm_update_executes_with_fingerprint(fake_service):
    fake_service.responses["accounts.containers.workspaces.tags.update"] = {"tagId": "4"}
    result = gtm_update(
        path=f"{WORKSPACE}/tags/4", body=TAG_BODY, fingerprint="abc", dry_run=False
    )
    assert result == {"updated": {"tagId": "4"}}
    dotted, kwargs = fake_service.calls[0]
    assert dotted == "accounts.containers.workspaces.tags.update"
    assert kwargs["fingerprint"] == "abc"


def test_gtm_update_rejects_non_writable_collections(no_service):
    with pytest.raises(ToolError, match="cannot be updated"):
        gtm_update(path="accounts/1/containers/2", body={})


DIMENSION_BODY = {"parameterName": "lead_type", "displayName": "Lead Type", "scope": "EVENT"}


def test_ga4_create_dry_run_by_default(no_service):
    result = ga4_admin_create(
        Ga4WriteEntityType.CUSTOM_DIMENSIONS, property_id="123", body=DIMENSION_BODY
    )
    assert result["dry_run"] is True
    assert result["parent"] == "properties/123"


def test_ga4_create_executes(fake_service):
    fake_service.responses["properties.customDimensions.create"] = {
        "name": "properties/123/customDimensions/9"
    }
    result = ga4_admin_create(
        Ga4WriteEntityType.CUSTOM_DIMENSIONS,
        property_id="properties/123",
        body=DIMENSION_BODY,
        dry_run=False,
    )
    assert result["created"]["name"].endswith("/9")
    assert fake_service.calls[0][1] == {"parent": "properties/123", "body": DIMENSION_BODY}


def test_ga4_create_rejects_property(no_service):
    with pytest.raises(ToolError, match="cannot be created"):
        ga4_admin_create(Ga4WriteEntityType.PROPERTY, property_id="123", body={})


def test_ga4_update_requires_resource_name(no_service):
    with pytest.raises(ToolError, match="not a GA4 resource name"):
        ga4_admin_update(
            Ga4WriteEntityType.CUSTOM_DIMENSIONS, name="123", body={}, update_mask="*"
        )


def test_ga4_update_executes_patch_with_mask(fake_service):
    fake_service.responses["properties.customDimensions.patch"] = {"displayName": "New"}
    result = ga4_admin_update(
        Ga4WriteEntityType.CUSTOM_DIMENSIONS,
        name="properties/123/customDimensions/9",
        body={"displayName": "New"},
        update_mask="displayName",
        dry_run=False,
    )
    assert result == {"updated": {"displayName": "New"}}
    dotted, kwargs = fake_service.calls[0]
    assert dotted == "properties.customDimensions.patch"
    assert kwargs["updateMask"] == "displayName"


def test_ga4_property_update_targets_properties_resource(fake_service):
    fake_service.responses["properties.patch"] = {"timeZone": "America/Edmonton"}
    result = ga4_admin_update(
        Ga4WriteEntityType.PROPERTY,
        name="properties/123",
        body={"timeZone": "America/Edmonton"},
        update_mask="timeZone",
        dry_run=False,
    )
    assert result["updated"]["timeZone"] == "America/Edmonton"
    assert fake_service.calls[0][0] == "properties.patch"
