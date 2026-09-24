"""write_memory node: store the finished case as an AgentCase vertex + edges (case memory write-back).

Attributes and the summary embedding go through the allowlisted `upsert_vectors` MCP tool;
edges go through the installed `link_case` query. Later investigations reach the case by
traversing from its card, transactions, devices, pattern or similar closed cases.
"""

import json

from agent.embed import embed_passages
from agent.tools.graph_tools import GraphTools


def case_vertex_id(case_id: str) -> str:
    return f"AC-{case_id}"


async def write_case(g: GraphTools, answer: dict, case: dict) -> str:
    c = answer["case"]
    vid = case_vertex_id(answer["case_id"])
    emb = embed_passages([f"{c['pattern']} {c['verdict']}. {c['summary']}"])[0]
    attrs = {
        "case_id": answer["case_id"], "card_id": case["card_id"], "customer_id": case["customer_id"],
        "opened_at": case["opened_at"], "trigger_type": case["trigger_type"], "status": c["status"],
        "verdict": c["verdict"], "fraud_probability": c["fraud_probability"], "pattern": c["pattern"],
        "exposure_usd": c["exposure_usd"], "sar_filed": answer["sar"]["file"], "summary": c["summary"],
        "record": json.dumps(answer, default=str),
    }
    g.calls += 1
    await g.tg.call("tigergraph__upsert_vectors", {
        "vertex_type": "AgentCase", "vector_attribute": "summary_emb",
        "vectors": [{"vertex_id": vid, "vector": emb, "attributes": attrs}]})
    await g.query("link_case", case_vid=vid, card_id=case["card_id"], txn_ids=c["affected_txn_ids"],
                  connected_cards=c["connected_card_ids"], similar_cases=c["similar_prior_cases"],
                  patterns=[c["pattern"]] if c["pattern"] != "none" else [],
                  devices=c["connected_device_profiles"])
    return vid
