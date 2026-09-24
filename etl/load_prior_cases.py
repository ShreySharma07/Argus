"""closed_cases_history.csv -> ClosedCase vertices + edges + note embeddings (M3).

    python -m etl.load_prior_cases            # add vector attr (once), load, verify
    python -m etl.load_prior_cases --verify

ClosedCase is the bank's labelled history (July-October) and the agent's
starting memory. Edges: INVOLVES -> Transaction, ON_CARD / CONNECTED_TO -> Card,
MATCHES -> FraudPattern (pattern 'none' has no edge).
"""

import argparse
import sys

import pandas as pd

from agent.embed import DIM, embed_passages
from config.settings import DATA_DIR, TG_GRAPHNAME
from graph.tg import connect

BATCH = 500


def _split(s) -> list[str]:
    return [x for x in str(s).split("|") if x and x != "nan"] if pd.notna(s) else []


def ensure_vector_attr(conn) -> None:
    if "notes_emb" in conn.gsql(f"USE GRAPH {TG_GRAPHNAME}\nLS"):
        return
    print(conn.gsql(f"""USE GRAPH {TG_GRAPHNAME}
CREATE SCHEMA_CHANGE JOB add_case_emb FOR GRAPH {TG_GRAPHNAME} {{
  ALTER VERTEX ClosedCase ADD VECTOR ATTRIBUTE notes_emb(DIMENSION={DIM}, METRIC="COSINE");
}}
RUN SCHEMA_CHANGE JOB add_case_emb
DROP JOB add_case_emb"""))


def build(cc: pd.DataFrame):
    embs = embed_passages(cc.analyst_notes.fillna("").tolist())
    vertices = []
    for r, emb in zip(cc.itertuples(), embs):
        vertices.append((r.case_id, {
            "customer_id": r.customer_id, "card_id": r.card_id,
            "opened_at": r.opened_at, "closed_at": r.closed_at,
            "outcome": r.outcome, "pattern": r.pattern,
            "first_fraud_txn_id": "" if pd.isna(r.first_fraud_txn_id) else str(r.first_fraud_txn_id),
            "n_txns": int(r.n_txns), "exposure_usd": float(r.exposure_usd),
            "actions_taken": r.actions_taken, "report_filed": r.report_filed == "Yes",
            "analyst_notes": r.analyst_notes, "notes_emb": emb,
        }))
    edges = {"INVOLVES": [], "ON_CARD": [], "CONNECTED_TO": [], "MATCHES": []}
    for r in cc.itertuples():
        edges["INVOLVES"] += [(r.case_id, t, {}) for t in _split(r.txn_ids)]
        edges["ON_CARD"].append((r.case_id, r.card_id, {}))
        edges["CONNECTED_TO"] += [(r.case_id, k, {}) for k in _split(r.connected_card_ids)]
        if r.pattern != "none":
            edges["MATCHES"].append((r.case_id, r.pattern, {}))
    return vertices, edges


TARGET = {"INVOLVES": "Transaction", "ON_CARD": "Card", "CONNECTED_TO": "Card", "MATCHES": "FraudPattern"}


def load(conn, vertices, edges) -> None:
    for i in range(0, len(vertices), BATCH):
        conn.upsertVertices("ClosedCase", vertices[i:i + BATCH])
    print(f"upserted {len(vertices)} ClosedCase")
    for e, rows in edges.items():
        for i in range(0, len(rows), 5000):
            # vertexMustExist: never create placeholder Transaction/Card vertices from a bad ID
            conn.upsertEdges("ClosedCase", e, TARGET[e], rows[i:i + 5000], vertexMustExist=True)
        print(f"upserted {len(rows)} {e}")


def verify(conn, vertices, edges) -> bool:
    ok = True
    for name, n, get in [("ClosedCase", len(vertices), conn.getVertexCount)] + \
                        [(e, len(r), conn.getEdgeCount) for e, r in edges.items()]:
        got = get(name)
        ok &= got == n
        print(f"  {'OK ' if got == n else 'BAD'} {name:14} expected {n:>6,}  got {got:>6,}")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    cc = pd.read_csv(DATA_DIR / "closed_cases_history.csv", dtype=str)
    conn = connect()
    vertices, edges = build(cc)
    if not args.verify:
        ensure_vector_attr(conn)
        load(conn, vertices, edges)
    sys.exit(0 if verify(conn, vertices, edges) else 1)


if __name__ == "__main__":
    main()
