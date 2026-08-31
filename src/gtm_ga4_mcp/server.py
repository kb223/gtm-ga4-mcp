"""Server assembly: build a FastMCP server exposing only the tools the config allows."""

from __future__ import annotations

import logging
import sys

from mcp.server.mcpserver import MCPServer

from . import auth
from .config import ServerConfig, parse_config
from .registry import all_specs

logger = logging.getLogger("gtm_ga4_mcp")


def build_server(config: ServerConfig) -> MCPServer:
    auth.configure(config.scopes)
    mcp = MCPServer("gtm_ga4_mcp")
    registered = 0
    for spec in all_specs():  # already sorted: deterministic tools/list ordering
        if config.allows(spec.name, spec.tier):
            mcp.tool(name=spec.name, annotations=spec.annotations)(spec.fn)
            registered += 1
        else:
            logger.info("tool %s disabled (tier=%s)", spec.name, spec.tier.name)
    logger.info(
        "gtm_ga4_mcp ready: %d tools registered, max tier=%s", registered, config.max_tier.name
    )
    return mcp


def main() -> None:
    # stdio transport owns stdout; all logging goes to stderr.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(message)s")
    build_server(parse_config()).run()


if __name__ == "__main__":
    main()
