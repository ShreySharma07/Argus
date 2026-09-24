"""explain node: the SAR narrative (FinCEN who/what/when/where/how/why), grounded in retrieved guidance."""

import json

from pydantic import BaseModel, Field

from agent import llm


class SarDraft(BaseModel):
    narrative: str = Field(description="6-12 sentences, stands on its own: who, what, when, where, how, why suspicious")
    subjects: list[str] = Field(description="IDs of customers, cards and device profiles named in the narrative")


SYSTEM = """You write Suspicious Activity Report narratives for a bank's fraud team, following FinCEN narrative guidance:
a regulator must understand the activity without any other document. Cover WHO (customer and card IDs, linked cards,
device profiles), WHAT happened, WHEN (dates and times), WHERE (channel, billing region, device), HOW it was carried out,
and WHY it is suspicious, then the total amount and the actions taken. 6-12 sentences, plain factual prose, no
speculation beyond the evidence, no headings or bullet points. Use only the IDs and figures given. Refer to the
customer as "the cardholder" or "they", never he/she (the data gives no gender)."""


def draft_sar(record: dict, guidance: list[dict], usage: llm.Usage) -> SarDraft:
    user = ("SAR NARRATIVE GUIDANCE (retrieved):\n" + "\n\n".join(f"[{g['id']}] {g['text']}" for g in guidance) +
            "\n\nCASE RECORD:\n" + json.dumps(record, default=str, indent=1) + "\n\nWrite the SAR narrative.")
    return llm.parse(SYSTEM, user, SarDraft, usage, effort="medium", max_tokens=8000)
