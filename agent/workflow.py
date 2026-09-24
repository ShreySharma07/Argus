"""Investigation workflow for one case.

triage -> gather_evidence -> retrieve (GraphRAG) -> assess (LLM, round 1)
       -> [uncertain?] request_evidence -> assess (round n) ... until a stop criterion holds
       -> decide + policy_gate -> explain (SAR) -> write_memory

Stop criteria (policy §6 + config/thresholds.yaml), checked after every assessment:
  1. decisive: p >= 0.85 or <= 0.15 with >= 2 independent signals and evidence confidence >= threshold
  2. a verification reply settled the question (customer confirms/denies, analyst confirms/clears)
  3. the assessor asks for nothing further (further steps unlikely to change the decision)
  4. no policy-approved evidence action left, or max_evidence_rounds reached

Every node appends to the case timeline. The answer dict follows the README Answer Format.
"""

import asyncio
import time
from datetime import datetime, timezone

from agent import llm
from agent.assess import assess, policy_context
from agent.decide import plan
from agent.evidence import features, gather, vector_memory
from agent.explain import draft_sar
from agent.memory import write_case
from agent.rag import REGULATION_SOURCES, asearch, get_rule
from agent.scoring import confidence, consistent_verdict, settings
from agent.tools.evidence_sources import simulate
from agent.tools.graph_tools import GraphTools

PATTERN_QUERY = {
    "risk_score": "model risk score alert: verify before blocking on a single weak signal",
    "customer_report": "customer denies the transaction; disputed charge; recurring charge",
    "analyst_request": "several cards share the same unusual device profile; shared origin ring; undocumented pattern",
}
ALWAYS_RULES = ["R1", "R2", "R3", "R4", "R6", "R8", "R9", "s3a", "s5", "s6"]
SETTLING = {"denies", "confirms", "analyst_confirms_fraud", "analyst_clears"}


class Timeline:
    def __init__(self):
        self.events: list[dict] = []

    def add(self, node: str, detail: str) -> None:
        self.events.append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "node": node,
                            "detail": detail})


def _clean_ids(ids, allowed: set) -> list[str]:
    seen, out = set(), []
    for i in ids:
        i = str(i).strip()
        if i in allowed and i not in seen:
            seen.add(i)
            out.append(i)
    return out


async def run_case(g: GraphTools, case: dict) -> tuple[dict, list[dict]]:
    t0 = time.time()
    usage = llm.Usage()
    tl = Timeline()
    tl.add("triage", f"{case['trigger_type']} on {case['card_id']}, flagged txn {case['flagged_txn_id']}")

    ev = await gather(g, case)
    fx = features(case, ev)
    brief = fx["brief"]
    tl.add("gather_evidence", f"{g.calls} graph calls; {len(fx['episode_ids'])} txns in episode window, "
                              f"{len(ev['similar'])} memory cases, {len(fx['rare_devices'])} rare devices")

    mem_vec = await vector_memory(g, brief)
    hits = await asearch(g, PATTERN_QUERY[case["trigger_type"]] + ". " + brief["flagged_txn"]["channel"])
    rules = [get_rule(r) for r in ALWAYS_RULES] + \
            [get_rule(f"pattern:{p}") for p in ("card_testing", "card_not_present_fraud", "card_not_present_new_device",
                                                "out_of_region_use", "account_takeover")]
    if case["trigger_type"] == "customer_report":
        rules.append(get_rule("R7"))
    if brief["signals"]["card_testing_runs"]:
        rules.append(get_rule("R5"))
    tl.add("retrieve", f"policy: {[h['id'] for h in hits]} + rules {ALWAYS_RULES}; vector memory {[m['id'] for m in mem_vec]}")

    policy_text = policy_context(hits, rules)

    async def _assess(received=None, previous=None):
        a = await asyncio.to_thread(assess, brief, mem_vec, policy_text, usage, received, previous)
        fixed = consistent_verdict(a.verdict, a.probability)
        if fixed != a.verdict:
            tl.add("assess", f"verdict {a.verdict} inconsistent with p={a.probability:.2f}; downgraded to {fixed}")
            a.verdict = fixed
        return a

    a1 = await _assess()
    conf = confidence(brief, a1, [])
    tl.add("assess", f"round 1: {a1.verdict} p={a1.probability:.2f} pattern={a1.pattern} "
                     f"signals={a1.independent_signals} confidence={conf['confidence']} {conf}")

    replies: list[dict] = []
    a, stop = a1, ""
    max_rounds = settings()["max_evidence_rounds"]
    while True:
        conf = confidence(brief, a, replies)
        decisive = (a.probability >= 0.85 or a.probability <= 0.15) and a.independent_signals >= 2
        if decisive and conf["confidence"] >= settings()["confidence_threshold"]:
            stop = (f"Decisive: p={a.probability:.2f} with {a.independent_signals} independent signals and evidence "
                    f"confidence {conf['confidence']:.2f} (policy §6).")
            break
        if replies and replies[-1]["outcome"] in SETTLING:
            stop = f"Verification settled the question: {replies[-1]['type']} -> {replies[-1]['outcome']} (policy §6)."
            break
        asked = {r["type"] for r in replies}
        kind = a.evidence_type if a.request_evidence and a.evidence_type != "none" else None
        if kind in asked:
            kind = "analyst_info" if "analyst_info" not in asked else None
        if kind is None:
            stop = ("Further evidence unlikely to change the decision; no new policy-approved request remains "
                    f"(p={a.probability:.2f}, confidence {conf['confidence']:.2f}; policy §6).")
            break
        if len(replies) >= max_rounds:
            stop = f"Evidence budget reached ({max_rounds} policy-approved requests); deciding on the evidence gathered."
            break
        step = len(tl.events) + 1
        tl.add("request_evidence", f"{kind}: {a.evidence_question or a.evidence_reason}")
        reply = await asyncio.to_thread(simulate, kind, brief, a.evidence_question or a.evidence_reason, usage)
        replies.append({"type": kind, "asked_after_step": step, "outcome": reply.outcome, "text": reply.text})
        tl.add("evidence_received", f"{kind} -> {reply.outcome}: {reply.text}")
        a = await _assess([{"type": r["type"], "reply": r["text"], "outcome": r["outcome"]} for r in replies], a)
        conf = confidence(brief, a, replies)
        tl.add("assess", f"round {len(replies) + 1}: {a.verdict} p={a.probability:.2f} pattern={a.pattern} "
                         f"confidence={conf['confidence']}")
    tl.add("stop", stop)

    # Validate every ID the LLM returned against what the graph actually showed it.
    ep_ids = set(fx["episode_ids"])
    brief_cards = {c["card"] for c in brief["cards_linked_by_rare_device"]} | \
                  set((brief.get("region_cluster") or {}).get("newcomer_card_ids_with_fraud", [])) | \
                  set(brief["signals"]["customer_other_cards"]) | {s["card"] for s in brief["memory_similar_cases"]["cases"]}
    brief_cards.discard(case["card_id"])
    mem_ids = set(fx["similar_ids"]) | {m["id"] for m in mem_vec}
    devices = set(fx["rare_devices"]) | ({brief["flagged_txn"]["device"]} if brief["flagged_txn"]["device"] else set())

    verdict_final = a.verdict
    a.affected_txn_ids = _clean_ids(a.affected_txn_ids, ep_ids) if verdict_final != "legitimate" else []
    if a.affected_txn_ids and case["flagged_txn_id"] not in a.affected_txn_ids and verdict_final == "fraud":
        a.affected_txn_ids.append(case["flagged_txn_id"])
    a.affected_txn_ids.sort(key=lambda i: fx["episode_ts"].get(i, ""))
    a.connected_card_ids = _clean_ids(a.connected_card_ids, brief_cards)
    a.connected_device_profiles = _clean_ids(a.connected_device_profiles, devices)
    a.similar_prior_cases = _clean_ids(a.similar_prior_cases, mem_ids)
    first = a.first_suspicious_txn_id if a.first_suspicious_txn_id in a.affected_txn_ids else \
        (a.affected_txn_ids[0] if a.affected_txn_ids else "")
    exposure = round(sum(abs(fx["episode_amounts"][i]) for i in a.affected_txn_ids), 2)
    linked = bool(fx["linked_fraud_cards"]) and bool(a.connected_card_ids)

    p = plan(a1, a, case["trigger_type"], exposure, brief["signals"], linked, replies)
    tl.add("decide", f"final: {p.verdict} p={p.probability:.2f}; initial {[x['action'] for x in p.initial]} -> "
                     f"final {[x['action'] for x in p.final]}")
    tl.add("policy_gate", "executed (auto): " + ", ".join(x["action"] for x in p.final if x["route"] == "auto") +
           " | awaiting approval: " + ", ".join(f"{x['action']}({x['route']})" for x in p.final if x["route"] != "auto"))

    known = ep_ids | brief_cards | mem_ids | devices | {case["card_id"], case["customer_id"], case["flagged_txn_id"]}
    evidence = []
    for e in a.evidence:
        evidence.append({"claim": e.claim, "source": e.source, "ref": e.ref,
                         "entity_ids": [i for i in e.entity_ids if i in known]})

    answer = {
        "case_id": case["case_id"],
        "case": {
            "status": p.status, "verdict": p.verdict, "fraud_probability": p.probability,
            "pattern": a.pattern if p.verdict != "legitimate" else "none",
            "pattern_description": a.pattern_description if a.pattern == "undocumented" and p.verdict != "legitimate" else "",
            "affected_txn_ids": a.affected_txn_ids if p.verdict != "legitimate" else [],
            "first_suspicious_txn_id": first if p.verdict != "legitimate" else "",
            "connected_card_ids": a.connected_card_ids,
            "connected_device_profiles": a.connected_device_profiles,
            "exposure_usd": exposure if p.verdict != "legitimate" else 0,
            "evidence": evidence,
            "similar_prior_cases": a.similar_prior_cases,
            "summary": a.summary,
            "written_to_graph": False,
            "graph_case_id": "",
        },
        "evidence_requests": p.evidence_requests,
        "next_best_actions": {"initial": p.initial, "final": p.final,
                              "what_changed": a.what_changed if p.evidence_requests else "nothing"},
        "sar": {"file": p.sar_file, "reason": p.sar_reason, "narrative": "", "subjects": [],
                "total_amount_usd": 0, "activity_dates": []},
        "stop_reason": f"{stop} {a.stop_reason}".strip(),
        "tool_calls": 0, "tokens": 0, "latency_s": 0.0,
    }

    if p.sar_file:
        guidance = await asearch(g, "how to write a complete SAR narrative: who what when where why how",
                                 REGULATION_SOURCES, k=3)
        draft = await asyncio.to_thread(draft_sar, {k: answer[k] for k in ("case_id", "case", "evidence_requests", "next_best_actions")} |
                          {"customer_id": case["customer_id"], "card_id": case["card_id"],
                           "txn_times": {i: fx["episode_ts"][i] for i in a.affected_txn_ids}}, guidance, usage)
        dates = sorted(fx["episode_ts"][i][:10] for i in a.affected_txn_ids) or [case["opened_at"][:10]]
        answer["sar"].update({
            "narrative": draft.narrative,
            # README: subjects are customers, cards, merchants and devices (not txn or case IDs)
            "subjects": _clean_ids(draft.subjects, ({case["card_id"], case["customer_id"]} | brief_cards | devices)
                                   ) or [case["customer_id"], case["card_id"]],
            "total_amount_usd": exposure, "activity_dates": [dates[0], dates[-1]],
        })
        tl.add("explain", f"SAR drafted from guidance {[x['id'] for x in guidance]}")

    answer["case"]["written_to_graph"] = True
    answer["case"]["graph_case_id"] = f"AC-{case['case_id']}"
    answer["tool_calls"] = g.calls + 2  # + the two write-back calls below
    answer["tokens"] = usage.tokens
    answer["latency_s"] = round(time.time() - t0, 1)
    await write_case(g, answer, case)
    tl.add("write_memory", f"AgentCase {answer['case']['graph_case_id']} + edges written")
    return answer, tl.events + [{"rationale": a.rationale}]
