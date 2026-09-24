"""Mock action APIs behind the policy gate (card management, customer messaging, case system, regulator).

`auto` actions may be executed by the agent; `L1` / `L2` actions wait for a human with the right role
(policy §2). Every execution and approval is appended to runs/actions_log.jsonl with actor and time,
so the case record shows who did what.
"""

import json
from datetime import datetime, timezone

from config.settings import ROOT

LOG = ROOT / "runs" / "actions_log.jsonl"

# Which roles may approve which route. A fraud manager can approve anything a team lead can.
CAN_APPROVE = {"L1": {"L1", "L2"}, "L2": {"L2"}}
ROLES = {"analyst": "Fraud analyst", "L1": "Team lead (L1)", "L2": "Fraud manager (L2)", "agent": "Argus agent"}

EFFECT = {
    "ALLOW_TRANSACTION": "Authorization {txn} released",
    "DECLINE_TRANSACTION": "Pending authorizations on {card} declined; card stays active",
    "MONITOR_CARD": "{card} monitoring sensitivity raised for 72h",
    "MONITOR_CONNECTED_CARDS": "{n_connected} connected card(s) placed under monitoring",
    "WARN_CUSTOMER": "Informational message sent to {customer}",
    "VERIFY_WITH_CUSTOMER": "Verification request sent to {customer}",
    "STEP_UP_AUTH": "Step-up authentication required on {card}",
    "BLOCK_CARD": "{card} blocked; reissue ordered",
    "BLOCK_ALL_CARDS": "All cards of {customer} blocked",
    "GENERATE_REPORT": "Internal report generated",
    "CREATE_CASE": "Case {graph_case_id} opened in the case system",
    "FILE_REPORT": "SAR for {case_id} submitted to the regulator",
    "ESCALATE_TO_ANALYST": "Case handed to the analyst queue with evidence",
    "CLOSE_NO_FRAUD": "Alert closed as legitimate",
}


class NotAuthorized(PermissionError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def history(case_id: str | None = None) -> list[dict]:
    if not LOG.exists():
        return []
    rows = [json.loads(line) for line in LOG.read_text().splitlines() if line.strip()]
    return [r for r in rows if case_id is None or r["case_id"] == case_id]


def _effect(action: str, answer: dict, case: dict) -> str:
    c = answer["case"]
    return EFFECT[action].format(txn=case.get("flagged_txn_id", ""), card=case.get("card_id", ""),
                                 customer=case.get("customer_id", ""), case_id=answer["case_id"],
                                 graph_case_id=c.get("graph_case_id", ""),
                                 n_connected=len(c.get("connected_card_ids", [])))


def execute(answer: dict, case: dict, action: str, role: str) -> dict:
    """Execute a final-plan action. auto -> anyone (incl. the agent); L1/L2 -> an approver with that authority."""
    final = {a["action"]: a for a in answer["next_best_actions"]["final"]}
    if action not in final:
        raise NotAuthorized(f"{action} is not in the final plan for {answer['case_id']}")
    route = final[action]["route"]
    if any(r["action"] == action and r["status"] == "executed" for r in history(answer["case_id"])):
        raise NotAuthorized(f"{action} already executed")
    if route != "auto" and role not in CAN_APPROVE[route]:
        raise NotAuthorized(f"{action} needs {route} approval; {ROLES.get(role, role)} cannot approve it")
    row = {"ts": _now(), "case_id": answer["case_id"], "action": action, "route": route, "actor": role,
           "actor_label": ROLES.get(role, role), "status": "executed", "effect": _effect(action, answer, case),
           "mock": True}
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row
