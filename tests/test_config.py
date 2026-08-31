from gtm_ga4_mcp.config import (
    GA4_EDIT_SCOPE,
    GA4_READ_SCOPE,
    GTM_DELETE_SCOPE,
    GTM_PUBLISH_SCOPE,
    GTM_READ_SCOPE,
    ServerConfig,
    Tier,
    parse_config,
)


def test_default_is_read_only():
    config = parse_config(argv=[], env={})
    assert config.max_tier == Tier.READ
    assert config.denylist == frozenset()
    assert set(config.scopes) == {GTM_READ_SCOPE, GA4_READ_SCOPE}


def test_write_flag_enables_write_tier():
    config = parse_config(argv=["--allow-write"], env={})
    assert config.max_tier == Tier.WRITE
    assert GA4_EDIT_SCOPE in config.scopes
    assert GTM_DELETE_SCOPE not in config.scopes


def test_destructive_flag_implies_write():
    config = parse_config(argv=["--allow-destructive"], env={})
    assert config.max_tier == Tier.DESTRUCTIVE
    assert GTM_PUBLISH_SCOPE in config.scopes
    assert GA4_EDIT_SCOPE in config.scopes  # write scopes included too


def test_env_vars_enable_tiers():
    config = parse_config(argv=[], env={"GTM_GA4_MCP_ALLOW_WRITE": "true"})
    assert config.max_tier == Tier.WRITE
    config = parse_config(argv=[], env={"GTM_GA4_MCP_ALLOW_DESTRUCTIVE": "1"})
    assert config.max_tier == Tier.DESTRUCTIVE
    config = parse_config(argv=[], env={"GTM_GA4_MCP_ALLOW_WRITE": "false"})
    assert config.max_tier == Tier.READ


def test_denylist_merges_env_and_flags():
    config = parse_config(
        argv=["--deny", "gtm_get"],
        env={"GTM_GA4_MCP_DENY": "ga4_run_report, ga4_metadata"},
    )
    assert config.denylist == frozenset({"gtm_get", "ga4_run_report", "ga4_metadata"})


def test_allows_gates_on_tier_and_denylist():
    config = ServerConfig(max_tier=Tier.READ, denylist=frozenset({"gtm_get"}))
    assert config.allows("gtm_list", Tier.READ)
    assert not config.allows("gtm_get", Tier.READ)  # denied by name
    assert not config.allows("gtm_create", Tier.WRITE)  # above tier
