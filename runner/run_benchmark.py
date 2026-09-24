"""Run the agent on the case pack -> cases/<case_id>.json (+ timelines in data/runs/).

    python -m runner.run_benchmark              # all 20
    python -m runner.run_benchmark HHG-001 ...  # selected cases
"""

import asyncio
import json
import logging
import sys
import traceback

import pandas as pd

from agent.tools.graph_tools import GraphTools
from agent.tools.mcp_client import TigerGraphMCP
from agent.workflow import run_case
from config.settings import CASES_DIR, DATA_DIR, ROOT

RUNS = ROOT / "runs"  # committed: the UI reads timelines from here


from agent import llm

# Gemini free tier is rate limited per minute: run cases one at a time (llm.py also paces calls).
WORKERS = 1 if llm.PROVIDER == "gemini" else 4
RETRY_PASSES = 2
RETRY_COOLDOWN_S = 90


async def _one(case: dict, sem: asyncio.Semaphore, failed: list) -> None:
    async with sem, TigerGraphMCP() as tg:  # one MCP session per in-flight case
        g = GraphTools(tg)
        try:
            answer, timeline = await run_case(g, case)
        except Exception as e:  # keep going: one bad case must not cost the other 19
            traceback.print_exc()
            failed.append(case["case_id"])
            print(f"{case['case_id']}: FAILED {e}", flush=True)
            return
    (CASES_DIR / f"{case['case_id']}.json").write_text(json.dumps(answer, indent=2))
    (RUNS / f"{case['case_id']}.timeline.json").write_text(json.dumps(timeline, indent=2))
    c, n = answer["case"], answer["next_best_actions"]
    print(f"{case['case_id']}: {c['verdict']:10} p={c['fraud_probability']:.2f} {c['pattern']:28} "
          f"exp=${c['exposure_usd']:>8} sar={answer['sar']['file']!s:5} "
          f"{[x['action'] for x in n['initial']]} -> {[x['action'] for x in n['final']]} "
          f"calls={answer['tool_calls']} tok={answer['tokens']} {answer['latency_s']}s", flush=True)


async def main(ids: list[str]) -> int:
    logging.disable(logging.WARNING)
    pack = pd.read_csv(DATA_DIR / "case_pack.csv", dtype=str).fillna("")
    if ids:
        pack = pack[pack.case_id.isin(ids)]
    CASES_DIR.mkdir(exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    cases = pack.to_dict("records")
    for case in cases:
        case["risk_score"] = float(case["risk_score"]) if case["risk_score"] else None
    failed: list[str] = []
    sem = asyncio.Semaphore(WORKERS)
    await asyncio.gather(*(_one(c, sem, failed) for c in cases))
    for attempt in range(RETRY_PASSES):  # transient provider outages: retry failed cases after a cool-down
        if not failed:
            break
        retry = [c for c in cases if c["case_id"] in failed]
        print(f"retry pass {attempt + 1}: {[c['case_id'] for c in retry]} after {RETRY_COOLDOWN_S}s", flush=True)
        await asyncio.sleep(RETRY_COOLDOWN_S)
        failed = []
        await asyncio.gather(*(_one(c, sem, failed) for c in retry))
    if failed:
        print("FAILED:", sorted(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
