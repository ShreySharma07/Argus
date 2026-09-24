"""GraphRAG document ingestion (M2).

Chunks the fraud policy, the five known patterns and the analyst guidance from
the dataset README (plus any regulatory documents placed in
DATA_DIR/regulations/), embeds them locally, writes data/knowledge/chunks.jsonl,
and optionally loads PolicyChunk / FraudPattern / DESCRIBES into TigerGraph.

    python -m etl.ingest_docs                 # build chunks.jsonl only
    python -m etl.ingest_docs --setup --load  # + create schema, install query, upsert
"""

import argparse
import html
import json
import re
from pathlib import Path

from agent.embed import embed_passages
from config.settings import DATA_DIR, KNOWLEDGE_CHUNKS, ROOT

PATTERNS = {
    "card testing": "card_testing",
    "card-not-present fraud": "card_not_present_fraud",
    "card-not-present fraud from a new device": "card_not_present_new_device",
    "out-of-region use": "out_of_region_use",
    "account takeover": "account_takeover",
}
# Rules whose text is about one specific pattern.
RULE_PATTERNS = {"R5": {"card_testing"}, "R9": {"undocumented"}}

# ~200-300 tokens: sharper matches, and well inside bge-small's 512-token window.
REG_CHUNK_CHARS = 1100
REG_OVERLAP = 200


def _section(md: str, heading: str) -> str:
    """Body of a markdown section, up to the next heading of the same or higher level."""
    level = len(heading) - len(heading.lstrip("#"))
    m = re.search(rf"^{re.escape(heading)}\s*$", md, re.M)
    if not m:
        raise ValueError(f"README section not found: {heading}")
    rest = md[m.end():]
    nxt = re.search(rf"^#{{1,{level}}} ", rest, re.M)
    return rest[: nxt.start() if nxt else len(rest)].strip()


def _rule_refs(text: str) -> set[str]:
    refs = set()
    for a, b in re.findall(r"\bR(\d+)(?:\s*(?:to|-|–)\s*R(\d+))?\b", text):
        lo, hi = int(a), int(b or a)
        refs |= {f"R{i}" for i in range(lo, hi + 1)}
    return refs


def _chunk(cid, section, title, text, source="policy", rules=(), patterns=()):
    return {
        "id": cid, "source": source, "section": section, "title": title,
        "text": text.strip(), "rule_ids": sorted(set(rules)), "pattern_ids": sorted(set(patterns)),
    }


def readme_chunks(md: str) -> list[dict]:
    chunks = []

    # Five known patterns: one chunk each.
    body = _section(md, "## The five known fraud patterns")
    for num, name, text in re.findall(r"\*\*(\d)\. ([^*]+?)\.\*\*\s*(.+?)(?=\n\s*\*\*\d\.|\Z)", body, re.S):
        pid = PATTERNS[name.strip().lower()]
        chunks.append(_chunk(f"pattern:{pid}", "Known fraud patterns", name.strip(),
                             f"Fraud pattern '{pid}' ({name.strip()}). {text}", source="pattern",
                             rules=_rule_refs(text), patterns=[pid]))

    chunks.append(_chunk("guide:things_to_know", "Things to know", "Investigation guidance",
                         _section(md, "## Things to know"), source="guidance"))
    chunks.append(_chunk("guide:glossary", "Glossary", "Glossary",
                         _section(md, "## Glossary"), source="guidance"))

    # Fraud Policy: numbered subsections, with §3 split per rule.
    policy = _section(md, "# Fraud Policy")
    for m in re.finditer(r"^### (\d+[a-z]?)\. (.+)$", policy, re.M):
        num, title = m.group(1), m.group(2).strip()
        text = _section(policy, m.group(0))
        if num == "3":
            for rid, rtitle, rtext in re.findall(r"\*\*(R\d+)\. ([^*]+?)\*\*\s*(.+?)(?=\n\s*\*\*R\d+\.|\Z)", text, re.S):
                chunks.append(_chunk(f"policy:{rid}", f"Fraud Policy §3 {rid}", rtitle.strip().rstrip("."),
                                     f"Policy rule {rid}. {rtitle.strip()} {rtext}",
                                     rules=[rid], patterns=RULE_PATTERNS.get(rid, ())))
        else:
            chunks.append(_chunk(f"policy:s{num}", f"Fraud Policy §{num}", title,
                                 f"Fraud Policy §{num} {title}.\n{text}", rules=_rule_refs(text)))

    # Patterns that cite rules link those rules back to the pattern.
    cited = {}
    for c in chunks:
        if c["source"] == "pattern":
            for r in c["rule_ids"]:
                cited.setdefault(r, set()).update(c["pattern_ids"])
    for c in chunks:
        if c["id"].startswith("policy:R"):
            c["pattern_ids"] = sorted(set(c["pattern_ids"]) | cited.get(c["id"][7:], set()))
    return chunks


def _pdf_pages(path: Path) -> list[str]:
    """PDF text per page with running headers/footers and bare page numbers removed."""
    from collections import Counter
    from pypdf import PdfReader
    pages = [(p.extract_text() or "").splitlines() for p in PdfReader(path).pages]
    freq = Counter(l.strip() for lines in pages for l in set(lines) if l.strip())
    repeated = {l for l, n in freq.items() if len(pages) >= 4 and n >= 0.5 * len(pages)}
    return ["\n".join(l for l in lines if l.strip() not in repeated and not re.fullmatch(r"\s*(page\s*)?\d+\s*", l, re.I))
            for lines in pages]


def _read_doc(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "\n".join(_pdf_pages(path))
    text = path.read_text(errors="ignore")
    if path.suffix.lower() in (".html", ".htm"):
        text = re.sub(r"(?s)<(script|style).*?</\1>", " ", text)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return text


def _sentences(text: str) -> list[str]:
    # Join PDF line-wraps, keep blank-line paragraph breaks, then split on sentence ends.
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    out = []
    for p in paras:
        out += [s for s in re.split(r"(?<=[.!?;:])\s+(?=[A-Z0-9(\"\u2022-])", p) if s]
    return out


def _pack(sentences: list[str]) -> list[str]:
    """Greedy-pack sentences into ~REG_CHUNK_CHARS chunks; carry trailing sentences as overlap."""
    chunks, cur = [], []
    for sent in sentences:
        while len(sent) > REG_CHUNK_CHARS:  # pathological run-on text: hard split
            sentences_head, sent = sent[:REG_CHUNK_CHARS], sent[REG_CHUNK_CHARS:]
            if cur:
                chunks.append(" ".join(cur)); cur = []
            chunks.append(sentences_head)
        if cur and len(" ".join(cur)) + len(sent) + 1 > REG_CHUNK_CHARS:
            chunks.append(" ".join(cur))
            tail = []
            for prev in reversed(cur):
                if len(" ".join([prev] + tail)) > REG_OVERLAP:
                    break
                tail.insert(0, prev)
            cur = tail
        cur.append(sent)
    if cur:
        chunks.append(" ".join(cur))
    return [c for c in chunks if len(c) >= 200]


def regulation_chunks(folder: Path) -> list[dict]:
    chunks = []
    if not folder.is_dir():
        return chunks
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in (".pdf", ".txt", ".md", ".html", ".htm"):
            continue
        doc = re.sub(r"[^A-Za-z0-9_-]+", "_", path.name.split(".pdf")[0].split(".")[0]).strip("_")
        for i, piece in enumerate(_pack(_sentences(_read_doc(path)))):
            chunks.append(_chunk(f"reg:{doc}:{i:03d}", doc, doc, piece, source="regulation"))
    return chunks


def build() -> list[dict]:
    md = (DATA_DIR / "README.md").read_text()
    chunks = readme_chunks(md) + regulation_chunks(DATA_DIR / "regulations")
    vecs = embed_passages([f"{c['title']}. {c['text']}" for c in chunks])
    for c, v in zip(chunks, vecs):
        c["emb"] = v
    KNOWLEDGE_CHUNKS.parent.mkdir(parents=True, exist_ok=True)
    with open(KNOWLEDGE_CHUNKS, "w") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")
    return chunks


def setup_graph(conn) -> None:
    from graph.tg import gsql_file
    print(gsql_file(conn, ROOT / "graph" / "schema_knowledge.gsql"))
    print(gsql_file(conn, ROOT / "graph" / "queries" / "policy_search.gsql"))
    print(conn.gsql(f"USE GRAPH {conn.graphname}\nINSTALL QUERY policy_search"))


def load_graph(conn, chunks: list[dict]) -> None:
    # Full sync: chunk IDs change when chunking changes, so drop chunks no longer produced.
    keep = {c["id"] for c in chunks}
    stale = [v["v_id"] for v in conn.getVertices("PolicyChunk", select="source", limit=100000) if v["v_id"] not in keep]
    for i in range(0, len(stale), 500):
        conn.delVerticesById("PolicyChunk", stale[i:i + 500])
    print(f"Removed {len(stale)} stale PolicyChunk")
    pattern_ids = set(PATTERNS.values()) | {"undocumented"}
    conn.upsertVertices("FraudPattern", [
        (p, {"name": p, "documented": p != "undocumented"}) for p in sorted(pattern_ids)])
    rows = [(c["id"], {k: c[k] for k in ("source", "section", "title", "text", "rule_ids", "pattern_ids", "emb")})
            for c in chunks]
    for i in range(0, len(rows), 200):
        conn.upsertVertices("PolicyChunk", rows[i:i + 200])
    edges = [(c["id"], p) for c in chunks for p in c["pattern_ids"]]
    conn.upsertEdges("PolicyChunk", "DESCRIBES", "FraudPattern", [(s, t, {}) for s, t in edges])
    print(f"Loaded {len(chunks)} PolicyChunk, {len(pattern_ids)} FraudPattern, {len(edges)} DESCRIBES")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true", help="create knowledge schema + install policy_search")
    ap.add_argument("--load", action="store_true", help="upsert chunks into TigerGraph")
    args = ap.parse_args()

    chunks = build()
    by_source = {}
    for c in chunks:
        by_source[c["source"]] = by_source.get(c["source"], 0) + 1
    print(f"Wrote {len(chunks)} chunks to {KNOWLEDGE_CHUNKS.relative_to(ROOT)}: {by_source}")

    if args.setup or args.load:
        from graph.tg import connect
        conn = connect()
        if args.setup:
            setup_graph(conn)
        if args.load:
            load_graph(conn, chunks)


if __name__ == "__main__":
    main()
