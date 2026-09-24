"""Create the entity schema and loading job on the graph (M1).

    python -m graph.setup            # schema + loading job
    python -m graph.setup --job-only # (re)create the loading job only
    python -m graph.setup --agent-cases  # AgentCase write-back schema (after load_prior_cases)
    python -m graph.setup --queries  # create + install graph/queries/*.gsql

The loading job is generated from the TSV headers written by etl.prepare so the
column order can never drift; the generated GSQL is saved to
graph/loading_jobs.gsql for reference.
"""

import argparse

from config.settings import ROOT, TG_GRAPHNAME
from graph.tg import connect, gsql_file

GRAPH_DIR = ROOT / "graph"
DATA = ROOT / "data" / "graph"
JOB = "load_entities"
# REST uploads ignore header="true", so etl.load strips the header line before sending.
OPTS = 'USING header="false", separator="\\t", eol="\\n"'


def _header(name: str) -> list[str]:
    return open(DATA / name).readline().rstrip("\n").split("\t")


def _vals(cols: list[str]) -> str:
    return ", ".join(f"${i}" for i in range(len(cols)))


def _col(file: str, name: str) -> str:
    """Positional reference ($n) to a named column of a prepared TSV."""
    return f"${_header(file).index(name)}"


def loading_job_gsql() -> str:
    txn_cols = _header("transactions_00.tsv")
    T = "transactions_00.tsv"
    tid, card, addr1, pe, re_ = (_col(T, c) for c in ("id", "card_id", "addr1", "p_email", "r_email"))
    return f"""USE GRAPH {TG_GRAPHNAME}
CREATE LOADING JOB {JOB} FOR GRAPH {TG_GRAPHNAME} {{
  DEFINE FILENAME customers;
  DEFINE FILENAME cards;
  DEFINE FILENAME devices;
  DEFINE FILENAME emails;
  DEFINE FILENAME regions;
  DEFINE FILENAME txns;
  DEFINE FILENAME txn_device;
  DEFINE FILENAME txn_next;

  LOAD customers TO VERTEX Customer VALUES ($0) {OPTS};
  LOAD cards TO VERTEX Card VALUES ({_vals(_header("cards.tsv"))}),
             TO EDGE OWNS VALUES ({_col("cards.tsv", "customer_id")}, {_col("cards.tsv", "id")}) {OPTS};
  LOAD devices TO VERTEX DeviceProfile VALUES ({_vals(_header("device_profiles.tsv"))}) {OPTS};
  LOAD emails TO VERTEX EmailDomain VALUES ($0) {OPTS};
  LOAD regions TO VERTEX BillingRegion VALUES ($0) {OPTS};
  LOAD txns TO VERTEX Transaction VALUES ({_vals(txn_cols)}),
            TO EDGE MADE VALUES ({card}, {tid}),
            TO EDGE BILLED_IN VALUES ({tid}, {addr1}) WHERE {addr1} != "",
            TO EDGE PURCHASER_EMAIL VALUES ({tid}, {pe}) WHERE {pe} != "",
            TO EDGE RECIPIENT_EMAIL VALUES ({tid}, {re_}) WHERE {re_} != "" {OPTS};
  LOAD txn_device TO EDGE FROM_DEVICE VALUES ($0, $1) {OPTS};
  LOAD txn_next TO EDGE NEXT VALUES ($0, $1, $2) {OPTS};
}}
"""


def install_queries(conn) -> None:
    files = sorted((GRAPH_DIR / "queries").glob("*.gsql"))
    for f in files:
        out = gsql_file(conn, f)
        print(f"{f.stem}: {out.strip().splitlines()[-1]}")
        if "fail" in out.lower() or "error" in out.lower():
            print(out)
            raise SystemExit(f"query {f.stem} did not compile")
    names = ", ".join(f.stem for f in files)
    print(conn.gsql(f"USE GRAPH {TG_GRAPHNAME}\nINSTALL QUERY {names}"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-only", action="store_true")
    ap.add_argument("--agent-cases", action="store_true")
    ap.add_argument("--queries", action="store_true")
    args = ap.parse_args()

    conn = connect()
    if args.agent_cases:
        print(gsql_file(conn, GRAPH_DIR / "schema_cases.gsql"))
        return
    if args.queries:
        install_queries(conn)
        return
    if not args.job_only:
        print(gsql_file(conn, GRAPH_DIR / "schema.gsql"))
    job = loading_job_gsql()
    (GRAPH_DIR / "loading_jobs.gsql").write_text(job)
    print(conn.gsql(f"USE GRAPH {TG_GRAPHNAME}\nDROP JOB {JOB}"))
    print(conn.gsql(job))


if __name__ == "__main__":
    main()
