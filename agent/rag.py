"""GraphRAG retrieval over the knowledge chunks (policy, patterns, guidance, regulations).

Ranking, per call:
  1. vector candidates from the graph (`policy_search`, filtered by source in GSQL)
  2. BM25 candidates over the same sources (exact terms: R5, BLOCK_CARD, FIN-2011-A016)
  3. reciprocal-rank fusion of 1+2
  4. cross-encoder rerank of the fused top-N (ms-marco-MiniLM-L-6), at most
     MAX_PER_DOC chunks from any one document

Rules are fetched by ID (`get_rule("R2")`) when the agent already knows which rule
applies; similarity search is for open questions. Without TG_HOST, step 1 uses the
local chunk file (same content, same embeddings).
"""

import asyncio
import json
import re
from functools import lru_cache

import numpy as np

from agent.embed import embed_query
from config.settings import KNOWLEDGE_CHUNKS, TG_HOST

FIELDS = ("id", "source", "section", "title", "text")
POLICY_SOURCES = ("policy", "pattern", "guidance")
REGULATION_SOURCES = ("regulation",)
CANDIDATES = 30   # per retriever
RERANK_TOP = 20   # fused candidates sent to the cross-encoder
RRF_K = 60
MAX_PER_DOC = 2


@lru_cache
def _chunks() -> dict[str, dict]:
    rows = {}
    for line in open(KNOWLEDGE_CHUNKS):
        r = json.loads(line)
        rows[r["id"]] = r
    return rows


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_§-]+", text.lower())


@lru_cache
def _bm25(sources: tuple[str, ...]):
    from rank_bm25 import BM25Okapi
    ids = [cid for cid, r in _chunks().items() if r["source"] in sources]
    corpus = [_tokens(f"{_chunks()[i]['title']} {_chunks()[i]['text']}") for i in ids]
    return ids, BM25Okapi(corpus)


@lru_cache
def _reranker():
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    return TextCrossEncoder("Xenova/ms-marco-MiniLM-L-6-v2")


def _vector_local(qv: list[float], sources: tuple[str, ...], k: int) -> list[str]:
    ids = [cid for cid, r in _chunks().items() if r["source"] in sources]
    mat = np.array([_chunks()[i]["emb"] for i in ids], dtype=np.float32)
    q = np.asarray(qv, dtype=np.float32)
    sims = (mat @ q) / (np.linalg.norm(mat, axis=1) * np.linalg.norm(q))
    return [ids[i] for i in np.argsort(-sims)[:k]]


async def _vector_graph(qv: list[float], sources: tuple[str, ...], k: int) -> list[str]:
    from agent.tools.mcp_client import TigerGraphMCP
    async with TigerGraphMCP() as tg:
        res = await tg.call("tigergraph__run_installed_query", {
            "query_name": "policy_search", "params": {"qv": qv, "k": k, "sources": list(sources)}})
    dist = res["result"][1]["distances"]
    return sorted(dist, key=dist.get)


def _bm25_top(query: str, sources: tuple[str, ...], k: int) -> list[str]:
    ids, bm = _bm25(sources)
    scores = bm.get_scores(_tokens(query))
    return [ids[i] for i in np.argsort(-scores)[:k] if scores[i] > 0]


def search(query: str, sources=POLICY_SOURCES, k: int = 3, use_graph: bool | None = None) -> list[dict]:
    sources = tuple(sources)
    qv = embed_query(query)
    if use_graph is None:
        use_graph = bool(TG_HOST)
    vec = asyncio.run(_vector_graph(qv, sources, CANDIDATES)) if use_graph else _vector_local(qv, sources, CANDIDATES)
    kw = _bm25_top(query, sources, CANDIDATES)

    fused: dict[str, float] = {}
    for ranked in (vec, kw):
        for rank, cid in enumerate(ranked):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    pool = sorted(fused, key=lambda c: -fused[c])[:RERANK_TOP]
    pool = [c for c in pool if c in _chunks()]

    scores = list(_reranker().rerank(query, [f"{_chunks()[c]['title']}. {_chunks()[c]['text']}" for c in pool]))
    out, per_doc = [], {}
    for cid, score in sorted(zip(pool, scores), key=lambda x: -x[1]):
        doc = _chunks()[cid]["section"] if _chunks()[cid]["source"] == "regulation" else cid
        if per_doc.get(doc, 0) >= MAX_PER_DOC:
            continue
        per_doc[doc] = per_doc.get(doc, 0) + 1
        r = _chunks()[cid]
        out.append({**{f: r[f] for f in FIELDS}, "patterns": r["pattern_ids"], "rules": r["rule_ids"],
                    "score": float(score), "via": [n for n, lst in (("vector", vec), ("bm25", kw)) if cid in lst]})
        if len(out) == k:
            break
    return out


def search_policy(query: str, k: int = 3, use_graph: bool | None = None) -> list[dict]:
    return search(query, POLICY_SOURCES, k, use_graph)


def search_regulations(query: str, k: int = 3, use_graph: bool | None = None) -> list[dict]:
    return search(query, REGULATION_SOURCES, k, use_graph)


def get_rule(rule_id: str) -> dict:
    """Exact policy text for a rule ('R2') or section ('s3a')."""
    key = f"policy:{rule_id}" if not rule_id.startswith(("policy:", "pattern:")) else rule_id
    r = _chunks()[key]
    return {f: r[f] for f in FIELDS}
