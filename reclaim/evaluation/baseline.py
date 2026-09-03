"""
Baseline recovery strategy for comparison.

Simple, no-diagnosis approach:
  - Payment failures → one retry_payment attempt
  - Checkout abandonment → one reminder_message attempt
  - If unresolved, stop. No scoring, no adaptation.

Uses the same Executor/simulator and seeds as RECLAIM for fair comparison.
"""

import json
import random


def run_baseline(cases: list[dict], seed: int = 42) -> dict:
    """
    Run the baseline strategy on the given batch of cases.

    Returns a results dict with:
      - outcomes: list of {case_id, action, recovered, amount}
      - total_recovered: float
      - recovery_rate: float
      - recovery_count: int
    """
    outcomes = []

    for case in cases:
        case_id = case["case_id"]
        amount = case["amount"]
        scenario = case["scenario"]
        hidden_probs = json.loads(case["hidden_probabilities"])

        # Baseline picks one fixed action based on scenario type
        if scenario == "payment_failure":
            action = "retry_payment"
        else:
            action = "reminder_message"

        # Deterministic outcome using case_id-based seed (same as Executor)
        case_rng = random.Random(hash((case_id, action, 0)))
        true_prob = hidden_probs.get(action, 0.0)
        recovered = case_rng.random() < true_prob

        outcomes.append({
            "case_id": case_id,
            "scenario": scenario,
            "action": action,
            "recovered": recovered,
            "amount": amount,
        })

    recovery_count = sum(1 for o in outcomes if o["recovered"])
    total_recovered = sum(o["amount"] for o in outcomes if o["recovered"])
    recovery_rate = recovery_count / len(cases) if cases else 0.0

    return {
        "outcomes": outcomes,
        "total_recovered": round(total_recovered, 2),
        "recovery_rate": round(recovery_rate, 4),
        "recovery_count": recovery_count,
        "total_cases": len(cases),
    }


if __name__ == "__main__":
    # Quick test: generate cases and run baseline
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from reclaim.data.generator import generate_cases

    cases = generate_cases()
    results = run_baseline(cases)
    print(f"Baseline results on {results['total_cases']} cases:")
    print(f"  Recovery count: {results['recovery_count']}")
    print(f"  Recovery rate:  {results['recovery_rate']:.2%}")
    print(f"  Total ₹ recovered: ₹{results['total_recovered']:,.2f}")
