"""assess node: Claude adjudicates the case from the deterministic brief + retrieved policy.

The LLM decides *what the evidence means* (pattern, verdict, calibrated probability,
which transactions/cards belong to the episode, what evidence to request and the most
likely response). It never picks actions or approval routes: decide.py does that
from policy. Every ID it returns is validated against the brief afterwards.
"""

import json
from typing import Literal

from pydantic import BaseModel, Field

from agent import llm

Pattern = Literal["card_testing", "card_not_present_fraud", "card_not_present_new_device",
                  "out_of_region_use", "account_takeover", "undocumented", "none"]
Verdict = Literal["fraud", "legitimate", "uncertain"]


class EvidenceItem(BaseModel):
    claim: str
    source: Literal["graph", "document", "customer", "external"]
    ref: str = Field(description="query name (e.g. 'query:card_activity'), policy section ('policy:R2'), memory case id, or 'evidence_request:1'")
    entity_ids: list[str]


class Assessment(BaseModel):
    rationale: str = Field(description="Justification for the case file: 3-6 sentences on which evidence drove the verdict")
    pattern: Pattern
    pattern_description: str = Field(description="2-3 sentences, only when pattern is undocumented, else empty")
    verdict_before: Verdict = Field(description="verdict from graph/memory evidence alone, before any requested evidence")
    probability_before: float
    independent_signals: int = Field(description="number of independent pieces of evidence supporting the verdict_before")
    single_signal: bool = Field(description="true if the case rests on one signal (e.g. risk score alone, or one unusual purchase)")
    affected_txn_ids: list[str] = Field(description="all txns in the fraud episode incl. the flagged one; empty if legitimate")
    first_suspicious_txn_id: str
    connected_card_ids: list[str] = Field(description="other cards in the same compromise/ring/device; from the brief only")
    connected_device_profiles: list[str] = Field(description="device profile strings linking this case to other cards")
    shared_origin: bool = Field(description="several cards show fraud from the same device profile / region / recipient in one window")
    shared_element: str
    recurring_legit_charge: bool = Field(description="disputed charge matches the cardholder's own recurring pattern (R7)")
    credentials_compromised: bool
    request_evidence: bool
    evidence_type: Literal["customer_validation", "step_up_auth", "analyst_info", "none"]
    evidence_reason: str
    assumed_response: str = Field(description="the simulated reply you assume, stated as a fact about what the customer/analyst said")
    response_outcome: Literal["denies", "confirms", "no_reply", "analyst_confirms_fraud", "analyst_clears", "none"]
    verdict_after: Verdict
    probability_after: float
    evidence: list[EvidenceItem]
    similar_prior_cases: list[str] = Field(description="closed-case IDs from memory you actually used")
    summary: str = Field(description="2-6 sentences an analyst could read")
    what_changed: str = Field(description="1-2 sentences on how the assessment moved after the evidence, or 'nothing'")
    stop_reason: str


SYSTEM = """You are a senior card-fraud investigator at a bank. You receive a structured evidence brief built from a
TigerGraph investigation (card baseline, transactions around the alert, device/region links to other cards, and the
bank's closed cases as memory) plus the relevant parts of the bank's Fraud Policy. Decide what the evidence means.

Ground rules:
- The model risk score is a reason to look, never a verdict. High scores are usually legitimate; some fraud scores low.
- About half of all alerts are legitimate. Blocking a legitimate customer is a real harm. Be calibrated: fraud_probability
  is scored for calibration, so 0.5 means genuinely unsure.
- Known patterns (README):
  1 card_testing: >=3 tiny online authorizations (often < $5) within an hour, then a larger purchase. The sequence itself confirms it.
  2 card_not_present_fraud: online amounts/products that don't fit the cardholder's history, often a burst of 2-4 within 48h.
    One unusual online purchase on its own is ambiguous: verify.
  3 card_not_present_new_device: pattern 2 plus the identity record marks the device New for this account, sometimes behind a
    proxy. Stronger than 2, still not proof: people buy new phones.
  4 out_of_region_use: card-present purchases in a billing region the cardholder has no history in, while their normal
    activity continues at home (a clone). Several days of purchases in one new region with home activity paused is a trip.
  5 account_takeover: mixed-channel activity inconsistent with the cardholder, often with device and match-flag anomalies
    (M4-M6, id_34), pointing to stolen credentials rather than a stolen number.
  undocumented: coordinated or repeated abuse that fits none of the five (e.g. one rare device profile used across several
    customers' cards, or several online purchases just under a round authorization threshold). Describe it in your own words.
  none: legitimate activity.
- Devices and regions connect people. A rare device profile (few cards all-time) shared by several cards in a short window,
  especially cards with confirmed fraud, is strong evidence of a shared origin. Common device strings mean nothing.
- Memory: closed cases on the same customer or linked by a rare device are strong context; say how their outcomes inform you.
- Customer and analyst replies are not provided. If the policy calls for more evidence (e.g. R1: single signal and
  probability < 0.70; R7: a disputed charge that matches a recurring pattern; genuinely conflicting evidence), set
  request_evidence and choose the most likely reply GIVEN THE EVIDENCE, stated plainly (e.g. "Customer confirms they are
  travelling in region 444 and made the purchase"). If the evidence is already decisive (>= 0.85 or <= 0.15 with at least
  two independent pieces), do not request anything.
- For a customer_report, the customer has already disputed the charge; that is one piece of evidence, not proof.
- Use ONLY transaction IDs, card IDs, device profile strings and closed-case IDs that appear in the brief. Never invent IDs.
- affected_txn_ids: every transaction you believe belongs to the same fraud episode on THIS card (flagged one included),
  none for a legitimate verdict. connected_card_ids: other cards in the same compromise/ring (from the brief).
- Evidence items: concrete claims with numbers, each citing its source and the entity IDs it rests on. Be honest about
  unnamed Vesta features. Use these refs: card_baseline_180d -> "query:card_profile"; flagged_txn / episode_window_txns ->
  "query:card_activity"; rare_shared_devices / cards_linked_by_rare_device -> "query:shared_devices"; region_cluster ->
  "query:region_newcomers"; memory_similar_cases -> "query:similar_cases"; semantic memory -> "query:case_vector_search";
  policy text -> "policy:R2" / "policy:s3a" (source "document"); the assumed reply -> "evidence_request:1" (source "customer").
"""


def _policy_context(rag_hits: list[dict], rules: list[dict]) -> str:
    parts = [f"[{r['id']}] {r['text']}" for r in rules]
    parts += [f"[{h['id']}] {h['text']}" for h in rag_hits if h["id"] not in {r["id"] for r in rules}]
    return "\n\n".join(parts)


def assess(brief: dict, memory_vector: list[dict], policy_text: str, usage: llm.Usage) -> Assessment:
    user = (
        "FRAUD POLICY (retrieved from the knowledge graph):\n" + policy_text +
        "\n\nEVIDENCE BRIEF (from TigerGraph):\n" + json.dumps(brief, default=str, indent=1) +
        "\n\nSEMANTICALLY SIMILAR CLOSED CASES (vector search over analyst notes; weaker than structural links):\n" +
        json.dumps(memory_vector, indent=1) +
        "\n\nAssess this case."
    )
    return llm.parse(SYSTEM, user, Assessment, usage, effort="high")


policy_context = _policy_context
