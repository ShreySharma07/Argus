"""gather_evidence node: graph queries (via MCP) -> deterministic features + pattern signals.

Everything here is reproducible: no LLM. The output `brief` is the compact,
structured context the LLM reasons over (GraphRAG: pass findings, not rows).
"""

import math
from collections import Counter
from datetime import datetime

from agent.embed import embed_query
from agent.tools.graph_tools import FMT, GraphTools, ts_shift

MISSING = -999
RARE_DEVICE_CARDS = 60        # a device profile seen on more cards than this is too common to link people
EPISODE_BEFORE_H = 72         # candidate episode window around the flagged txn
BASE_FRAUD_CARD_RATE = 0.10   # share of all cards with a confirmed-fraud closed case (computed from history)


def _t(ts: str) -> datetime:
    return datetime.strptime(ts, FMT)


def _hours(a: str, b: str) -> float:
    return (_t(b) - _t(a)).total_seconds() / 3600


def _share(counter: dict, key) -> float:
    total = sum(counter.values())
    return (counter.get(key, 0) / total) if total else 0.0


def _txn_view(t: dict, prof: dict) -> dict:
    """Compact per-transaction row for the brief, with novelty flags vs the card's baseline."""
    mean = prof["total"] / prof["n_txns"] if prof["n_txns"] else 0
    return {
        "id": t["id"], "ts": t["ts"], "amount": round(t["amount"], 2), "channel": t["channel"],
        "product": t["product_cd"], "region": t["addr1"] or None, "country": t["addr2"] or None,
        "risk_score": t["risk_score"], "device": t["device"] or None,
        "device_new_flag": t["id_15"] or None, "proxy": (t["id_23"] or "").replace("IP_PROXY:", "") or None,
        "email": t["p_email"] or None,
        "new_region_for_card": bool(t["addr1"]) and prof["regions"].get(t["addr1"], 0) == 0,
        "new_device_for_card": bool(t["device"]) and t["device"] not in prof["devices"],
        "amount_vs_mean": round(t["amount"] / mean, 2) if mean else None,
        "prior_case": t["cases"] or None,
    }


def card_testing_runs(txns: list[dict]) -> list[dict]:
    """>=3 small (<$10) online auths within 60 min, followed within 2h by a larger purchase (pattern 1 / R5)."""
    online = [t for t in txns if t["channel"] == "online"]
    runs = []
    for i, t in enumerate(online):
        if t["amount"] >= 10:
            continue
        small = [u for u in online[i:] if u["amount"] < 10 and 0 <= _hours(t["ts"], u["ts"]) <= 1]
        if len(small) < 3:
            continue
        big = [u for u in online if u["amount"] >= 10 and 0 < _hours(small[-1]["ts"], u["ts"]) <= 2]
        runs.append({"small": [u["id"] for u in small], "large": [u["id"] for u in big],
                     "large_cleared_over_100": any(u["amount"] > 100 for u in big)})
        break
    return runs


def threshold_runs(txns: list[dict]) -> list[dict]:
    """>=3 online purchases just under $500 within 60 min (undocumented pattern seen in history)."""
    near = [t for t in txns if t["channel"] == "online" and 400 <= t["amount"] < 500]
    for i, t in enumerate(near):
        grp = [u for u in near[i:] if 0 <= _hours(t["ts"], u["ts"]) <= 1]
        if len(grp) >= 3:
            return [{"txns": [u["id"] for u in grp], "amounts": [u["amount"] for u in grp]}]
    return []


def recurring_matches(flagged: dict, history: list[dict]) -> dict:
    """Prior charges with the same product and ~same amount on distinct months (policy R7)."""
    same = [h for h in history if h["id"] != flagged["id"] and h["product_cd"] == flagged["product_cd"]
            and abs(h["amount"] - flagged["amount"]) <= max(1.0, 0.01 * flagged["amount"])
            and h["ts"] < flagged["ts"]]
    months = sorted({h["ts"][:7] for h in same})
    gaps = [round(_hours(a["ts"], b["ts"]) / 24) for a, b in zip(same, same[1:])]
    return {"n_prior_same_amount": len(same), "distinct_months": months,
            "prior_txn_ids": [h["id"] for h in same][-6:], "day_gaps": gaps[-6:],
            "looks_monthly": len(months) >= 2 and any(25 <= g <= 35 for g in gaps)}


async def gather(g: GraphTools, case: dict) -> dict:
    """Run the investigation queries for one case. Returns raw evidence keyed by source."""
    opened, card = case["opened_at"], case["card_id"]
    act = await g.card_activity(card, ts_shift(opened, days=-7), opened)
    flagged = next((a for a in act if a["id"] == case["flagged_txn_id"]), None)
    if flagged is None:
        act = await g.card_activity(card, ts_shift(opened, days=-30), opened)
        flagged = next((a for a in act if a["id"] == case["flagged_txn_id"]), None)
    if flagged is None:
        raise RuntimeError(f"flagged txn {case['flagged_txn_id']} not found on {card}")
    fts = flagged["ts"]

    ev = {"flagged": flagged, "activity": act}
    ev["profile"] = await g.card_profile(card, fts)
    ev["shared"] = await g.shared_devices(card, ts_shift(fts, days=-30), opened)
    ev["similar"] = await g.similar_cases(card, opened, ts_shift(fts, days=-30))
    ev["agent_memory"] = await g.agent_case_memory(card, opened, ts_shift(fts, days=-30))
    if flagged["addr1"]:
        ev["region"] = await g.region_newcomers(flagged["addr1"], ts_shift(fts, days=-7), opened)
    if case["trigger_type"] == "customer_report":
        # Longer history only for disputes: needed to recognise a recurring charge (R7).
        ev["history"] = await g.card_activity(card, ts_shift(fts, days=-150), ts_shift(fts, days=-7))
    return ev


def features(case: dict, ev: dict) -> dict:
    """Deterministic signals + a compact brief for the LLM."""
    f, prof, act = ev["flagged"], ev["profile"], ev["activity"]
    n = prof["n_txns"]
    mean = prof["total"] / n if n else 0.0
    std = math.sqrt(max(prof["sum_sq"] / n - mean ** 2, 0)) if n else 0.0
    episode = [a for a in act if -EPISODE_BEFORE_H <= _hours(f["ts"], a["ts"]) and a["ts"] <= case["opened_at"]
               and _hours(a["ts"], f["ts"]) <= EPISODE_BEFORE_H]
    home_regions = {r for r, c in prof["regions"].items() if c >= 3}

    # Out-of-region: is normal activity continuing at home while the new region is used?
    new_region_txns = [a for a in episode if a["channel"] == "in_person" and a["addr1"]
                       and prof["regions"].get(a["addr1"], 0) == 0]
    home_during = [a for a in episode if a["addr1"] in home_regions
                   and abs(_hours(f["ts"], a["ts"])) <= 48]
    region_days = sorted({a["ts"][:10] for a in act if a["addr1"] == f["addr1"] and f["addr1"]})

    # Devices: only rare profiles can link people.
    rare_devs = [d for d in ev["shared"]["devices"] if d["cards_all_time"] <= RARE_DEVICE_CARDS]
    rare_ids = {d["id"] for d in rare_devs}
    linked_cards = [o for o in ev["shared"]["other_cards"] if set(o["devices"]) & rare_ids]
    linked_fraud = [o for o in linked_cards if o["fraud_cases"]]

    sim = ev["similar"]
    sim_counts = Counter((s["outcome"], s["pattern"]) for s in sim)
    undocumented_links = [s for s in sim if s["pattern"] == "undocumented"]

    region = ev.get("region")
    region_info = None
    if region:
        nc = region["newcomers"]
        fraud_nc = [x for x in nc if x["fraud_cases"]]
        region_info = {"region": f["addr1"], "active_cards_7d": region["active_cards"], "newcomer_cards_7d": len(nc),
                       "newcomers_with_confirmed_fraud_history": len(fraud_nc),
                       "fraud_history_rate_among_newcomers": round(len(fraud_nc) / len(nc), 2) if nc else 0.0,
                       "base_rate_all_cards": BASE_FRAUD_CARD_RATE,
                       "newcomer_card_ids_with_fraud": [x["id"] for x in fraud_nc][:10]}

    sig = {
        "amount_z": round((f["amount"] - mean) / std, 2) if std else None,
        "amount_above_card_max": n > 0 and f["amount"] > prof["max_amount"],
        "channel_share_in_history": round(_share(prof["channels"], f["channel"]), 3),
        "product_share_in_history": round(_share(prof["products"], f["product_cd"]), 3),
        "region_txns_in_history": prof["regions"].get(f["addr1"], 0) if f["addr1"] else None,
        "new_region_in_person_txns": [a["id"] for a in new_region_txns],
        "home_activity_within_48h": len(home_during),
        "days_card_used_in_flagged_region_7d": region_days,
        "device_in_card_history": bool(f["device"]) and f["device"] in prof["devices"],
        "device_new_flag": f["id_15"] or None,
        "proxy": f["id_23"] or None,
        "card_testing_runs": card_testing_runs(episode),
        "just_under_500_runs": threshold_runs(episode),
        "online_txns_in_episode": sum(a["channel"] == "online" for a in episode),
        "customer_other_cards": [c["id"] for c in prof["customer_cards"] if c["id"] != case["card_id"]],
    }
    if "history" in ev:
        sig["recurring"] = recurring_matches(f, ev["history"] + [a for a in act if a["ts"] < f["ts"]])

    brief = {
        "case": {k: case[k] for k in ("case_id", "opened_at", "trigger_type", "trigger_text", "flagged_txn_id",
                                      "card_id", "customer_id", "risk_score")},
        "card_baseline_180d": {
            "n_txns": n, "mean_amount": round(mean, 2), "std_amount": round(std, 2),
            "max_amount": prof["max_amount"], "first_ts": prof["first_ts"] if n else None,
            "channels": prof["channels"], "products": prof["products"],
            "top_regions": dict(Counter(prof["regions"]).most_common(6)), "countries": prof["countries"],
            "n_devices": len(prof["devices"]), "top_devices": dict(Counter(prof["devices"]).most_common(4)),
        },
        "flagged_txn": _txn_view(f, prof),
        "episode_window_txns": [_txn_view(a, prof) for a in episode][:40],
        "signals": sig,
        "rare_shared_devices": [{"device": d["id"], "cards_all_time": d["cards_all_time"],
                                 "cards_in_window": d["cards_in_window"]}
                                for d in sorted(rare_devs, key=lambda d: -d["cards_in_window"])][:15],
        "rare_shared_devices_total": len(rare_devs),
        "cards_linked_by_rare_device": [{"card": o["id"], "txns": o["n_txns"], "amount": round(o["amount"], 2),
                                         "devices": o["devices"], "confirmed_fraud_cases": o["fraud_cases"]}
                                        for o in linked_cards][:15],
        "region_cluster": region_info,
        "memory_agent_cases": [{"case_id": m["case_id"], "card": m["card_id"], "opened_at": m["opened_at"],
                                "verdict": m["verdict"], "probability": m["fraud_probability"], "pattern": m["pattern"],
                                "why": m["why"], "summary": m["summary"][:260]} for m in ev.get("agent_memory", [])][:5],
        "memory_similar_cases": {
            "counts_by_outcome_pattern": {f"{o}/{p}": c for (o, p), c in sim_counts.most_common()},
            "cases": [{"id": s["id"], "card": s["card_id"], "outcome": s["outcome"], "pattern": s["pattern"],
                       "why": s["why"], "exposure": s["exposure_usd"], "actions": s["actions_taken"],
                       "notes": s["analyst_notes"][:260]}
                      for s in (undocumented_links + [s for s in sim if s not in undocumented_links])][:12],
        },
    }
    return {"brief": brief, "signals": sig,
            "linked_fraud_cards": [o["id"] for o in linked_fraud], "rare_devices": sorted(rare_ids),
            "episode_ids": [a["id"] for a in episode], "episode_amounts": {a["id"]: a["amount"] for a in episode},
            "episode_ts": {a["id"]: a["ts"] for a in episode},
            "similar_ids": [s["id"] for s in sim]}


async def vector_memory(g: GraphTools, brief: dict) -> list[dict]:
    """Semantic case memory: closed cases whose notes read like this alert (secondary signal)."""
    f = brief["flagged_txn"]
    text = (f"{brief['case']['trigger_text']} {f['channel']} product {f['product']} "
            f"{'new device ' if f['new_device_for_card'] else ''}{'proxy ' + f['proxy'] if f['proxy'] else ''} "
            f"{'new billing region' if f['new_region_for_card'] else ''}")
    hits = await g.case_vector_search(embed_query(text), k=5)
    return [{"id": h["id"], "outcome": h["outcome"], "pattern": h["pattern"], "similarity": round(h["similarity"], 3),
             "notes": h["analyst_notes"][:200]} for h in hits]
