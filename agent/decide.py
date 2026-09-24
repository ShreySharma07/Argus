"""decide + policy_gate nodes: deterministic Fraud Policy engine (README "Fraud Policy" v1.0).

Input: the validated assessment (verdict/probability before and after evidence, pattern,
flags) and the exposure. Output: next_best_actions.initial / .final with the approval
route of every action (config/policy_matrix.yaml), evidence requests, the SAR decision
and the case status. The LLM never chooses actions or routes.
"""

from dataclasses import dataclass, field

from config.policy import route_for, threshold


@dataclass
class Plan:
    initial: list[dict] = field(default_factory=list)
    final: list[dict] = field(default_factory=list)
    evidence_requests: list[dict] = field(default_factory=list)
    sar_file: bool = False
    sar_reason: str = ""
    status: str = "open"
    verdict: str = "uncertain"
    probability: float = 0.5
    rules: list[str] = field(default_factory=list)


def _act(actions: list[dict], name: str, reason: str, exposure: float) -> None:
    if any(a["action"] == name for a in actions):
        return
    actions.append({"action": name, "route": route_for(name, exposure), "reason": reason})


def _sar(verdict: str, prob: float, exposure: float, a, linked: bool) -> tuple[bool, str]:
    """§3a: confirmed or strongly suspected fraud AND (exposure > $1,000 OR shared/linked origin OR undocumented)."""
    strong = verdict == "fraud" or prob >= 0.70
    if not strong:
        return False, f"No report: fraud not confirmed or strongly suspected (p={prob:.2f}); §3a requires it before filing."
    reasons = []
    if exposure > threshold("sar_exposure_usd"):
        reasons.append(f"exposure ${exposure:,.2f} exceeds $1,000 (§3a, R2)")
    if a.shared_origin or linked:
        reasons.append(f"activity connects to a shared origin / other customers' fraud ({a.shared_element or 'shared device'}) (§3a, R6)")
    if a.pattern == "undocumented":
        reasons.append("coordinated, undocumented pattern (R9)")
    if not reasons:
        return False, (f"Case only, no report: fraud with exposure ${exposure:,.2f} <= $1,000, no shared device/region link "
                       f"and a documented pattern, so no §3a condition holds.")
    return True, "File: " + "; ".join(reasons) + "."


def _fraud_actions(a, exposure: float, linked: bool, trigger: str, sig: dict, after_denial: bool) -> list[dict]:
    acts: list[dict] = []
    ct = sig.get("card_testing_runs") or []
    if a.pattern == "card_testing" and not after_denial:
        _act(acts, "DECLINE_TRANSACTION", "R5: card-testing sequence; decline pending authorizations", exposure)
        _act(acts, "STEP_UP_AUTH", "R5: require step-up before further activity", exposure)
        if ct and ct[0]["large_cleared_over_100"]:
            _act(acts, "BLOCK_CARD", f"R5: a purchase over $100 already cleared; exposure ${exposure:,.2f} "
                                     f"{'<=' if exposure <= 2500 else '>'} $2,500", exposure)
    else:
        why = "R2: customer denies the transaction" if after_denial or trigger == "customer_report" else \
              f"fraud confirmed by independent evidence (p>={threshold('stop_high_prob')})"
        _act(acts, "BLOCK_CARD", f"{why}; exposure ${exposure:,.2f} {'<=' if exposure <= 2500 else '>'} $2,500 "
                                 f"-> {route_for('BLOCK_CARD', exposure)}", exposure)
    if a.credentials_compromised and len(sig.get("customer_other_cards", [])) >= 1:
        _act(acts, "BLOCK_ALL_CARDS", "R10: customer credentials confirmed compromised", exposure)
    _act(acts, "CREATE_CASE", "R2/§3a: open the fraud case and write it to the graph", exposure)
    file, _ = _sar("fraud", 1.0, exposure, a, linked)
    if file:
        _act(acts, "FILE_REPORT", "§3a/R2/R6/R9: report conditions met (see sar.reason)", exposure)
    if a.connected_card_ids and (a.shared_origin or linked or a.pattern == "undocumented"):
        _act(acts, "MONITOR_CONNECTED_CARDS", f"R6: monitor {len(a.connected_card_ids)} card(s) sharing "
                                              f"{a.shared_element or 'the same origin'}", exposure)
    if a.pattern == "undocumented":
        _act(acts, "ESCALATE_TO_ANALYST", "R9: undocumented coordinated pattern; hand to an analyst with the evidence", exposure)
    return acts


def _legit_actions(a, exposure: float, trigger: str) -> list[dict]:
    acts: list[dict] = []
    if a.recurring_legit_charge and trigger == "customer_report":
        _act(acts, "CREATE_CASE", "R7/§3a: disputed charge; case records the dispute", exposure)
        _act(acts, "WARN_CUSTOMER", "R7: recurring-charge reminder; do not block", exposure)
        _act(acts, "CLOSE_NO_FRAUD", "R3: customer recognises the recurring charge", exposure)
        return acts
    if trigger == "customer_report":
        _act(acts, "CREATE_CASE", "§3a: every customer dispute opens a case", exposure)
    else:
        _act(acts, "ALLOW_TRANSACTION", "R3: activity is the cardholder's own; let the transaction stand", exposure)
    _act(acts, "CLOSE_NO_FRAUD", "R3: close the alert as legitimate and note the confirmation", exposure)
    return acts


def _uncertain_actions(a, exposure: float, trigger: str, no_reply: bool) -> list[dict]:
    acts: list[dict] = []
    _act(acts, "CREATE_CASE", "§3a: evidence requested / probability >= 0.30 -> case stays open", exposure)
    if no_reply:
        _act(acts, "MONITOR_CARD", "R4: no reply within 24h -> monitor the card", exposure)
        _act(acts, "DECLINE_TRANSACTION", "R4: decline pending authorizations while unresolved", exposure)
    else:
        _act(acts, "MONITOR_CARD", "R8: unresolved; raise monitoring for 72h", exposure)
    if exposure > threshold("r8_escalate_exposure_usd") or no_reply and exposure > threshold("r4_escalate_exposure_usd"):
        _act(acts, "ESCALATE_TO_ANALYST", f"R8/R4: uncertain with exposure ${exposure:,.2f} > $500", exposure)
    return acts


def _initial_with_request(a, exposure: float, trigger: str, sig: dict) -> list[dict]:
    """What we recommend while the requested evidence is pending (R1 / R5 / R7 / §3a)."""
    acts: list[dict] = []
    online = a.evidence_type == "step_up_auth"
    if a.pattern == "card_testing":
        _act(acts, "DECLINE_TRANSACTION", "R5: card-testing sequence; decline pending authorizations", exposure)
        _act(acts, "STEP_UP_AUTH", "R5: require step-up before further activity", exposure)
    elif a.recurring_legit_charge and trigger == "customer_report":
        _act(acts, "CREATE_CASE", "R7: dispute of a charge matching the cardholder's recurring pattern", exposure)
        _act(acts, "VERIFY_WITH_CUSTOMER", "R7: confirm the recurring merchant/amount with the customer", exposure)
        _act(acts, "WARN_CUSTOMER", "R7: send a recurring-charge reminder; do not block", exposure)
        return acts
    elif a.evidence_type == "analyst_info":
        _act(acts, "ESCALATE_TO_ANALYST", "§5: request information from an analyst before acting", exposure)
    else:
        name = "STEP_UP_AUTH" if online else "VERIFY_WITH_CUSTOMER"
        rule = "R1" if a.single_signal and a.probability_before < threshold("r1_weak_signal_max_prob") else "§5/§6"
        _act(acts, name, f"{rule}: p={a.probability_before:.2f} is not decisive; verify before any block", exposure)
    _act(acts, "CREATE_CASE", "§3a: a case is opened whenever evidence is requested", exposure)
    if a.probability_before >= 0.5 and a.pattern != "card_testing":
        _act(acts, "MONITOR_CARD", "R1: keep the card active but raise monitoring while verification is pending", exposure)
    if a.verdict_before == "uncertain" and exposure > threshold("r8_escalate_exposure_usd"):
        _act(acts, "ESCALATE_TO_ANALYST", f"R8: uncertain with exposure ${exposure:,.2f} > $500", exposure)
    return acts


def plan(a, trigger: str, exposure: float, sig: dict, linked: bool) -> Plan:
    p = Plan()
    if a.request_evidence and a.evidence_type != "none":
        p.evidence_requests = [{"type": a.evidence_type, "asked_after_step": 4, "assumed_response": a.assumed_response}]
        p.initial = _initial_with_request(a, exposure, trigger, sig)
        verdict, prob = a.verdict_after, a.probability_after
        denied = a.response_outcome in ("denies", "analyst_confirms_fraud")
        no_reply = a.response_outcome == "no_reply"
    else:
        verdict, prob = a.verdict_before, a.probability_before
        denied, no_reply = trigger == "customer_report", False

    if verdict == "fraud":
        p.final = _fraud_actions(a, exposure, linked, trigger, sig, after_denial=denied)
        esc = any(x["action"] == "ESCALATE_TO_ANALYST" for x in p.final)
        p.status = "escalated" if esc else "closed_fraud"
    elif verdict == "legitimate":
        p.final = _legit_actions(a, exposure, trigger)
        p.status = "closed_legitimate"
    else:
        p.final = _uncertain_actions(a, exposure, trigger, no_reply)
        p.status = "escalated" if any(x["action"] == "ESCALATE_TO_ANALYST" for x in p.final) else "open"

    if not p.evidence_requests:
        p.initial = [dict(x) for x in p.final]
    p.verdict, p.probability = verdict, round(min(max(prob, 0.0), 1.0), 2)
    p.sar_file, p.sar_reason = _sar(verdict, p.probability, exposure, a, linked)
    if p.sar_file and not any(x["action"] == "FILE_REPORT" for x in p.final):
        p.sar_file = False
        p.sar_reason = (f"No report yet: verdict is {verdict} (p={p.probability:.2f}); §3a requires confirmed or strongly "
                        f"suspected fraud, so the case is escalated/open and a report follows only if the analyst confirms.")
    if not p.sar_file and verdict == "legitimate":
        p.sar_reason = "No report: activity assessed as legitimate (R3); §3a filing conditions do not apply."
    return p
