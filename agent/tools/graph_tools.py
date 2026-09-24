"""Typed wrappers over the installed GSQL queries, sharing one MCP session.

Every call goes through the allowlisted TigerGraphMCP client and is counted,
so the answer file's `tool_calls` is the real number of graph/retrieval calls.
"""

from datetime import datetime, timedelta
from typing import Any

from agent.tools.mcp_client import TigerGraphMCP

FMT = "%Y-%m-%d %H:%M:%S"


def ts_shift(ts: str, days: float = 0, hours: float = 0) -> str:
    return (datetime.strptime(ts, FMT) + timedelta(days=days, hours=hours)).strftime(FMT)


def _rows(items: list[dict], prefix: str) -> list[dict]:
    """Flatten TigerGraph vertex rows: {'v_id', 'attributes': {'T.amount': ..}} -> {'id', 'amount', ..}."""
    out = []
    for it in items:
        row = {"id": it["v_id"]}
        for k, v in it["attributes"].items():
            key = k[len(prefix):] if k.startswith(prefix) else k
            row[key.lstrip("@")] = v
        out.append(row)
    return out


class GraphTools:
    def __init__(self, tg: TigerGraphMCP):
        self.tg = tg
        self.calls = 0
        self.log: list[dict] = []

    async def query(self, name: str, **params) -> list[dict]:
        self.calls += 1
        res = await self.tg.call("tigergraph__run_installed_query", {"query_name": name, "params": params})
        self.log.append({"query": name, "params": {k: v for k, v in params.items() if k != "qv"}})
        return res["result"]

    async def card_profile(self, card: str, as_of: str, lookback_days: int = 180) -> dict:
        r = await self.query("card_profile", card=card, as_of=as_of, lookback_days=lookback_days)
        prof = r[0]
        prof["customer_cards"] = _rows(r[1]["customer_cards"], "cards.")
        return prof

    async def card_activity(self, card: str, start_ts: str, end_ts: str, max_rows: int = 1000) -> list[dict]:
        r = await self.query("card_activity", card=card, start_ts=start_ts, end_ts=end_ts, max_rows=max_rows)
        return _rows(r[0]["txns"], "T.")

    async def shared_devices(self, card: str, start_ts: str, end_ts: str) -> dict:
        r = await self.query("shared_devices", card=card, start_ts=start_ts, end_ts=end_ts)
        return {"devices": _rows(r[0]["devices"], "D."), "other_cards": _rows(r[1]["other_cards"], "WC.")}

    async def region_newcomers(self, region: str, start_ts: str, end_ts: str) -> dict:
        r = await self.query("region_newcomers", region=region, start_ts=start_ts, end_ts=end_ts)
        return {"active_cards": r[0]["active_cards"], "newcomers": _rows(r[1]["newcomers"], "N.")}

    async def similar_cases(self, card: str, as_of: str, device_since: str) -> list[dict]:
        r = await self.query("similar_cases", card=card, as_of=as_of, device_since=device_since)
        return _rows(r[0]["cases"], "A.")

    async def case_vector_search(self, qv: list[float], k: int = 5) -> list[dict]:
        r = await self.query("case_vector_search", qv=qv, k=k)
        dist = r[1]["distances"]
        rows = _rows(r[0]["cases"], "hits.")
        for row in rows:
            row["similarity"] = 1.0 - float(dist.get(row["id"], 1.0))
        return sorted(rows, key=lambda x: -x["similarity"])

    async def upsert(self, query: str, **params) -> Any:
        return await self.query(query, **params)
