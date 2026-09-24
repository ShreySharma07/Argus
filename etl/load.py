"""Run the load_entities job over data/graph/*.tsv and check counts (M1).

    python -m etl.load            # load everything, then verify
    python -m etl.load --verify   # verify counts only
"""

import argparse
import sys
import tempfile
from pathlib import Path

from config.settings import ROOT
from graph.setup import JOB
from graph.tg import connect

DATA = ROOT / "data" / "graph"

# fileTag in the loading job -> file(s)
FILES = [
    ("customers", ["customers.tsv"]),
    ("cards", ["cards.tsv"]),
    ("devices", ["device_profiles.tsv"]),
    ("emails", ["email_domains.tsv"]),
    ("regions", ["billing_regions.tsv"]),
    ("txns", sorted(p.name for p in DATA.glob("transactions_*.tsv"))),
    ("txn_device", ["txn_device.tsv"]),
    ("txn_next", ["txn_next.tsv"]),
]


def rows(name: str) -> int:
    with open(DATA / name) as f:
        return sum(1 for _ in f) - 1


def expected() -> tuple[dict, dict]:
    txn_files = dict(FILES)["txns"]
    n_txn = sum(rows(f) for f in txn_files)
    nonempty = {"addr1": 0, "p_email": 0, "r_email": 0}
    for f in txn_files:
        with open(DATA / f) as fh:
            cols = fh.readline().rstrip("\n").split("\t")
            idx = {c: cols.index(c) for c in nonempty}
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                for c, i in idx.items():
                    nonempty[c] += parts[i] != ""
    vertices = {
        "Customer": rows("customers.tsv"), "Card": rows("cards.tsv"),
        "DeviceProfile": rows("device_profiles.tsv"), "EmailDomain": rows("email_domains.tsv"),
        "BillingRegion": rows("billing_regions.tsv"), "Transaction": n_txn,
    }
    edges = {
        "OWNS": rows("cards.tsv"), "MADE": n_txn, "BILLED_IN": nonempty["addr1"],
        "PURCHASER_EMAIL": nonempty["p_email"], "RECIPIENT_EMAIL": nonempty["r_email"],
        "FROM_DEVICE": rows("txn_device.tsv"), "NEXT": rows("txn_next.tsv"),
    }
    return vertices, edges


def verify(conn) -> bool:
    vertices, edges = expected()
    ok = True
    for kind, exp, get in (("vertex", vertices, conn.getVertexCount), ("edge", edges, conn.getEdgeCount)):
        for name, n in exp.items():
            got = get(name)
            flag = "OK " if got == n else "BAD"
            ok &= got == n
            print(f"  {flag} {kind:6} {name:16} expected {n:>9,}  got {got:>9,}")
    return ok


def load(conn) -> None:
    for tag, names in FILES:
        for name in names:
            print(f"loading {name} -> {tag} ...", flush=True)
            # Online POST loads the header as data, so send a headerless copy.
            with open(DATA / name) as src, tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False) as tmp:
                src.readline()
                for line in src:
                    tmp.write(line)
            try:
                res = conn.runLoadingJobWithFile(tmp.name, tag, JOB, sep="\t", timeout=600_000)
            finally:
                Path(tmp.name).unlink()
            stats = (res or [{}])[0].get("statistics", res)
            print(f"   {stats}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    conn = connect()
    if not args.verify:
        load(conn)
    sys.exit(0 if verify(conn) else 1)


if __name__ == "__main__":
    main()
