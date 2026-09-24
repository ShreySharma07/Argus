"""Deterministic confidence + verdict consistency (CLAUDE.md design decision 2).

confidence = w_cov * coverage + w_agr * signal agreement + w_mem * similar-case outcome agreement

The LLM proposes a verdict and probability; this module measures how well the gathered evidence
supports acting on it. The loop only stops on a decisive probability when confidence is high enough.
"""

from functools import lru_cache

import yaml

from config.settings import CONFIG_DIR


@lru_cache
def settings() -> dict:
    return yaml.safe_load(open(CONFIG_DIR / "thresholds.yaml"))


def coverage(brief: dict, replies: list[dict]) -> float:
    base = brief["card_baseline_180d"]
    f = brief["flagged_txn"]
    parts = [
        min(base["n_txns"] / 20, 1.0),                                   # enough history to know "normal"
        1.0 if f["channel"] == "in_person" or f["device"] else 0.3,      # identity record for online txns
        1.0 if brief["memory_similar_cases"]["cases"] or brief.get("memory_agent_cases") else 0.4,
        1.0 if brief.get("region_cluster") or brief["rare_shared_devices"] or f["channel"] == "online" else 0.6,
        1.0 if replies else 0.0,                                         # direct confirmation from a party
    ]
    return round(sum(parts) / len(parts), 3)


def memory_agreement(brief: dict, verdict: str) -> float:
    cases = [c for c in brief["memory_similar_cases"]["cases"]
             if {"same_customer", "shared_device", "connected_card"} & set(c["why"])]
    if not cases or verdict == "uncertain":
        return 0.5
    fraud = sum(c["outcome"] == "confirmed_fraud" for c in cases) / len(cases)
    return round(fraud if verdict == "fraud" else 1 - fraud, 3)


def confidence(brief: dict, assessment, replies: list[dict]) -> dict:
    w = settings()["confidence_weights"]
    cov = coverage(brief, replies)
    agr = min(assessment.independent_signals / 3, 1.0)
    mem = memory_agreement(brief, assessment.verdict)
    score = round(w["coverage"] * cov + w["agreement"] * agr + w["memory"] * mem, 3)
    return {"confidence": score, "coverage": cov, "signal_agreement": round(agr, 3), "memory_agreement": mem}


def consistent_verdict(verdict: str, p: float) -> str:
    s = settings()
    if verdict == "fraud" and p < s["fraud_min_probability"]:
        return "uncertain"
    if verdict == "legitimate" and p > s["legit_max_probability"]:
        return "uncertain"
    return verdict
