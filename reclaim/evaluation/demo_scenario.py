"""
Demo Scenario Walkthrough Script.

Walks a single case through every stage of the RECLAIM agent pipeline with
verbose printed output, designed for demo presentations and video walkthroughs:
  1. Event Ingestion & Context Display
  2. Risk Detector Scoring (0–1 priority score)
  3. Root Cause Analysis (Deterministic RCA Lookup)
  4. Policy Agent Candidate Proposal (Allowlist verification)
  5. Confidence-Aware ERV Scoring (Beta posterior mean & expected value)
  6. Guardrail Check (Confidence floor, max retries, allowlist assertion)
  7. Executor Simulation (Deterministic outcome)
  8. Posterior Update & Belief Sharpening
  9. SQLite Audit Trail Logging & History Inspection

Supports `--force-failure` to demonstrate failure injection, the re-evaluation loop,
and compliant stopping / escalation rules.
"""

import sys
import os
import argparse
import json
import sqlite3

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from reclaim.data.generator import generate_cases, init_db
from reclaim.agents.risk_detector import compute_risk_score
from reclaim.agents.rca import classify
from reclaim.agents.policy_agent import get_candidates
from reclaim.agents.erv_scorer import ERVScorer
from reclaim.agents.guardrails import check, GuardrailResult, MAX_ATTEMPTS as guardrails_max
from reclaim.core.state_machine import CaseStateMachine, CaseState
from reclaim.core.executor import SimulatedExecutor
from reclaim.core.audit import AuditTrail


def run_demo(case_id: str | None = None, force_failure: bool = False):
    print("\n" + "=" * 80)
    print("           RECLAIM: AI REVENUE RECOVERY AGENT — LIVE DEMO WALKTHROUGH")
    print("=" * 80)

    # 1. Load case batch
    cases = generate_cases(seed=42)
    if case_id:
        selected = next((c for c in cases if c["case_id"] == case_id), None)
        if not selected:
            print(f"Error: Case {case_id} not found.")
            return
    else:
        # Pick a rich interesting case: e.g. payment_method abandonment or technical decline
        if force_failure:
            # Pick a case with insufficient funds to show retry exhaustion
            selected = next(c for c in cases if c.get("decline_reason") == "insufficient_funds")
        else:
            # Pick a case with technical_decline or payment_method
            selected = next(c for c in cases if c.get("abandonment_step") == "payment_method")

    db_file = os.path.join(REPO_ROOT, "reclaim_demo.db")
    conn = init_db(db_file)
    audit = AuditTrail(conn)
    scorer = ERVScorer()

    # Pre-warm scorer with a few prior observations to simulate an active pipeline
    for _ in range(6):
        scorer.update("payment_friction", "alternate_payment_method", True)
        scorer.update("retry_likely_to_succeed", "retry_payment", True)
        scorer.update("customer_action_needed", "alternate_payment_method", True)
    for _ in range(2):
        scorer.update("payment_friction", "reminder_message", False)

    executor = SimulatedExecutor()
    sm = CaseStateMachine(selected["case_id"])

    print("\n[STAGE 1: AT-RISK EVENT INGESTED]")
    print(f"  • Case ID:            {selected['case_id']}")
    print(f"  • Scenario:           {selected['scenario']}")
    if selected['scenario'] == 'payment_failure':
        print(f"  • Decline Reason:     {selected['decline_reason']}")
        print(f"  • Retries So Far:     {selected['retry_count_so_far']}")
    else:
        print(f"  • Abandonment Step:   {selected['abandonment_step']}")
        print(f"  • Time Elapsed:       {selected['minutes_since_abandonment']} minutes")
    print(f"  • Transaction Amount: ₹{selected['amount']:,.2f}")
    hidden = json.loads(selected["hidden_probabilities"])
    print(f"  • Hidden True Probs:  {hidden}  (Hidden from agent!)")

    # STAGE 2: Risk Scoring
    print("\n[STAGE 2: RISK DETECTOR PRIORITY SCORING]")
    risk_score = compute_risk_score(selected)
    print(f"  • Computed Risk Score: {risk_score:.4f} / 1.0000")
    urgency = "HIGH" if risk_score > 0.65 else ("MEDIUM" if risk_score > 0.4 else "LOW")
    print(f"  • Priority Band:       {urgency} urgency for recovery")

    # STAGE 3: RCA
    print("\n[STAGE 3: ROOT CAUSE ANALYSIS (RCA)]")
    sm.transition(CaseState.DIAGNOSED)
    root_cause = classify(selected)
    print(f"  • State Machine:       {sm.history[-1][0].value} ➔ {sm.state.value}")
    print(f"  • Diagnosed Root Cause:{root_cause}")

    # STAGE 4: Policy Agent
    print("\n[STAGE 4: RECOVERY POLICY AGENT]")
    candidates = get_candidates(root_cause)
    print(f"  • Defense-Only Candidates Proposed:")
    for i, c in enumerate(candidates, 1):
        print(f"      {i}. {c}")

    # STAGE 5 & 6: Scoring & Execution Loop
    attempts = 0
    resolved = False

    while attempts < 3 and not resolved:
        print(f"\n--- [CYCLE ATTEMPT #{attempts + 1}] ---")
        sm.transition(CaseState.SCORED)
        print(f"  • State Machine:       ➔ {sm.state.value}")

        print("  • ERV Scorer Candidate Evaluations:")
        ranked = scorer.score_all(root_cause, candidates, selected["amount"])
        for r in ranked:
            print(f"      - {r['action']:<25} | ERV: ₹{r['erv']:>9.2f} | P(rec): {r['p_recovery']:.2%} | Conf: {r['confidence']:.0f} obs")

        best_action, best_erv, confidence = scorer.select_best(root_cause, candidates, selected["amount"])
        print(f"  ★ Selected Best Action: {best_action} (ERV: ₹{best_erv:,.2f})")

        # Guardrail Check
        sm.transition(CaseState.AWAITING_APPROVAL)
        g_res, g_reason = check(best_action, confidence, attempts)
        print(f"  • Guardrail Engine Check: {g_res.value.upper()} — {g_reason}")

        if g_res == GuardrailResult.ESCALATE:
            sm.transition(CaseState.ESCALATED)
            audit.log_decision(
                selected["case_id"], root_cause, best_action, confidence, "escalated", g_reason
            )
            print(f"  ➔ Case ESCALATED to Human Review Queue. [TERMINAL]")
            resolved = True
            break

        elif g_res == GuardrailResult.APPROVE:
            sm.transition(CaseState.EXECUTING)
            print(f"  • State Machine:       ➔ {sm.state.value}")

            # Execution
            if force_failure:
                print(f"  ⚡ [SIMULATOR] Action executed under --force-failure injection.")
                recovered = executor.execute(selected, best_action, attempts, force_failure=True)
            else:
                recovered = executor.execute(selected, best_action, attempts)

            attempts += 1
            scorer.update(root_cause, best_action, recovered)

            if "razorpay_payment_link" in selected:
                link = selected["razorpay_payment_link"]
                print(f"  🔗 [RAZORPAY TEST API] Real Payment Link: {link.get('short_url')} (ID: {link.get('id')})")

            if recovered:
                sm.transition(CaseState.RECOVERED)
                audit.log_decision(
                    selected["case_id"], root_cause, best_action, confidence, "recovered"
                )
                print(f"  ✔ Outcome: SUCCESSFUL RECOVERY! ₹{selected['amount']:,.2f} recovered.")
                print(f"  • State Machine:       ➔ {sm.state.value} [TERMINAL]")
                resolved = True
                break
            else:
                print(f"  ✖ Outcome: Attempt Failed (Unresolved).")
                # Re-check guardrails after incrementing attempts —
                # single source of truth for the attempt cap
                g_stop_res, g_stop_reason = check(best_action, confidence, attempts)
                if g_stop_res == GuardrailResult.STOP:
                    sm.transition(CaseState.STOPPED)
                    audit.log_decision(
                        selected["case_id"], root_cause, best_action, confidence, "stopped",
                        g_stop_reason
                    )
                    print(f"  ➔ Attempts exhausted ({attempts}/{guardrails_max}). Case STOPPED. [TERMINAL]")
                    resolved = True
                    break
                else:
                    audit.log_decision(
                        selected["case_id"], root_cause, best_action, confidence, "not_recovered"
                    )
                    print(f"  ➔ Re-evaluating case: looping back with updated posterior beliefs...")

    # STAGE 7: Audit Trail verification
    print("\n[STAGE 7: AUDIT TRAIL LOG VERIFICATION]")
    history = audit.get_case_history(selected["case_id"])
    print(f"Audit log rows recorded for {selected['case_id']} in SQLite:")
    for h in history:
        print(f"  [{h['timestamp']}] Action: {h['action_taken']:<25} | Outcome: {h['outcome']:<13} | Conf: {h['confidence_at_decision']:<4} | Stop Reason: {h['stop_reason']}")

    # STAGE 8: LLM Narrator (additive only — after all decisions are finalized)
    from reclaim.agents.narrator import draft_customer_message, draft_escalation_briefing

    final_state = sm.state.value
    # Get the last action and confidence from the most recent audit entry
    last_entry = history[-1] if history else {}
    last_action = last_entry.get("action_taken", "")
    last_confidence = last_entry.get("confidence_at_decision", 0)
    last_reason = last_entry.get("stop_reason", "")

    if sm.state == CaseState.ESCALATED:
        print("\n[STAGE 8: LLM NARRATOR — ESCALATION BRIEFING]")
        briefing = draft_escalation_briefing(
            selected, root_cause, float(last_confidence), last_reason or ""
        )
        print(briefing)
    elif last_action in ("reminder_message", "otp_assist_link"):
        print("\n[STAGE 8: LLM NARRATOR — CUSTOMER MESSAGE DRAFT]")
        msg = draft_customer_message(selected, root_cause, last_action)
        print(msg)
    else:
        print("\n[STAGE 8: LLM NARRATOR — No narration needed for this action type]")

    conn.close()
    if os.path.exists(db_file):
        os.remove(db_file)

    print("\n" + "=" * 80)
    print("                    DEMO WALKTHROUGH COMPLETE")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RECLAIM Single-Case Demo Walkthrough")
    parser.add_argument("--case-id", type=str, help="Specific Case ID to run (e.g. PF-0001, CA-0028)")
    parser.add_argument("--force-failure", action="store_true", help="Force failure injection to demonstrate retries and stopping rules")
    args = parser.parse_args()

    run_demo(case_id=args.case_id, force_failure=args.force_failure)
