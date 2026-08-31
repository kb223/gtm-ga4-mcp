"""GTM destructive-tier tools: delete, publish, and user permissions.

Available only with --allow-destructive. Every tool here is two-phase: the
first call returns a one-time confirm_token bound to the exact operation plus
a human-readable summary; only a second call with that token executes.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .. import auth, confirm
from ..config import Tier
from ..ratelimit import execute_gtm
from ..registry import ToolSpec, destructive_tool
from .gtm import _GET_CHAINS, GTM_API, _segments

# Deletable collections. Accounts and containers are excluded on purpose:
# deleting a container erases every version and workspace in it, and neither
# is something an agent should ever do — remove them by hand in the GTM UI.
_DELETABLE = {
    "workspaces",
    "environments",
    "versions",
    "tags",
    "triggers",
    "variables",
    "folders",
    "templates",
    "clients",
    "transformations",
    "zones",
}


def _resource(chain: tuple[str, ...]):
    resource = auth.get_service(*GTM_API)
    for attribute in chain:
        resource = getattr(resource, attribute)()
    return resource


def gtm_delete(
    path: Annotated[
        str,
        Field(
            description="Full path of the entity to delete, from gtm_list/gtm_get.",
            min_length=1,
        ),
    ],
    confirm_token: Annotated[
        str | None,
        Field(
            description=(
                "Omit on the first call — it returns a token and a summary instead of "
                "deleting. Pass the token back (same path) to execute."
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """Delete a GTM entity (tag, trigger, variable, workspace, version, ...). Two-phase.

    Without confirm_token nothing is deleted; you get a summary + token to
    confirm with. Deleting a workspace discards its unpublished changes.
    """
    segments = _segments(path)
    if len(segments) < 2 or len(segments) % 2 != 0:
        raise ToolError(f"'{path}' is not a valid GTM entity path.")
    collection = segments[-2]
    if collection not in _DELETABLE:
        raise ToolError(
            f"'{collection}' cannot be deleted through this tool. "
            f"Deletable: {', '.join(sorted(_DELETABLE))}. Accounts and containers are "
            "excluded by design — remove those in the GTM UI."
        )
    args = {"path": "/".join(segments)}
    if confirm_token is None:
        return confirm.store.pending(
            "gtm_delete",
            args,
            summary=f"PERMANENTLY DELETE GTM {collection[:-1]} at '{path}'. "
            "This cannot be undone through the API.",
        )
    if not confirm.store.redeem("gtm_delete", args, confirm_token):
        raise ToolError(
            "Invalid, expired, or already-used confirm_token for this exact operation. "
            "Call again without confirm_token to get a fresh one."
        )
    execute_gtm(_resource(_GET_CHAINS[collection]).delete(path=args["path"]))
    return {"deleted": args["path"]}


def gtm_publish(
    workspace_path: Annotated[
        str,
        Field(
            description="Workspace to publish, e.g. 'accounts/123/containers/456/workspaces/7'.",
            min_length=1,
        ),
    ],
    version_name: Annotated[
        str | None, Field(description="Name for the created version.")
    ] = None,
    notes: Annotated[str | None, Field(description="Notes for the created version.")] = None,
    confirm_token: Annotated[
        str | None,
        Field(
            description=(
                "Omit on the first call — it returns a token and a summary instead of "
                "publishing. Pass the token back (same arguments) to execute."
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """Compile a GTM workspace into a version and publish it LIVE. Two-phase.

    Publishing deploys the container to every page that loads it — treat it
    like a production release. The source workspace is consumed by versioning.
    """
    segments = _segments(workspace_path)
    if len(segments) != 6 or segments[-2] != "workspaces":
        raise ToolError(
            f"'{workspace_path}' is not a workspace path. Expected "
            "'accounts/{{account_id}}/containers/{{container_id}}/workspaces/{{workspace_id}}'."
        )
    args = {"workspace_path": "/".join(segments), "version_name": version_name, "notes": notes}
    if confirm_token is None:
        return confirm.store.pending(
            "gtm_publish",
            args,
            summary=(
                f"PUBLISH workspace '{workspace_path}' LIVE: compiles the workspace into a "
                "new container version and deploys it to every page loading this container. "
                "Review pending changes first (gtm_list of tags/triggers/variables)."
            ),
        )
    if not confirm.store.redeem("gtm_publish", args, confirm_token):
        raise ToolError(
            "Invalid, expired, or already-used confirm_token for this exact operation. "
            "Call again without confirm_token to get a fresh one."
        )
    body: dict[str, Any] = {}
    if version_name:
        body["name"] = version_name
    if notes:
        body["notes"] = notes
    workspaces = _resource(("accounts", "containers", "workspaces"))
    compiled = execute_gtm(
        workspaces.create_version(path=args["workspace_path"], body=body)
    ) or {}
    if compiled.get("compilerError"):
        raise ToolError(
            "Workspace failed to compile into a version — nothing was published. "
            f"Details: {compiled.get('newWorkspacePath', '')} {compiled}"
        )
    version = compiled.get("containerVersion") or {}
    version_path = version.get("path")
    if not version_path:
        raise ToolError(
            f"Version creation returned no path — publish aborted. Response: {compiled}"
        )
    published = execute_gtm(
        _resource(("accounts", "containers", "versions")).publish(path=version_path)
    )
    return {"published_version": version_path, "result": published}


def gtm_permissions(
    action: Annotated[
        str,
        Field(description="'grant' (new user), 'update' (existing permission), or 'revoke'."),
    ],
    account_id: Annotated[
        str | None,
        Field(description="For 'grant': the GTM account ID, e.g. '123456'."),
    ] = None,
    path: Annotated[
        str | None,
        Field(
            description=(
                "For 'update'/'revoke': the permission path from "
                "gtm_list(user_permissions), e.g. 'accounts/123/user_permissions/456'."
            )
        ),
    ] = None,
    body: Annotated[
        dict[str, Any] | None,
        Field(
            description=(
                "For 'grant'/'update': permission JSON, e.g. {'emailAddress': ..., "
                "'accountAccess': {'permission': 'user'}, 'containerAccess': "
                "[{'containerId': ..., 'permission': 'edit'}]}."
            )
        ),
    ] = None,
    confirm_token: Annotated[
        str | None,
        Field(description="Omit first to get a summary + token; pass back to execute."),
    ] = None,
) -> dict[str, Any]:
    """Grant, update, or revoke a user's access to a GTM account. Two-phase.

    Access changes are security-sensitive: always show the summary to the
    user before confirming.
    """
    if action not in ("grant", "update", "revoke"):
        raise ToolError("action must be 'grant', 'update', or 'revoke'.")
    if action == "grant" and (not account_id or not body):
        raise ToolError("'grant' needs account_id and body (with emailAddress + accountAccess).")
    if action in ("update", "revoke") and not path:
        raise ToolError(f"'{action}' needs the permission's path from gtm_list(user_permissions).")
    if action == "update" and not body:
        raise ToolError("'update' needs body with the full permission JSON.")

    args = {"action": action, "account_id": account_id, "path": path, "body": body}
    target = body.get("emailAddress") if body else path
    if confirm_token is None:
        return confirm.store.pending(
            "gtm_permissions",
            args,
            summary=f"{action.upper()} GTM access for '{target}' "
            f"on {'account ' + account_id if account_id else path}.",
        )
    if not confirm.store.redeem("gtm_permissions", args, confirm_token):
        raise ToolError(
            "Invalid, expired, or already-used confirm_token for this exact operation. "
            "Call again without confirm_token to get a fresh one."
        )
    permissions = _resource(("accounts", "user_permissions"))
    if action == "grant":
        created = execute_gtm(permissions.create(parent=f"accounts/{account_id}", body=body))
        return {"granted": created}
    if action == "update":
        return {"updated": execute_gtm(permissions.update(path=path, body=body))}
    execute_gtm(permissions.delete(path=path))
    return {"revoked": path}


SPECS = [
    ToolSpec(gtm_delete, "gtm_delete", Tier.DESTRUCTIVE, destructive_tool("Delete GTM Entity")),
    ToolSpec(
        gtm_publish, "gtm_publish", Tier.DESTRUCTIVE, destructive_tool("Publish GTM Workspace")
    ),
    ToolSpec(
        gtm_permissions,
        "gtm_permissions",
        Tier.DESTRUCTIVE,
        destructive_tool("Manage GTM User Permissions"),
    ),
]
