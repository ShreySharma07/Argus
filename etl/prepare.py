"""Raw dataset CSVs -> slim TSV vertex/edge files in data/graph/ (M1).

    python -m etl.prepare

Card IDs are not a column in the dataset. They are derived per customer from
the distinct (card4, card6) pairs: the pair with both blank first, then the
rest sorted by (card4, card6); the n-th pair is <customer_id>-K<n>. This
reproduces every card_id in closed_cases_history.csv and case_pack.csv.
"""

import csv

import numpy as np
import pandas as pd

from config.settings import DATA_DIR, ROOT

OUT = ROOT / "data" / "graph"
MISSING = -999  # numeric NaN sentinel (TigerGraph would load NaN as 0)
TXN_CHUNK_ROWS = 100_000  # keeps each upload well under the 128 MB REST limit

C_COLS = [f"C{i}" for i in range(1, 15)]
D_COLS = [f"D{i}" for i in range(1, 16)]
M_COLS = [f"M{i}" for i in range(1, 10)]
TXN_COLS = (["TransactionID", "TransactionDT", "TransactionAmt", "ProductCD",
             "card2", "card3", "card4", "card5", "card6", "addr1", "addr2", "dist1", "dist2",
             "P_emaildomain", "R_emaildomain", "customer_id", "ts", "channel", "risk_score"]
            + C_COLS + D_COLS + M_COLS)
ID_NUM = [f"id_{i:02d}" for i in range(1, 12)]
ID_CAT = ["id_12", "id_15", "id_16", "id_23", "id_27", "id_28", "id_29",
          "id_34", "id_35", "id_36", "id_37", "id_38"]
ID_COLS = ["TransactionID", "id_30", "id_31", "id_33", "DeviceType", "DeviceInfo"] + ID_NUM + ID_CAT


def code(s: pd.Series) -> pd.Series:
    """Float codes like 444.0 -> '444'; NaN -> ''."""
    return s.map(lambda v: "" if pd.isna(v) else str(int(v)) if float(v).is_integer() else str(v))


def text(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.replace("\t", " ")


def num(s: pd.Series) -> pd.Series:
    return s.fillna(MISSING)


def assign_card_ids(t: pd.DataFrame) -> pd.Series:
    pairs = t[["customer_id", "card4", "card6"]].drop_duplicates()
    pairs["blank"] = pairs.card4.isna() & pairs.card6.isna()
    pairs = pairs.sort_values(["customer_id", "blank", "card4", "card6"],
                              ascending=[True, False, True, True], na_position="last")
    pairs["card_id"] = pairs.customer_id + "-K" + (pairs.groupby("customer_id").cumcount() + 1).astype(str)
    keyed = t[["customer_id", "card4", "card6"]].merge(pairs, on=["customer_id", "card4", "card6"], how="left")
    return pd.Series(keyed.card_id.values, index=t.index)


def device_profile_id(i: pd.DataFrame) -> pd.Series:
    parts = [i[c].fillna("unknown").astype(str).str.replace("\t", " ") for c in ("DeviceInfo", "id_30", "id_31", "id_33")]
    return parts[0] + " | " + parts[1] + " | " + parts[2] + " | " + parts[3]


def write(df: pd.DataFrame, name: str) -> None:
    df.to_csv(OUT / name, sep="\t", index=False, quoting=csv.QUOTE_NONE, escapechar="\\")
    print(f"  {name}: {len(df):,} rows")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.tsv"):
        f.unlink()

    print("reading transactions.csv ...")
    t = pd.read_csv(DATA_DIR / "transactions.csv", usecols=TXN_COLS, low_memory=False)
    print("reading identity.csv ...")
    i = pd.read_csv(DATA_DIR / "identity.csv", usecols=ID_COLS, low_memory=False)
    i["device_profile"] = device_profile_id(i)

    t["card_id"] = assign_card_ids(t)
    assert t.card_id.notna().all()
    t = t.merge(i, on="TransactionID", how="left", indicator=True)
    t["has_identity"] = np.where(t.pop("_merge") == "both", "true", "false")

    # Vertices
    write(pd.DataFrame({"id": sorted(t.customer_id.unique())}), "customers.tsv")
    cards = t.drop_duplicates("card_id")[["card_id", "customer_id", "card4", "card6"]]
    write(pd.DataFrame({"id": cards.card_id, "customer_id": cards.customer_id,
                        "network": text(cards.card4), "card_type": text(cards.card6)}), "cards.tsv")
    dev = i.drop_duplicates("device_profile")
    write(pd.DataFrame({"id": dev.device_profile, "device_info": text(dev.DeviceInfo), "os": text(dev.id_30),
                        "browser": text(dev.id_31), "screen": text(dev.id_33)}), "device_profiles.tsv")
    emails = pd.concat([t.P_emaildomain, t.R_emaildomain]).dropna().unique()
    write(pd.DataFrame({"id": sorted(emails)}), "email_domains.tsv")
    write(pd.DataFrame({"id": sorted(code(t.addr1.dropna()).unique())}), "billing_regions.tsv")

    tx = pd.DataFrame({
        "id": t.TransactionID.astype(str), "dt": t.TransactionDT, "ts": t.ts,
        "amount": t.TransactionAmt, "product_cd": t.ProductCD, "channel": t.channel,
        "risk_score": t.risk_score, "card_id": t.card_id, "customer_id": t.customer_id,
        "card2": code(t.card2), "card3": code(t.card3), "card5": code(t.card5),
        "addr1": code(t.addr1), "addr2": code(t.addr2), "dist1": num(t.dist1), "dist2": num(t.dist2),
        "p_email": text(t.P_emaildomain), "r_email": text(t.R_emaildomain),
        **{c: num(t[c]) for c in C_COLS + D_COLS}, **{c: text(t[c]) for c in M_COLS},
        "has_identity": t.has_identity, "device_type": text(t.DeviceType),
        **{c: num(t[c]) for c in ID_NUM}, **{c: text(t[c]) for c in ID_CAT},
    })
    for n, start in enumerate(range(0, len(tx), TXN_CHUNK_ROWS)):
        write(tx.iloc[start:start + TXN_CHUNK_ROWS], f"transactions_{n:02d}.tsv")

    # Edges not derivable from the transaction rows' own columns
    write(pd.DataFrame({"txn": t.TransactionID[t.device_profile.notna()].astype(str),
                        "device": t.device_profile.dropna()}), "txn_device.tsv")
    s = t.sort_values(["card_id", "TransactionDT", "TransactionID"])
    same = s.card_id.values[1:] == s.card_id.values[:-1]
    write(pd.DataFrame({
        "src": s.TransactionID.values[:-1][same].astype(str),
        "dst": s.TransactionID.values[1:][same].astype(str),
        "gap_s": (s.TransactionDT.values[1:] - s.TransactionDT.values[:-1])[same],
    }), "txn_next.tsv")


if __name__ == "__main__":
    main()
