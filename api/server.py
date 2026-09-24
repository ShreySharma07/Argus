"""Analyst API for the Argus frontend.

    .venv/bin/uvicorn api.server:app --port 8000

Serves the investigation record (cases/*.json + runs/*.timeline.json), per-case and
cross-case graphs built from TigerGraph, the Fraud Policy, and the mock action API
behind the approval gate. Read-only against the graph; the only write is the action log.
"""

import json
from functools import lru_cache

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.tools import actions
from config.policy import policy
from config.settings import CASES_DIR, DATA_DIR, ROOT

RUNS = ROOT / "runs"
app = FastAPI(title="Argus analyst API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------- data access

@lru_cache
def pack() -> dict[str, dict]:
    df = pd.read_csv(DATA_DIR / "case_pack.csv", dtype=str).fillna("")
    return {r["case_id"]: r for r in df.to_dict("records")}


def answer(case_id: str) -> dict:
    f = CASES_DIR / f"{case_id}.json"
    if not f.exists():
        raise HTTPException(404, f"no answer file for {case_id}")
    return json.loads(f.read_text())


def timeline(case_id: str) -> list[dict]:
    f = RUNS / f"{case_id}.timeline.json"
    return json.loads(f.read_text()) if f.exists() else []


@lru_cache
def tg():
    from graph.tg import connect
    return connect()


def _vertices(vtype: str, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    try:
        return {v["v_id"]: v["attributes"] for v in tg().getVerticesById(vtype, ids)}
    except Exception:
        return {}


def _edges(vtype: str, vid: str, etype: str) -> list[str]:
    try:
        return [e["to_id"] for e in tg().getEdges(vtype, vid, etype)]
    except Exception:
        return []


def _pending(a: dict) -> list[dict]:
    done = {r["action"] for r in actions.history(a["case_id"]) if r["status"] == "executed"}
    return [x for x in a["next_best_actions"]["final"] if x["route"] != "auto" and x["action"] not in done]


def _probability_path(tl: list[dict]) -> list[dict]:
    """[{round, verdict, p}] parsed from the assess events on the timeline."""
    out = []
    for e in tl:
        d = e.get("detail", "")
        if e.get("node") == "assess" and " p=" in d:
            head = d.split(":", 1)[0] if d.startswith("round") else "round 1"
            body = d.split(": ", 1)[-1]
            try:
                verdict = body.split()[0]
                p = float(body.split("p=")[1].split()[0].rstrip(";"))
            except (IndexError, ValueError):
                continue
            conf = None
            if "confidence=" in d:
                try:
                    conf = float(d.split("confidence=")[1].split()[0].rstrip(",{"))
                except ValueError:
                    pass
            out.append({"round": head, "verdict": verdict, "p": p, "confidence": conf})
    return out


def row(case_id: str) -> dict:
    a, c, meta = answer(case_id), answer(case_id)["case"], pack()[case_id]
    return {
        "case_id": case_id, "opened_at": meta["opened_at"], "trigger_type": meta["trigger_type"],
        "trigger_text": meta["trigger_text"], "card_id": meta["card_id"], "customer_id": meta["customer_id"],
        "flagged_txn_id": meta["flagged_txn_id"],
        "risk_score": float(meta["risk_score"]) if meta["risk_score"] else None,
        "verdict": c["verdict"], "fraud_probability": c["fraud_probability"], "pattern": c["pattern"],
        "status": c["status"], "exposure_usd": c["exposure_usd"], "sar": a["sar"]["file"],
        "pending_approvals": len(_pending(a)), "evidence_requests": len(a["evidence_requests"]),
        "tool_calls": a["tool_calls"], "tokens": a["tokens"], "latency_s": a["latency_s"],
    }


# ---------------------------------------------------------------- endpoints

@app.get("/api/cases")
def list_cases() -> list[dict]:
    return sorted((row(cid) for cid in pack() if (CASES_DIR / f"{cid}.json").exists()),
                  key=lambda r: r["case_id"])


@app.get("/api/stats")
def stats() -> dict:
    rows = list_cases()
    by = lambda k: {v: sum(r[k] == v for r in rows) for v in sorted({r[k] for r in rows})}
    return {
        "cases": len(rows), "verdicts": by("verdict"), "patterns": by("pattern"), "status": by("status"),
        "sars": sum(r["sar"] for r in rows), "exposure_usd": round(sum(r["exposure_usd"] for r in rows), 2),
        "pending_approvals": sum(r["pending_approvals"] for r in rows),
        "evidence_requests": sum(r["evidence_requests"] for r in rows),
        "avg_latency_s": round(sum(r["latency_s"] for r in rows) / max(len(rows), 1), 1),
    }


@app.get("/api/cases/{case_id}")
def case_detail(case_id: str) -> dict:
    if case_id not in pack():
        raise HTTPException(404, case_id)
    a, tl = answer(case_id), timeline(case_id)
    meta = pack()[case_id]
    txn_ids = list(dict.fromkeys([meta["flagged_txn_id"]] + a["case"]["affected_txn_ids"]))
    txns = _vertices("Transaction", txn_ids)
    closed = _vertices("ClosedCase", a["case"]["similar_prior_cases"])
    return {
        "row": row(case_id), "answer": a,
        "timeline": [e for e in tl if "node" in e],
        "rationale": next((e["rationale"] for e in tl if "rationale" in e), ""),
        "probability_path": _probability_path(tl),
        "transactions": [{"id": t, **{k: txns.get(t, {}).get(k) for k in
                                     ("ts", "amount", "channel", "product_cd", "addr1", "risk_score", "id_15", "id_23")}}
                         for t in txn_ids],
        "similar_cases": [{"id": cid, **{k: closed.get(cid, {}).get(k) for k in
                                         ("outcome", "pattern", "exposure_usd", "analyst_notes", "card_id")}}
                          for cid in a["case"]["similar_prior_cases"]],
        "actions_log": actions.history(case_id),
        "pending": _pending(a),
    }


class ActionRequest(BaseModel):
    action: str
    role: str


@app.post("/api/cases/{case_id}/actions")
def run_action(case_id: str, req: ActionRequest) -> dict:
    try:
        return actions.execute(answer(case_id), pack()[case_id], req.action, req.role)
    except actions.NotAuthorized as e:
        raise HTTPException(403, str(e))


@app.get("/api/policy")
def get_policy() -> dict:
    pol = policy()
    rules = []
    try:
        chunks = tg().getVertices("PolicyChunk", where='source="policy"', limit=200)
        rules = sorted(({"id": v["v_id"], "section": v["attributes"]["section"], "title": v["attributes"]["title"],
                         "text": v["attributes"]["text"]} for v in chunks), key=lambda r: _rule_order(r["id"]))
    except Exception:
        pass
    return {"version": pol["version"], "actions": pol["actions"], "thresholds": pol["thresholds"], "rules": rules}


def _rule_order(cid: str):
    tail = cid.split(":", 1)[1]
    if tail.startswith("R"):
        return (1, int(tail[1:]), "")
    return (0 if tail < "s3" else 2, 0, tail)


# ---------------------------------------------------------------- graphs

def _node(nodes: dict, nid: str, kind: str, label: str, **props) -> None:
    if nid not in nodes:
        nodes[nid] = {"id": nid, "kind": kind, "label": label, "props": props}


def _edge(edges: list, s: str, t: str, label: str) -> None:
    if s != t and not any(e["source"] == s and e["target"] == t for e in edges):
        edges.append({"source": s, "target": t, "label": label})


@app.get("/api/graph/{case_id}")
def case_graph(case_id: str) -> dict:
    """The case's neighbourhood: case, customer, card, episode txns with their devices and regions,
    connected cards, memory cases and the pattern."""
    a, meta = answer(case_id), pack()[case_id]
    c = a["case"]
    nodes: dict = {}
    edges: list = []
    cid = c["graph_case_id"] or case_id
    _node(nodes, cid, "case", case_id, verdict=c["verdict"], p=c["fraud_probability"], status=c["status"])
    _node(nodes, meta["customer_id"], "customer", meta["customer_id"])
    _node(nodes, meta["card_id"], "card", meta["card_id"], subject=True)
    _edge(edges, meta["customer_id"], meta["card_id"], "OWNS")
    _edge(edges, cid, meta["card_id"], "ON_CARD")
    if c["pattern"] != "none":
        _node(nodes, f"pattern:{c['pattern']}", "pattern", c["pattern"].replace("_", " "))
        _edge(edges, cid, f"pattern:{c['pattern']}", "MATCHES")

    txn_ids = list(dict.fromkeys([meta["flagged_txn_id"]] + c["affected_txn_ids"]))
    txns = _vertices("Transaction", txn_ids)
    for t in txn_ids:
        v = txns.get(t, {})
        _node(nodes, t, "txn", f"${v.get('amount', 0):,.2f}" if v else t, flagged=t == meta["flagged_txn_id"],
              affected=t in c["affected_txn_ids"], ts=v.get("ts"), channel=v.get("channel"),
              product=v.get("product_cd"), risk=v.get("risk_score"), device_new=v.get("id_15"),
              proxy=v.get("id_23"))
        _edge(edges, meta["card_id"], t, "MADE")
        for d in _edges("Transaction", t, "FROM_DEVICE"):
            _node(nodes, f"dev:{d}", "device", d.split(" | ")[0][:22], full=d)
            _edge(edges, t, f"dev:{d}", "FROM_DEVICE")
        for r in _edges("Transaction", t, "BILLED_IN"):
            _node(nodes, f"region:{r}", "region", f"region {r}")
            _edge(edges, t, f"region:{r}", "BILLED_IN")

    for d in c["connected_device_profiles"]:
        _node(nodes, f"dev:{d}", "device", d.split(" | ")[0][:22], full=d, shared=True)
    anchor = f"dev:{c['connected_device_profiles'][0]}" if c["connected_device_profiles"] else cid
    for k in c["connected_card_ids"][:14]:
        _node(nodes, k, "linked_card", k)
        _edge(edges, k, anchor, "SHARES_DEVICE" if anchor != cid else "CONNECTED")
    closed = _vertices("ClosedCase", c["similar_prior_cases"])
    for m in c["similar_prior_cases"][:10]:
        v = closed.get(m, {})
        _node(nodes, m, "memory", m, outcome=v.get("outcome"), pattern=v.get("pattern"),
              notes=(v.get("analyst_notes") or "")[:220])
        _edge(edges, cid, m, "SIMILAR_TO")
        if v.get("pattern") and v["pattern"] not in ("none",) and v["pattern"] == c["pattern"]:
            _edge(edges, m, f"pattern:{c['pattern']}", "MATCHES")
    return {"nodes": list(nodes.values()), "edges": edges}


@app.get("/api/graph")
def overview_graph() -> dict:
    """All investigated cases on one canvas, joined by the patterns, devices, cards and memory they share."""
    nodes: dict = {}
    edges: list = []
    for r in list_cases():
        a = answer(r["case_id"])
        c = a["case"]
        cid = r["case_id"]
        _node(nodes, cid, "case", cid, verdict=c["verdict"], p=c["fraud_probability"], status=c["status"])
        _node(nodes, r["card_id"], "card", r["card_id"])
        _edge(edges, cid, r["card_id"], "ON_CARD")
        if c["pattern"] != "none":
            _node(nodes, f"pattern:{c['pattern']}", "pattern", c["pattern"].replace("_", " "))
            _edge(edges, cid, f"pattern:{c['pattern']}", "MATCHES")
        for d in c["connected_device_profiles"]:
            _node(nodes, f"dev:{d}", "device", d.split(" | ")[0][:22], full=d, shared=True)
            _edge(edges, cid, f"dev:{d}", "DEVICE")
        for k in c["connected_card_ids"][:6]:
            _node(nodes, k, "linked_card", k)
            _edge(edges, k, cid, "CONNECTED")
        for m in c["similar_prior_cases"][:4]:
            _node(nodes, m, "memory", m)
            _edge(edges, cid, m, "SIMILAR_TO")
    return {"nodes": list(nodes.values()), "edges": edges}
