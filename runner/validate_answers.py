"""Validate cases/*.json against the README Answer Format and the dataset.

    python -m runner.validate_answers
"""

import json
import sys

import pandas as pd

from config.policy import policy, route_for
from config.settings import CASES_DIR, DATA_DIR, ROOT

PATTERNS = {"card_testing", "card_not_present_fraud", "card_not_present_new_device", "out_of_region_use",
            "account_takeover", "undocumented", "none"}
TOP = {"case_id": str, "case": dict, "evidence_requests": list, "next_best_actions": dict, "sar": dict,
       "stop_reason": str, "tool_calls": int, "tokens": int, "latency_s": (int, float)}
CASE = {"status": str, "verdict": str, "fraud_probability": (int, float), "pattern": str, "pattern_description": str,
        "affected_txn_ids": list, "first_suspicious_txn_id": str, "connected_card_ids": list,
        "connected_device_profiles": list, "exposure_usd": (int, float), "evidence": list,
        "similar_prior_cases": list, "summary": str, "written_to_graph": bool, "graph_case_id": str}
SAR = {"file": bool, "reason": str, "narrative": str, "subjects": list, "total_amount_usd": (int, float),
       "activity_dates": list}


def _ids():
    txns, cards = {}, set(pd.read_csv(ROOT / "data/graph/cards.tsv", sep="\t", usecols=["id"]).id)
    for f in sorted((ROOT / "data/graph").glob("transactions_*.tsv")):
        d = pd.read_csv(f, sep="\t", usecols=["id", "amount"], dtype={"id": str})
        txns.update(zip(d.id, d.amount))
    devices = set(pd.read_csv(ROOT / "data/graph/device_profiles.tsv", sep="\t", usecols=["id"], quoting=3).id)
    closed = set(pd.read_csv(DATA_DIR / "closed_cases_history.csv", usecols=["case_id"]).case_id)
    return txns, cards, devices, closed


def check(a: dict, ids) -> list[str]:
    txns, cards, devices, closed = ids
    errs = []
    for k, t in TOP.items():
        if not isinstance(a.get(k), t):
            errs.append(f"top.{k} missing/wrong type")
    c, s, n = a.get("case", {}), a.get("sar", {}), a.get("next_best_actions", {})
    for k, t in CASE.items():
        if not isinstance(c.get(k), t):
            errs.append(f"case.{k} missing/wrong type")
    for k, t in SAR.items():
        if not isinstance(s.get(k), t):
            errs.append(f"sar.{k} missing/wrong type")
    if errs:
        return errs
    if c["status"] not in {"open", "closed_fraud", "closed_legitimate", "escalated"}: errs.append("bad status")
    if c["verdict"] not in {"fraud", "legitimate", "uncertain"}: errs.append("bad verdict")
    if c["pattern"] not in PATTERNS: errs.append("bad pattern")
    if not 0 <= c["fraud_probability"] <= 1: errs.append("probability out of range")
    if c["pattern"] == "undocumented" and not c["pattern_description"]: errs.append("undocumented needs description")
    for t in c["affected_txn_ids"] + ([c["first_suspicious_txn_id"]] if c["first_suspicious_txn_id"] else []):
        if t not in txns: errs.append(f"unknown txn {t}")
    for k in c["connected_card_ids"]:
        if k not in cards: errs.append(f"unknown card {k}")
    for d in c["connected_device_profiles"]:
        if d not in devices: errs.append(f"unknown device {d}")
    for cc in c["similar_prior_cases"]:
        if cc not in closed: errs.append(f"unknown closed case {cc}")
    exp = round(sum(abs(txns[t]) for t in c["affected_txn_ids"] if t in txns), 2)
    if abs(exp - c["exposure_usd"]) > 0.01: errs.append(f"exposure {c['exposure_usd']} != sum {exp}")
    if c["verdict"] == "legitimate" and (c["affected_txn_ids"] or c["exposure_usd"] or s["file"]):
        errs.append("legitimate verdict must have no txns, 0 exposure, no SAR")
    for e in c["evidence"]:
        if set(e) != {"claim", "source", "ref", "entity_ids"} or e["source"] not in {"graph", "document", "customer", "external"}:
            errs.append(f"bad evidence item {e}")
    for r in a["evidence_requests"]:
        if r.get("type") not in {"customer_validation", "step_up_auth", "analyst_info"} or \
                not isinstance(r.get("asked_after_step"), int) or not isinstance(r.get("assumed_response"), str):
            errs.append(f"bad evidence request {r}")
    actions = policy()["actions"]
    for phase in ("initial", "final"):
        for x in n.get(phase, []):
            if x.get("action") not in actions: errs.append(f"{phase}: unknown action {x.get('action')}")
            elif x.get("route") != route_for(x["action"], c["exposure_usd"]):
                errs.append(f"{phase}: {x['action']} route {x.get('route')} != policy {route_for(x['action'], c['exposure_usd'])}")
            if not x.get("reason"): errs.append(f"{phase}: {x.get('action')} missing reason")
    if not isinstance(n.get("what_changed"), str): errs.append("what_changed missing")
    if not a["evidence_requests"] and n.get("initial") != n.get("final"): errs.append("no request but initial != final")
    has_report = any(x["action"] == "FILE_REPORT" for x in n.get("final", []))
    if s["file"] != has_report: errs.append("sar.file disagrees with FILE_REPORT in final")
    if s["file"]:
        if not s["narrative"] or not s["subjects"] or len(s["activity_dates"]) != 2: errs.append("SAR incomplete")
    elif s["narrative"] or s["subjects"] or s["total_amount_usd"] or s["activity_dates"]:
        errs.append("sar.file false but SAR fields not empty")
    if not c["written_to_graph"] or not c["graph_case_id"]: errs.append("case not written to graph")
    return errs


def main() -> int:
    pack = pd.read_csv(DATA_DIR / "case_pack.csv", dtype=str)
    ids = _ids()
    bad = 0
    for cid in pack.case_id:
        f = CASES_DIR / f"{cid}.json"
        if not f.exists():
            print(f"{cid}: MISSING"); bad += 1; continue
        errs = check(json.loads(f.read_text()), ids)
        print(f"{cid}: {'OK' if not errs else 'ERR ' + '; '.join(errs)}")
        bad += bool(errs)
    print(f"\n{len(pack) - bad}/{len(pack)} valid")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
