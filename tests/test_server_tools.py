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


def _list_tools(config: ServerConfig):
    server = build_server(config)
    return asyncio.run(server.list_tools())


def test_read_config_registers_expected_tools_in_alphabetical_order():
    tools = _list_tools(ServerConfig(max_tier=Tier.READ))
    names = [tool.name for tool in tools]
    assert names == EXPECTED_READ_TOOLS
    assert names == sorted(names)


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
    for tool in _list_tools(ServerConfig(max_tier=Tier.READ)):
        assert tool.description and len(tool.description) > 20, tool.name
