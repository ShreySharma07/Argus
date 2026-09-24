"""M0 smoke test: connect to tigergraph-mcp, list tools, run list_graphs.

    .venv/bin/python -m scripts.check_mcp
"""

import asyncio
import sys

from agent.tools.mcp_client import ALLOWED_TOOLS, TigerGraphMCP, ToolNotAllowed
from config.settings import TG_GRAPHNAME, TG_HOST


async def main() -> int:
    if not TG_HOST:
        print("TG_HOST is not set. Copy .env.example to .env and fill in Savanna credentials.")
        return 1
    print(f"Host: {TG_HOST}  graph: {TG_GRAPHNAME or '(none)'}")

    async with TigerGraphMCP() as tg:
        served = set(await tg.list_tools())
        print(f"Server advertises {len(served)} tools")
        leaked = served - ALLOWED_TOOLS
        if leaked:
            print(f"FAIL: server exposes non-allowlisted tools: {sorted(leaked)}")
            return 1

        try:
            await tg.call("tigergraph__drop_graph", {"graph_name": "x"})
            print("FAIL: drop_graph was not blocked")
            return 1
        except ToolNotAllowed:
            print("OK: drop_graph blocked client-side")

        graphs = await tg.call("tigergraph__list_graphs")
        print("list_graphs ->", graphs)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
