"""tigergraph-mcp client with a hard tool allowlist.

The allowlist is enforced twice:
  1. server side, by starting tigergraph-mcp with TG_ALLOWED_TOOLS, so
     non-allowlisted tools are never advertised or dispatchable;
  2. client side, in `call()`, so a bug or a prompt-injected tool name fails
     before it reaches the server.

`run_installed_query` is the only way the agent writes to the graph, so it is
further restricted to the query names in ALLOWED_QUERIES.
"""

import asyncio
import json
import os
import re
import shutil
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config.settings import tg_env

# Read-only graph access + installed queries + vector search/upsert.
# Deliberately excluded: gsql, run_query (arbitrary text), install/drop_query,
# add/delete node/edge, update_schema, drop_graph, clear_graph_data,
# loading jobs, data sources.
ALLOWED_TOOLS = frozenset({
    "tigergraph__list_graphs",
    "tigergraph__get_graph_schema",
    "tigergraph__show_graph_details",
    "tigergraph__get_vertex_count",
    "tigergraph__get_edge_count",
    "tigergraph__get_node",
    "tigergraph__get_nodes",
    "tigergraph__has_node",
    "tigergraph__get_node_edges",
    "tigergraph__get_node_degree",
    "tigergraph__get_neighbors",
    "tigergraph__get_edge",
    "tigergraph__get_edges",
    "tigergraph__has_edge",
    "tigergraph__is_query_installed",
    "tigergraph__get_query_metadata",
    "tigergraph__run_installed_query",
    "tigergraph__list_vector_attributes",
    "tigergraph__get_vector_index_status",
    "tigergraph__search_top_k_similarity",
    "tigergraph__fetch_vector",
    "tigergraph__upsert_vectors",
})

# Installed queries the agent may run (CLAUDE.md §3). Pattern detectors are
# matched by prefix since their names depend on the dataset README.
ALLOWED_QUERIES = frozenset({
    "entity_profile", "txn_neighborhood", "shared_entities", "velocity_window",
    "ring_detect", "entity_centrality", "similar_cases",
    "upsert_case", "add_evidence", "add_action", "policy_search",
})
ALLOWED_QUERY_PREFIXES = ("pattern_",)


class ToolNotAllowed(PermissionError):
    pass


def check_allowed(tool: str, args: dict[str, Any]) -> None:
    if tool not in ALLOWED_TOOLS:
        raise ToolNotAllowed(f"MCP tool '{tool}' is not in the allowlist")
    if tool == "tigergraph__run_installed_query":
        q = args.get("query_name", "")
        if q not in ALLOWED_QUERIES and not q.startswith(ALLOWED_QUERY_PREFIXES):
            raise ToolNotAllowed(f"Installed query '{q}' is not in the allowlist")


def _server_command() -> str:
    # Prefer the entry point from the interpreter's own env (.venv/bin).
    local = Path(sys.executable).parent / "tigergraph-mcp"
    return str(local) if local.exists() else (shutil.which("tigergraph-mcp") or "tigergraph-mcp")


class TigerGraphMCP:
    """Async context manager around a stdio tigergraph-mcp session.

        async with TigerGraphMCP() as tg:
            graphs = await tg.call("tigergraph__list_graphs")
    """

    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self.session: ClientSession | None = None

    async def __aenter__(self) -> "TigerGraphMCP":
        env = {
            "PATH": os.environ.get("PATH", ""),
            **tg_env(),
            "TG_ALLOWED_TOOLS": ",".join(sorted(ALLOWED_TOOLS)),
        }
        params = StdioServerParameters(command=_server_command(), args=[], env=env)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        return self

    async def __aexit__(self, *exc) -> None:
        await self._stack.aclose()

    async def list_tools(self) -> list[str]:
        result = await self.session.list_tools()
        return [t.name for t in result.tools]

    async def call(self, tool: str, args: dict[str, Any] | None = None) -> Any:
        args = args or {}
        check_allowed(tool, args)
        result = await self.session.call_tool(tool, args)
        text = "\n".join(c.text for c in result.content if getattr(c, "text", None))
        if getattr(result, "isError", False):
            raise RuntimeError(f"{tool} failed: {text}")
        # tigergraph-mcp replies with a ```json envelope {success, data, error, ...} plus markdown.
        m = re.search(r"```json\n(.*?)\n```", text, re.S)
        try:
            envelope = json.loads(m.group(1) if m else text)
        except (json.JSONDecodeError, TypeError):
            return text
        if isinstance(envelope, dict) and "success" in envelope:
            if not envelope["success"]:
                raise RuntimeError(f"{tool} failed: {envelope.get('error') or envelope.get('summary')}")
            return envelope.get("data")
        return envelope


def call_sync(tool: str, args: dict[str, Any] | None = None) -> Any:
    """One-shot call for scripts; opens and closes a session."""
    async def _run():
        async with TigerGraphMCP() as tg:
            return await tg.call(tool, args)
    return asyncio.run(_run())
