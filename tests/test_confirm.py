from gtm_ga4_mcp import confirm


def test_pending_then_redeem_same_args(confirm_clock):
    args = {"path": "accounts/1/containers/2/workspaces/3/tags/4"}
    pending = confirm.store.pending("gtm_delete", args, summary="delete tag")
    assert pending["status"] == "confirmation_required"
    assert pending["summary"] == "delete tag"
    token = pending["confirm_token"]
    assert confirm.store.redeem("gtm_delete", args, token) is True


def test_token_is_single_use(confirm_clock):
    args = {"path": "accounts/1"}
    token = confirm.store.pending("gtm_delete", args, summary="s")["confirm_token"]
    assert confirm.store.redeem("gtm_delete", args, token) is True
    assert confirm.store.redeem("gtm_delete", args, token) is False


def test_token_bound_to_exact_operation(confirm_clock):
    token = confirm.store.pending("gtm_delete", {"path": "accounts/1/containers/2"}, "s")[
        "confirm_token"
    ]
    # Different args: the confirmation must not transfer.
    assert confirm.store.redeem("gtm_delete", {"path": "accounts/1/containers/9"}, token) is False
    # Different tool, same args: must not transfer either.
    token2 = confirm.store.pending("gtm_delete", {"path": "a/1"}, "s")["confirm_token"]
    assert confirm.store.redeem("gtm_publish", {"path": "a/1"}, token2) is False


def test_token_expires(confirm_clock):
    args = {"path": "accounts/1"}
    token = confirm.store.pending("gtm_delete", args, summary="s")["confirm_token"]
    confirm_clock.now += confirm.TTL_SECONDS + 1
    assert confirm.store.redeem("gtm_delete", args, token) is False
