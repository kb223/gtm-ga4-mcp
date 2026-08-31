import pytest
from mcp.server.mcpserver.exceptions import ToolError

from gtm_ga4_mcp.tools.ga4_destructive import ga4_admin_delete
from gtm_ga4_mcp.tools.gtm_destructive import gtm_delete, gtm_permissions, gtm_publish

TAG_PATH = "accounts/1/containers/2/workspaces/3/tags/4"
WORKSPACE = "accounts/1/containers/2/workspaces/3"


def test_gtm_delete_first_call_confirms_not_deletes(confirm_clock, fake_service):
    result = gtm_delete(TAG_PATH)
    assert result["status"] == "confirmation_required"
    assert "DELETE" in result["summary"]
    assert fake_service.calls == []  # nothing touched the API


def test_gtm_delete_executes_with_valid_token(confirm_clock, fake_service):
    token = gtm_delete(TAG_PATH)["confirm_token"]
    result = gtm_delete(TAG_PATH, confirm_token=token)
    assert result == {"deleted": TAG_PATH}
    assert fake_service.calls == [
        ("accounts.containers.workspaces.tags.delete", {"path": TAG_PATH})
    ]


def test_gtm_delete_token_does_not_transfer_to_other_path(confirm_clock, fake_service):
    token = gtm_delete(TAG_PATH)["confirm_token"]
    other = "accounts/1/containers/2/workspaces/3/tags/5"
    with pytest.raises(ToolError, match="confirm_token"):
        gtm_delete(other, confirm_token=token)
    assert fake_service.calls == []


def test_gtm_delete_token_single_use(confirm_clock, fake_service):
    token = gtm_delete(TAG_PATH)["confirm_token"]
    gtm_delete(TAG_PATH, confirm_token=token)
    with pytest.raises(ToolError, match="confirm_token"):
        gtm_delete(TAG_PATH, confirm_token=token)


def test_gtm_delete_refuses_containers_and_accounts(confirm_clock, no_service):
    with pytest.raises(ToolError, match="cannot be deleted"):
        gtm_delete("accounts/1/containers/2")
    with pytest.raises(ToolError, match="cannot be deleted"):
        gtm_delete("accounts/1")


def test_gtm_publish_two_phase_and_call_order(confirm_clock, fake_service):
    fake_service.responses["accounts.containers.workspaces.create_version"] = {
        "containerVersion": {"path": "accounts/1/containers/2/versions/42"}
    }
    fake_service.responses["accounts.containers.versions.publish"] = {"containerVersion": {}}

    pending = gtm_publish(WORKSPACE, notes="release")
    assert pending["status"] == "confirmation_required"
    assert "LIVE" in pending["summary"]
    assert fake_service.calls == []

    result = gtm_publish(WORKSPACE, notes="release", confirm_token=pending["confirm_token"])
    assert result["published_version"] == "accounts/1/containers/2/versions/42"
    assert [dotted for dotted, _ in fake_service.calls] == [
        "accounts.containers.workspaces.create_version",
        "accounts.containers.versions.publish",
    ]


def test_gtm_publish_aborts_on_compiler_error(confirm_clock, fake_service):
    fake_service.responses["accounts.containers.workspaces.create_version"] = {
        "compilerError": True
    }
    token = gtm_publish(WORKSPACE)["confirm_token"]
    with pytest.raises(ToolError, match="compile"):
        gtm_publish(WORKSPACE, confirm_token=token)
    assert [dotted for dotted, _ in fake_service.calls] == [
        "accounts.containers.workspaces.create_version"  # publish never ran
    ]


def test_gtm_publish_validates_workspace_path(confirm_clock, no_service):
    with pytest.raises(ToolError, match="not a workspace path"):
        gtm_publish("accounts/1/containers/2")


def test_gtm_permissions_grant_flow(confirm_clock, fake_service):
    fake_service.responses["accounts.user_permissions.create"] = {"emailAddress": "a@b.com"}
    body = {"emailAddress": "a@b.com", "accountAccess": {"permission": "user"}}
    pending = gtm_permissions("grant", account_id="1", body=body)
    assert pending["status"] == "confirmation_required"
    result = gtm_permissions(
        "grant", account_id="1", body=body, confirm_token=pending["confirm_token"]
    )
    assert result == {"granted": {"emailAddress": "a@b.com"}}
    assert fake_service.calls[0][1] == {"parent": "accounts/1", "body": body}


def test_gtm_permissions_validates_arguments(confirm_clock, no_service):
    with pytest.raises(ToolError, match="grant"):
        gtm_permissions("grant", body={"emailAddress": "a@b.com"})  # missing account_id
    with pytest.raises(ToolError, match="revoke"):
        gtm_permissions("revoke")  # missing path
    with pytest.raises(ToolError, match="action"):
        gtm_permissions("destroy", path="accounts/1/user_permissions/2")


def test_ga4_delete_archives_custom_dimensions(confirm_clock, fake_service):
    name = "properties/123/customDimensions/9"
    pending = ga4_admin_delete(name)
    assert "ARCHIVE" in pending["summary"]
    result = ga4_admin_delete(name, confirm_token=pending["confirm_token"])
    assert result == {"archived": name}
    assert fake_service.calls == [
        ("properties.customDimensions.archive", {"name": name, "body": {}})
    ]


def test_ga4_delete_deletes_key_events(confirm_clock, fake_service):
    name = "properties/123/keyEvents/9"
    token = ga4_admin_delete(name)["confirm_token"]
    result = ga4_admin_delete(name, confirm_token=token)
    assert result == {"deleted": name}
    assert fake_service.calls == [("properties.keyEvents.delete", {"name": name})]


def test_ga4_delete_refuses_properties_and_unknown_collections(confirm_clock, no_service):
    with pytest.raises(ToolError, match="not a deletable"):
        ga4_admin_delete("properties/123")
    with pytest.raises(ToolError, match="cannot be deleted"):
        ga4_admin_delete("properties/123/googleAdsLinks/9")
