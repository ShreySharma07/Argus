"""GraphRAG retrieval: policy / pattern / regulation chunks.

Uses the installed `policy_search` query via MCP when the graph is configured,
otherwise falls back to cosine search over data/knowledge/chunks.jsonl.
"""

import asyncio
import json
from functools import lru_cache

import numpy as np

from agent.embed import embed_query
from config.settings import KNOWLEDGE_CHUNKS, TG_HOST

FIELDS = ("id", "source", "section", "title", "text")


@lru_cache
def _local_index():
    rows = [json.loads(line) for line in open(KNOWLEDGE_CHUNKS)]
    mat = np.array([r.pop("emb") for r in rows], dtype=np.float32)
    mat /= np.linalg.norm(mat, axis=1, keepdims=True)
    return rows, mat


def _search_local(qv: list[float], k: int) -> list[dict]:
    rows, mat = _local_index()
    q = np.asarray(qv, dtype=np.float32)
    sims = mat @ (q / np.linalg.norm(q))
    out = []
    for i in np.argsort(-sims)[:k]:
        r = rows[i]
        out.append({**{f: r[f] for f in FIELDS}, "patterns": r["pattern_ids"], "score": float(sims[i])})
    return out


async def _search_graph(qv: list[float], k: int) -> list[dict]:
    from agent.tools.mcp_client import TigerGraphMCP
    async with TigerGraphMCP() as tg:
        res = await tg.call("tigergraph__run_installed_query",
                            {"query_name": "policy_search", "params": {"qv": qv, "k": k}})
    results = res["result"]
    chunks, dist = results[0]["chunks"], results[1]["distances"]
    out = []
    for c in chunks:
        a = c["attributes"]
        out.append({
            **{f: a.get(f"hits.{f}") for f in FIELDS},
            "patterns": a.get("hits.@patterns", []),
            "score": 1.0 - float(dist.get(c["v_id"], 1.0)),  # cosine distance -> similarity
        })
    return sorted(out, key=lambda r: -r["score"])


def search_policy(query: str, k: int = 5, use_graph: bool | None = None) -> list[dict]:
    qv = embed_query(query)
    if use_graph is None:
        use_graph = bool(TG_HOST)
    if use_graph:
        return asyncio.run(_search_graph(qv, k))
    return _search_local(qv, k)
