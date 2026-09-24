"""M3 check: run every installed query through the allowlisted MCP client for sample cases.

    .venv/bin/python -m scripts.check_queries HHG-001 HHG-010 HHG-014
"""

import asyncio
import sys
from datetime import datetime, timedelta

import pandas as pd

from agent.embed import embed_query
from agent.tools.mcp_client import TigerGraphMCP
from config.settings import DATA_DIR

FMT = "%Y-%m-%d %H:%M:%S"


async def run(tg, query, **params):
    res = await tg.call("tigergraph__run_installed_query", {"query_name": query, "params": params})
    return res["result"]


async def check(tg, case) -> None:
    card, as_of = case.card_id, case.opened_at
    t0 = datetime.strptime(as_of, FMT)
    win = lambda days: (t0 - timedelta(days=days)).strftime(FMT)
    print(f"\n=== {case.case_id}  {case.trigger_type}  card {card}  txn {case.flagged_txn_id}")

    prof = (await run(tg, "card_profile", card=card, as_of=as_of))[0]
    top = lambda m: sorted(m.items(), key=lambda kv: -kv[1])[:3]
    print(f"card_profile: {prof['n_txns']} txns before alert, max ${prof['max_amount']:.2f}, "
          f"channels {prof['channels']}, top regions {top(prof['regions'])}, devices {len(prof['devices'])}")

    acts = (await run(tg, "card_activity", card=card, start_ts=win(3), end_ts=as_of))[0]["txns"]
    flagged = [a["attributes"] for a in acts if a["v_id"] == str(case.flagged_txn_id)]
    print(f"card_activity (72h): {len(acts)} txns; flagged present: {bool(flagged)}")
    if flagged:
        f = flagged[0]
        print(f"   flagged: ${f['T.amount']} {f['T.channel']} {f['T.product_cd']} region {f['T.addr1']} "
              f"device {f['T.@device'] or '-'} id_15={f['T.id_15'] or '-'} risk {f['T.risk_score']}")

    sd = await run(tg, "shared_devices", card=card, start_ts=win(30), end_ts=as_of)
    devs, others = sd[0]["devices"], sd[1]["other_cards"]
    print(f"shared_devices (30d): {len(devs)} device(s), {len(others)} other card(s); "
          f"with fraud history: {sum(bool(o['attributes']['fraud_cases']) for o in others)}")
    for d in devs[:3]:
        a = d["attributes"]
        print(f"   {d['v_id'][:70]}  all-time cards {a['cards_all_time']}, in window {a['cards_in_window']}")

    if flagged and flagged[0]["T.addr1"]:
        rn = await run(tg, "region_newcomers", region=flagged[0]["T.addr1"], start_ts=win(7), end_ts=as_of)
        print(f"region_newcomers ({flagged[0]['T.addr1']}, 7d): {len(rn[1]['newcomers'])} newcomer cards "
              f"of {rn[0]['active_cards']} active")

    sc = (await run(tg, "similar_cases", card=card, as_of=as_of, device_since=win(60)))[0]["cases"]
    print(f"similar_cases: {len(sc)} closed case(s)")
    for c in sc[:4]:
        a = c["attributes"]
        print(f"   {c['v_id']} {a['A.outcome']:15} {a['A.pattern']:28} why={a['why']}")

    qv = embed_query(f"{case.trigger_text}")
    vs = (await run(tg, "case_vector_search", qv=qv, k=5))[0]["cases"]
    print(f"case_vector_search: {[(c['v_id'], c['attributes']['hits.pattern']) for c in vs]}")


async def main(ids) -> None:
    pack = pd.read_csv(DATA_DIR / "case_pack.csv", dtype=str).set_index("case_id", drop=False)
    async with TigerGraphMCP() as tg:
        for cid in ids:
            await check(tg, pack.loc[cid])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["HHG-001", "HHG-010", "HHG-014"]))
