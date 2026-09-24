# Fraud Investigation Agent — TigerGraph HHGOA

Hackathon build. Deadline: Sept 25, 2026, 11:59 AM IST (per the submission form). Team of 2.
**Rule #1: all 20 benchmark answer files must exist end-to-end by hour ~20. Polish after.**

> The dataset README (`$DATA_DIR/README.md`) is the spec: columns, the 20 cases, the
> Fraud Policy (actions, routes, R1–R10) and the answer format. Read it; don't invent.

---

## 1. Architecture

```mermaid
flowchart LR
  T[Trigger<br/>risk score / customer report / analyst] --> AG
  subgraph AG[LangGraph Agent]
    direction TB
    TR[triage] --> OC[open_case]
    OC --> GE[gather_evidence<br/>bounded tool loop]
    GE --> AS[assess<br/>scoring + LLM synthesis]
    AS --> UC{enough evidence?}
    UC -- no --> RE[request_evidence<br/>policy-approved action]
    RE --> GE
    UC -- yes --> DE[decide_actions]
    DE --> PG[policy_gate<br/>auto / approval / forbidden]
    PG --> EX[explain + SAR]
    EX --> MEM[write_memory]
  end
  AG <--> MCP[tigergraph-mcp<br/>ALLOWLISTED tools]
  AG <--> ACT[mock action API<br/>freeze, step-up, notify]
  MCP <--> TG[(TigerGraph Savanna<br/>graph + vectors)]
  MEM --> TG
  AG --> ANS[cases/*.json]
  UI[Streamlit analyst UI] <--> AG
```

### Layers and responsibilities

| Layer | What it does | Key rule |
|---|---|---|
| **TigerGraph** | Entities, transactions, prior cases, policy chunks (vectors), new cases | Single source of truth, including written-back cases |
| **GSQL queries** | All graph analytics: neighbourhoods, shared devices, rings, velocity, pattern detectors, similar cases | Graph does the analysis; the LLM never scans raw rows |
| **tigergraph-mcp** | Exposes graph to agent | Allowlist only (no drop/clear/delete tools) |
| **GraphRAG** | Policy/typology/regulation chunks + connected graph evidence → compact context | Pass structured briefs, not raw data |
| **Scoring** | Deterministic risk score + confidence from evidence | Reproducible; LLM explains, doesn't invent numbers |
| **Agent (LangGraph)** | Orchestrates the investigation loop, stop criteria | Max N evidence rounds; explicit stop reason |
| **Policy gate** | Maps each action → auto / needs-approval (role) / forbidden | Agent may *recommend* anything, *execute* only authorised |
| **Case memory** | Prior cases as vertices; similar-case retrieval; write-back on close | Hybrid retrieval: vector + shared entities + same pattern |
| **UI** | Case queue, timeline, evidence graph, uncertainty, NBA before/after, approve buttons | Streamlit, fastest to build |

### Core design decisions
1. **Graph for facts, rules for scores, LLM for reasoning.** Pattern detectors are GSQL; risk/confidence is Python; LLM picks tools, synthesises, explains.
2. **Uncertainty is explicit.** `confidence = f(evidence coverage, signal agreement, similar-case outcome agreement)`. Low confidence → request evidence, not guess.
3. **Two NBA snapshots per case**: `next_best_actions.initial` (before requested evidence) and `.final` (after the assumed responses), each action with its route (`auto` | `L1` | `L2`) and cited rule, plus `what_changed`. (Required by submission.)
4. **Stop criteria** (`agent/workflow.py`, knobs in `config/thresholds.yaml`): decisive p (≥0.85 / ≤0.15) with ≥2 independent signals AND deterministic confidence ≥ threshold, OR a verification reply settled it, OR no new policy-approved request remains, OR max rounds hit. Stop reason recorded. Replies come from `agent/tools/evidence_sources.py`, a simulator separate from the assessor (README §5).
5. **Every step appends to the case record** (evidence, finding, decision, action, timestamp, actor). Case written to graph at each stage.

---

## 2. Graph schema (graph `FraudGraph`, loaded)

Files: `graph/schema.gsql` (entities + prior cases), `graph/schema_knowledge.gsql` (GraphRAG).

**Entity vertices (M1, loaded):**
| Vertex | ID | Notes |
|---|---|---|
| `Customer` | `C01234` | = `card1` (1:1) |
| `Card` | `C01234-K1` | Not a dataset column. Derived per customer from distinct (`card4`, `card6`): blank pair first, then sorted; n-th = `-K<n>`. Reproduces every card_id in closed cases + case pack |
| `Transaction` | `TransactionID` | ts, amount, product_cd, channel, risk_score, card_id, addr1/2, dist1/2, emails, C1–C14, D1–D15, M1–M9, identity fields (id_01–11 numeric, readable id_12…id_38, device_type). V1–V339 not loaded. **Missing numerics = -999** |
| `DeviceProfile` | `DeviceInfo \| OS \| browser \| screen` | Answer-file format for `connected_device_profiles`; missing parts = `unknown` |
| `EmailDomain`, `BillingRegion` | domain / `addr1` code (`444`) | |

**Prior-case memory (Option B: separate types):**
- `ClosedCase` — the 5,565 rows of `closed_cases_history.csv` (schema created in M1, loaded in M3)
- `Case` (+ `Evidence`, `Action`) — cases the agent writes; added with M3/M4 write-back

**Knowledge (M2, loaded):** `PolicyChunk` (vector `emb`, 384-d cosine, bge-small), `FraudPattern` (5 known + `undocumented`)

**Edges (all have reverse edges):**
- `Customer -OWNS-> Card -MADE-> Transaction`, `Transaction -NEXT(gap_s)-> Transaction` (per card, by time)
- `Transaction -FROM_DEVICE-> DeviceProfile`, `-PURCHASER_EMAIL->`/`-RECIPIENT_EMAIL-> EmailDomain`, `-BILLED_IN-> BillingRegion`
- `ClosedCase -INVOLVES-> Transaction`, `-ON_CARD-> Card`, `-CONNECTED_TO-> Card`, `-MATCHES-> FraudPattern`
- `PolicyChunk -DESCRIBES-> FraudPattern`

**Loaded counts:** Customer 13,553 · Card 14,318 · Transaction 590,742 · DeviceProfile 9,706 · EmailDomain 60 · BillingRegion 332 · MADE 590,742 · NEXT 576,424 · FROM_DEVICE 144,432 · BILLED_IN 525,003 · PURCHASER_EMAIL 496,262 · RECIPIENT_EMAIL 137,453 · PolicyChunk 832

**Rebuild:** `python -m etl.prepare && python -m graph.setup && python -m etl.load` (load verifies counts). Knowledge: `python -m etl.ingest_docs --setup --load`.

---

## 3. GSQL queries (installed)

All in `graph/queries/`, installed with `python -m graph.setup --queries`, called only via the MCP allowlist. Time params bound every query to data **before the alert** (no future leakage).

| Query | Purpose |
|---|---|
| `card_profile(card, as_of, lookback_days)` | Baseline before `as_of`: n, total, sum_sq, max, channel/product/region/country/email/device mix, customer's other cards |
| `card_activity(card, start_ts, end_ts)` | Txns in window, oldest first, with device profile, id_15/id_23/id_34, M4–M6, C/D samples, and any prior ClosedCase on the txn |
| `shared_devices(card, start_ts, end_ts)` | Devices the card used + how common each is (all-time cards) + other cards on them in the window with their confirmed-fraud cases (R6) |
| `region_newcomers(region, start_ts, end_ts)` | Cards active in a region in the window with no prior history there (+ fraud cases): region-cluster signal (R6) |
| `similar_cases(card, as_of, device_since)` | Structural memory: ClosedCases on same customer / connected card / shared (non-popular) device, tagged `why` |
| `case_vector_search(qv, k)` | ClosedCase by `notes_emb` similarity (weak for templated risk-score alerts; use as a secondary signal) |
| `policy_search(qv, k)` | GraphRAG over `PolicyChunk.emb` + linked patterns |
| `agent_case_memory(card, as_of, device_since)` | The agent's own earlier `AgentCase` write-backs (same customer / connected card / rare device), `opened_at < as_of` |
| `link_case(case_vid, …)` | Write-back: edges from an `AgentCase` to card, txns, connected cards, similar ClosedCases, pattern, devices (vertex + `summary_emb` via MCP `upsert_vectors`) |

**Pattern detection** runs in Python (`agent/scoring.py`) over these outputs rather than as 5 GSQL queries: tuning against the 20 cases needs fast iteration, and each GSQL change costs a ~1 min reinstall.

---

## 4. File structure

```
fraud-agent/
├── CLAUDE.md                  # this file
├── README.md
├── .env.example               # TG_*, LLM keys
├── requirements.txt
├── config/
│   ├── settings.py            # env loading, paths
│   ├── policy_matrix.yaml     # action -> auto | approval(role) | forbidden
│   └── thresholds.yaml        # risk bands, confidence threshold, max rounds
├── graph/
│   ├── schema.gsql
│   ├── loading_jobs.gsql
│   ├── queries/*.gsql
│   └── setup.py               # create schema, loading jobs, install queries
├── etl/
│   ├── prepare.py             # raw CSV -> vertex/edge CSVs
│   ├── load.py                # run loading jobs
│   ├── load_prior_cases.py    # months 1-4 cases -> Case vertices (memory)
│   └── ingest_docs.py         # policy/patterns/regs -> chunks + embeddings (GraphRAG)
├── agent/
│   ├── state.py               # CaseState (pydantic): the full case record
│   ├── workflow.py            # LangGraph wiring
│   ├── nodes/
│   │   ├── triage.py
│   │   ├── open_case.py
│   │   ├── gather_evidence.py
│   │   ├── assess.py
│   │   ├── request_evidence.py
│   │   ├── decide.py
│   │   ├── policy_gate.py
│   │   ├── explain.py         # summary + SAR
│   │   └── memory.py          # write-back + SIMILAR_TO edges
│   ├── tools/
│   │   ├── mcp_client.py      # tigergraph-mcp with allowlist
│   │   ├── actions.py         # mock action APIs
│   │   └── evidence_sources.py# simulated customer/analyst responses (README §5: assumed, recorded in evidence_requests)
│   ├── scoring.py             # risk + confidence
│   ├── rag.py                 # GraphRAG retrieval + context builder
│   ├── llm.py                 # provider wrapper
│   └── prompts/*.md
├── runner/
│   ├── run_benchmark.py       # 20 cases -> cases/
│   └── validate_answers.py    # checks against required answer format
├── ui/
│   └── app.py                 # Streamlit
├── cases/                     # submission output: <case_id>.json (README Answer Format)
├── docs/
│   └── blog.md
└── tests/
```

---

## 5. Build order (milestones)

| # | Milestone | Owner | Done when |
|---|---|---|---|
| M0 | Savanna up, `.env`, MCP connects, list tools | A | `list_graphs` works via MCP |
| M1 | Schema + ETL + load | A | vertex/edge counts match row counts |
| M2 | Doc ingestion (GraphRAG) + policy_matrix.yaml | B | top-k policy search returns sane chunks |
| M3 | Core GSQL queries + prior cases loaded | A | queries return for 3 sample cases |
| M4 | **Thin agent end-to-end** (no fancy loop) | A+B | 20 answer files produced & validate |
| M5 | Uncertainty loop, request_evidence, before/after NBA | A | 2 NBA snapshots in every answer |
| M6 | Streamlit UI + mock actions + approval buttons | B | full case walkthrough in UI |
| M7 | Accuracy pass on 20 cases, pattern detector tuning | A | — |
| M8 | Demo video, blog, social post, submit | B | submitted |

---

## 6. Working rules for Claude Code
- Work one milestone at a time; don't scaffold files for later milestones.
- Never guess dataset columns or answer format; read `$DATA_DIR/README.md` first.
- Keep LLM calls out of ETL and scoring.
- The agent must never call MCP tools outside the allowlist in `agent/tools/mcp_client.py`.
- Every node reads and returns `CaseState`; every node appends to `case.timeline`.