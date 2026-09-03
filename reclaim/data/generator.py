"""
Synthetic case generator for RECLAIM.

Generates ~280 cases (140 payment_failure + 140 checkout_abandonment),
each with hidden true recovery probabilities used only by the Executor.
All randomness is seeded for reproducibility.
"""

import json
import random
import sqlite3
import os
from pathlib import Path

SEED = 42

# ── Action allowlist (reference, used for hidden probability keys) ──────────
ACTIONS = [
    "retry_payment",
    "alternate_payment_method",
    "reminder_message",
    "otp_assist_link",
    "manual_escalation",
]

# ── Decline reasons and abandonment steps ───────────────────────────────────
DECLINE_REASONS = [
    "insufficient_funds",
    "card_expired",
    "risky_transaction",
    "technical_decline",
    "gateway_timeout",
]

ABANDONMENT_STEPS = ["cart", "address", "payment_method", "otp"]

# ── Hidden true recovery probabilities by signal ────────────────────────────
# These are the TRUE probabilities the Executor uses to draw outcomes.
# The ERV Scorer never sees these — it learns from observed outcomes only.
#
# Design: each signal has a "best" action with a high probability, and
# the others are low. This creates a learning signal the Bayesian scorer
# can pick up across the batch.

HIDDEN_PROBS_BY_SIGNAL = {
    # payment_failure signals
    "technical_decline": {
        "retry_payment": 0.78,
        "alternate_payment_method": 0.15,
        "reminder_message": 0.08,
        "otp_assist_link": 0.05,
        "manual_escalation": 0.30,
    },
    "gateway_timeout": {
        "retry_payment": 0.72,
        "alternate_payment_method": 0.12,
        "reminder_message": 0.06,
        "otp_assist_link": 0.04,
        "manual_escalation": 0.25,
    },
    "insufficient_funds": {
        "retry_payment": 0.10,
        "alternate_payment_method": 0.45,
        "reminder_message": 0.35,
        "otp_assist_link": 0.05,
        "manual_escalation": 0.20,
    },
    "card_expired": {
        "retry_payment": 0.05,
        "alternate_payment_method": 0.48,
        "reminder_message": 0.30,
        "otp_assist_link": 0.05,
        "manual_escalation": 0.18,
    },
    "risky_transaction": {
        "retry_payment": 0.05,
        "alternate_payment_method": 0.08,
        "reminder_message": 0.06,
        "otp_assist_link": 0.03,
        "manual_escalation": 0.15,
    },
    # checkout_abandonment signals
    "cart": {
        "retry_payment": 0.05,
        "alternate_payment_method": 0.10,
        "reminder_message": 0.25,
        "otp_assist_link": 0.03,
        "manual_escalation": 0.12,
    },
    "address": {
        "retry_payment": 0.05,
        "alternate_payment_method": 0.12,
        "reminder_message": 0.28,
        "otp_assist_link": 0.04,
        "manual_escalation": 0.14,
    },
    "payment_method": {
        "retry_payment": 0.10,
        "alternate_payment_method": 0.55,
        "reminder_message": 0.30,
        "otp_assist_link": 0.08,
        "manual_escalation": 0.18,
    },
    "otp": {
        "retry_payment": 0.40,
        "alternate_payment_method": 0.20,
        "reminder_message": 0.15,
        "otp_assist_link": 0.65,
        "manual_escalation": 0.22,
    },
}


def _get_signal(case: dict) -> str:
    """Extract the signal key from a case (decline_reason or abandonment_step)."""
    if case["scenario"] == "payment_failure":
        return case["decline_reason"]
    else:
        return case["abandonment_step"]


def generate_cases(seed: int = SEED) -> list[dict]:
    """
    Generate ~280 synthetic cases, roughly balanced between payment_failure
    and checkout_abandonment. Returns a list of case dicts.
    """
    rng = random.Random(seed)
    cases = []

    # ── Payment failures: 140 cases ─────────────────────────────────────
    for i in range(140):
        decline_reason = rng.choice(DECLINE_REASONS)
        case = {
            "case_id": f"PF-{i+1:04d}",
            "scenario": "payment_failure",
            "decline_reason": decline_reason,
            "retry_count_so_far": rng.randint(0, 2),
            "abandonment_step": None,
            "minutes_since_abandonment": None,
            "amount": round(rng.uniform(200, 15000), 2),
            "hidden_probabilities": json.dumps(
                HIDDEN_PROBS_BY_SIGNAL[decline_reason]
            ),
        }
        cases.append(case)

    # ── Checkout abandonments: 140 cases ────────────────────────────────
    for i in range(140):
        abandonment_step = rng.choice(ABANDONMENT_STEPS)
        case = {
            "case_id": f"CA-{i+1:04d}",
            "scenario": "checkout_abandonment",
            "decline_reason": None,
            "retry_count_so_far": None,
            "abandonment_step": abandonment_step,
            "minutes_since_abandonment": round(rng.uniform(2, 120), 1),
            "amount": round(rng.uniform(300, 20000), 2),
            "hidden_probabilities": json.dumps(
                HIDDEN_PROBS_BY_SIGNAL[abandonment_step]
            ),
        }
        cases.append(case)

    return cases


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize the SQLite database with the schema."""
    schema_path = Path(__file__).parent / "schema.sql"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
    return conn


def save_cases_to_db(conn: sqlite3.Connection, cases: list[dict]) -> None:
    """Insert generated cases into the database."""
    conn.executemany(
        """
        INSERT OR REPLACE INTO cases
            (case_id, scenario, decline_reason, retry_count_so_far,
             abandonment_step, minutes_since_abandonment, amount,
             hidden_probabilities)
        VALUES
            (:case_id, :scenario, :decline_reason, :retry_count_so_far,
             :abandonment_step, :minutes_since_abandonment, :amount,
             :hidden_probabilities)
        """,
        cases,
    )
    conn.commit()


def load_cases_from_db(conn: sqlite3.Connection) -> list[dict]:
    """Load all cases from the database as a list of dicts."""
    cursor = conn.execute("SELECT * FROM cases ORDER BY case_id")
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


def generate_and_save(db_path: str = "reclaim.db", seed: int = SEED) -> list[dict]:
    """Generate cases, save to DB, and return them."""
    conn = init_db(db_path)
    cases = generate_cases(seed)
    save_cases_to_db(conn, cases)
    conn.close()
    return cases


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "reclaim.db")
    db_path = os.path.normpath(db_path)
    cases = generate_and_save(db_path)
    print(f"Generated {len(cases)} cases and saved to {db_path}")

    # Print summary
    pf = sum(1 for c in cases if c["scenario"] == "payment_failure")
    ca = sum(1 for c in cases if c["scenario"] == "checkout_abandonment")
    print(f"  Payment failures: {pf}")
    print(f"  Checkout abandonments: {ca}")

    # Show a sample case
    sample = cases[0]
    print(f"\nSample case: {sample['case_id']}")
    for k, v in sample.items():
        if k == "hidden_probabilities":
            print(f"  {k}: {json.loads(v)}")
        else:
            print(f"  {k}: {v}")
