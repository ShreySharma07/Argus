"""request_evidence backends: simulated cardholder / analyst replies (README §5).

The dataset provides no replies, so the policy-approved request is answered by a simulator that
role-plays the party asked, using only the observable account facts. The simulator is a separate
call from the assessor, is told nothing about the assessor's verdict, and its reply is recorded
verbatim in `evidence_requests[].assumed_response` as the stated assumption.
"""

import json
from typing import Literal

from pydantic import BaseModel, Field

from agent import llm

RequestType = Literal["customer_validation", "step_up_auth", "analyst_info"]


PRONOUNS = ("\nRefer to the cardholder as 'the cardholder' or 'they'; the dataset gives no gender, so never use he/she.")


class Reply(BaseModel):
    outcome: Literal["denies", "confirms", "no_reply", "analyst_confirms_fraud", "analyst_clears", "analyst_inconclusive"]
    text: str = Field(description="the reply as it would be recorded in the case file, one or two sentences")


SYSTEM = {
    "customer_validation": """You simulate the genuine cardholder being asked by their bank whether they made a transaction.
Answer as that person would, based only on the account facts provided: their normal spending, regions, devices, recurring
charges, and whether the activity fits their own behaviour or looks like someone else's. A genuine cardholder confirms
purchases that fit their life (travel they took, a new phone they bought, a subscription they forgot) and denies ones made
by someone else. If the facts suggest they would plausibly not see or answer the message within 24 hours, you may choose
no_reply, but prefer a clear answer when the facts support one.""",
    "step_up_auth": """You simulate the result of a step-up authentication challenge (one-time passcode to the cardholder's
registered phone) sent before further activity. The genuine cardholder passes it (outcome "confirms") when the activity is
theirs; a fraudster using a stolen number cannot (outcome "denies", recorded as a failed/abandoned challenge). Decide from
the account facts which is more plausible.""",
    "analyst_info": """You simulate a senior fraud analyst asked to review linked evidence (shared devices, regions, other
cards, prior closed cases). Give a professional judgement from the facts provided: analyst_confirms_fraud,
analyst_clears, or analyst_inconclusive.""",
}


def simulate(kind: RequestType, brief: dict, question: str, usage: llm.Usage) -> Reply:
    facts = {k: brief[k] for k in ("case", "card_baseline_180d", "flagged_txn", "episode_window_txns", "signals",
                                   "rare_shared_devices", "cards_linked_by_rare_device", "region_cluster")}
    if kind == "analyst_info":
        facts["memory_similar_cases"] = brief["memory_similar_cases"]
    user = f"QUESTION FROM THE BANK: {question}\n\nACCOUNT FACTS:\n{json.dumps(facts, default=str, indent=1)}"
    return llm.parse(SYSTEM[kind] + PRONOUNS, user, Reply, usage, effort="low", max_tokens=4000)
