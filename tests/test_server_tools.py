import asyncio

from gtm_ga4_mcp.config import ServerConfig, Tier
from gtm_ga4_mcp.server import build_server

EXPECTED_READ_TOOLS = [
    "ga4_account_summaries",
    "ga4_admin_list",
    "ga4_metadata",
    "ga4_property_get",
    "ga4_run_realtime_report",
    "ga4_run_report",
    "gtm_get",
    "gtm_list",
]

EXPECTED_WRITE_TOOLS = ["ga4_admin_create", "ga4_admin_update", "gtm_create", "gtm_update"]

EXPECTED_DESTRUCTIVE_TOOLS = ["ga4_admin_delete", "gtm_delete", "gtm_permissions", "gtm_publish"]


def _list_tools(config: ServerConfig):
    server = build_server(config)
    return asyncio.run(server.list_tools())


def test_read_config_registers_expected_tools_in_alphabetical_order():
    tools = _list_tools(ServerConfig(max_tier=Tier.READ))
    names = [tool.name for tool in tools]
    assert names == EXPECTED_READ_TOOLS
    assert names == sorted(names)


def test_write_config_adds_write_tools_only():
    names = {tool.name for tool in _list_tools(ServerConfig(max_tier=Tier.WRITE))}
    assert names == set(EXPECTED_READ_TOOLS) | set(EXPECTED_WRITE_TOOLS)


def test_destructive_config_registers_all_sixteen_tools():
    names = [tool.name for tool in _list_tools(ServerConfig(max_tier=Tier.DESTRUCTIVE))]
    assert names == sorted(
        EXPECTED_READ_TOOLS + EXPECTED_WRITE_TOOLS + EXPECTED_DESTRUCTIVE_TOOLS
    )
    assert len(names) == 16


def test_destructive_tools_are_annotated_destructive():
    tools = {tool.name: tool for tool in _list_tools(ServerConfig(max_tier=Tier.DESTRUCTIVE))}
    for name in EXPECTED_DESTRUCTIVE_TOOLS:
        assert tools[name].annotations.destructive_hint is True, name
        assert tools[name].annotations.read_only_hint is False, name
    for name in EXPECTED_WRITE_TOOLS:
        assert tools[name].annotations.destructive_hint is False, name
        assert tools[name].annotations.read_only_hint is False, name


def test_all_v01_tools_are_annotated_read_only():
    for tool in _list_tools(ServerConfig(max_tier=Tier.READ)):
        assert tool.annotations is not None, tool.name
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.destructive_hint is False, tool.name


def test_denylist_removes_tool_from_registration():
    tools = _list_tools(ServerConfig(max_tier=Tier.READ, denylist=frozenset({"gtm_get"})))
    names = [tool.name for tool in tools]
    assert "gtm_get" not in names
    assert "gtm_list" in names


def test_every_tool_has_a_description():
    for tool in _list_tools(ServerConfig(max_tier=Tier.DESTRUCTIVE)):
        assert tool.description and len(tool.description) > 20, tool.name
