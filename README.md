# Argus — agentic fraud investigation on TigerGraph

Argus investigates card-fraud alerts the way an analyst would. It builds evidence from a TigerGraph knowledge graph (590k transactions, device and region links, 5,565 closed cases), reasons over it with an LLM, requests more evidence under the bank's policy when it is not sure, recommends actions with their approval routes, writes a SAR when the policy requires one, and writes every case back to the graph as memory.

- **Answer files:** [`cases/`](cases/): one `HHG-xxx.json` per benchmark case (README Answer Format)
- **Write-up:** [`docs/blog.md`](docs/blog.md)
- **Design notes:** [`CLAUDE.md`](CLAUDE.md) (architecture, schema, queries, milestones)

```
alert ─▶ gather evidence (GSQL via MCP) ─▶ retrieve policy (GraphRAG) ─▶ assess (LLM, round 1)
      ─▶ [not decisive] request evidence ─▶ re-assess ─▶ stop criteria (policy §6)
      ─▶ policy engine: actions + approval routes (R1–R10) ─▶ SAR ─▶ write case to TigerGraph
```

The graph establishes the facts, deterministic code applies the policy (actions, routes, SAR decision), and the LLM judges what the evidence means and explains it.

## Repository layout

| Path | What it is |
|---|---|
| `graph/` | GSQL schema (`schema.gsql`, `schema_knowledge.gsql`, `schema_cases.gsql`), installed queries (`queries/*.gsql`), `setup.py` |
| `etl/` | `prepare.py` (raw CSV → TSVs, card-ID derivation), `load.py`, `load_prior_cases.py`, `ingest_docs.py` (GraphRAG) |
| `agent/` | `workflow.py` (the investigation loop), `evidence.py`, `assess.py`, `decide.py` (policy engine), `explain.py` (SAR), `memory.py`, `rag.py`, `scoring.py`, `llm.py`, `tools/` (MCP client with allowlist, graph queries, evidence simulator, mock actions) |
| `config/` | `policy_matrix.yaml` (Fraud Policy v1.0), `thresholds.yaml` (loop settings) |
| `runner/` | `run_benchmark.py` (20 cases → `cases/`), `validate_answers.py` |
| `api/` | FastAPI analyst API for the console |
| `frontend/` | React/Expo (web) analyst console |
| `runs/` | Per-case investigation timelines |

## Prerequisites

- Python 3.12, Node 20
- A TigerGraph Savanna workspace (or Community Edition) with an **empty graph named `FraudGraph`**. On Savanna, enable auto-start; workspaces auto-stop when idle.
- The dataset folder (`transactions.csv`, `identity.csv`, `closed_cases_history.csv`, `case_pack.csv`, `README.md`), plus optional regulatory PDFs in `<dataset>/regulations/`
- An LLM key: Anthropic (default) or Gemini

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
(cd frontend && npm ci)
cp .env.example .env    # then fill it in
```

In `.env`, set:
- `TG_HOST` (e.g. `https://<workspace>.i.tgcloud.io`), `TG_GRAPHNAME=FraudGraph`, `TG_SECRET`, `TG_TGCLOUD=true`, `TG_RESTPP_PORT=443`, `TG_GS_PORT=443`
- `DATA_DIR`: the path to the dataset folder
- `ANTHROPIC_API_KEY`, or `LLM_PROVIDER=gemini` with `GEMINI_API_KEY` and `GEMINI_MODEL`

Check the connection. The agent reaches the graph only through `tigergraph-mcp` with a tool allowlist:

```bash
.venv/bin/python -m scripts.check_mcp
```

## Build the graph (once, in this order)

```bash
# 1. Knowledge layer: policy, patterns, regulations -> PolicyChunk vectors + policy_search
.venv/bin/python -m etl.ingest_docs --setup --load

# 2. Entities: 590,742 transactions, cards, devices, regions, emails (about 10 min; verifies every count)
.venv/bin/python -m etl.prepare
.venv/bin/python -m graph.setup
.venv/bin/python -m etl.load

# 3. Case memory: 5,565 ClosedCase vertices + edges + note embeddings (verifies counts)
.venv/bin/python -m etl.load_prior_cases

# 4. Agent write-back schema, then install every query in graph/queries/
.venv/bin/python -m graph.setup --agent-cases
.venv/bin/python -m graph.setup --queries

# optional: run each query for three sample cases through MCP
.venv/bin/python -m scripts.check_queries HHG-001 HHG-010 HHG-014
```

If a load reports a count mismatch right after a large upload, re-run with `--verify`: TigerGraph can take a few seconds to report final counts.

## Run the investigation

```bash
.venv/bin/python -m runner.run_benchmark                 # all 20 cases -> cases/, timelines -> runs/
.venv/bin/python -m runner.run_benchmark HHG-014         # one case
.venv/bin/python -m runner.validate_answers              # answer format + every ID exists in the dataset
```

- **Pace and cost:** about 80 s and 10–15 graph calls per case, running 4 cases in parallel on Anthropic.
- **Gemini free tier:** set `LLM_PROVIDER=gemini`. Cases then run one at a time and calls are paced by `GEMINI_RPM`. If a model is overloaded, calls rotate across `GEMINI_MODEL` and `GEMINI_FALLBACK_MODELS`.
- **Each case:**
  1. gathers graph evidence and retrieves the relevant policy
  2. assesses the case
  3. if not decisive, requests policy-approved evidence (customer, step-up or analyst). Replies are simulated, and the assumption is recorded in `evidence_requests`, as the README requires.
  4. re-assesses until a stop criterion holds
  5. produces `initial`/`final` next best actions with approval routes, and a SAR when §3a requires one
  6. writes an `AgentCase` vertex with its edges to TigerGraph

## Run the analyst console

```bash
.venv/bin/uvicorn api.server:app --port 8000
cd frontend && npx expo start --web --port 8081      # open http://localhost:8081
```

Set `EXPO_PUBLIC_API_URL` if the API isn't on `localhost:8000`.

The console has:
- **Overview:** totals and the case queue
- **Investigations:** the queue, with filters
- **Case page:** how the probability moved, next best actions before and after the evidence, role-gated approvals, evidence, timeline, the case's graph, and the SAR
- **Knowledge Graph:** all cases or one case
- **Policy:** approval routes and rules

Switch the role in the sidebar to approve L1 or L2 actions. The API enforces the same rules and logs every approval to `runs/actions_log.jsonl`.

## Notes

- Answer files were produced with `claude-opus-5`. HHG-001 to HHG-011 used the full evidence loop; HHG-012 to HHG-020 are from the earlier single-pass version, because API credits ran out before a rerun. All 20 validate.
- Every transaction, card, device and case ID in the answers is validated against the dataset.
- The LLM never chooses actions or approval routes; `agent/decide.py` applies the policy.
