"""
Root Cause Classifier for RECLAIM.

A fixed lookup table mapping structured event codes (decline reasons,
abandonment steps) to root-cause categories. Deterministic on purpose:
the synthetic generator controls these codes, so a learned classifier
would add complexity with no benefit.
"""

# ── Root cause lookup table ─────────────────────────────────────────────────
# Maps the signal (decline_reason or abandonment_step) to a root cause label.
# This is the complete, authoritative mapping — see build brief §4.3.

_SIGNAL_TO_ROOT_CAUSE = {
    # Payment failure signals
    "technical_decline": "retry_likely_to_succeed",
    "gateway_timeout": "retry_likely_to_succeed",
    "insufficient_funds": "customer_action_needed",
    "card_expired": "customer_action_needed",
    "risky_transaction": "requires_verification",
    # Checkout abandonment signals
    "cart": "low_intent_drop_off",
    "address": "low_intent_drop_off",
    "payment_method": "payment_friction",
    "otp": "otp_friction",
}

# All valid root cause labels (for validation)
ROOT_CAUSES = sorted(set(_SIGNAL_TO_ROOT_CAUSE.values()))


def classify(case: dict) -> str:
    """
    Classify a case into a root cause category.

    Args:
        case: A case dict with 'scenario' and either 'decline_reason'
              or 'abandonment_step'.

    Returns:
        A root cause label string.

    Raises:
        ValueError: If the signal is not in the lookup table.
    """
    if case["scenario"] == "payment_failure":
        signal = case["decline_reason"]
    elif case["scenario"] == "checkout_abandonment":
        signal = case["abandonment_step"]
    else:
        raise ValueError(f"Unknown scenario: {case['scenario']}")

    root_cause = _SIGNAL_TO_ROOT_CAUSE.get(signal)
    if root_cause is None:
        raise ValueError(f"Unknown signal '{signal}' — not in RCA lookup table")

    return root_cause


def get_signal(case: dict) -> str:
    """Extract the signal (decline_reason or abandonment_step) from a case."""
    if case["scenario"] == "payment_failure":
        return case["decline_reason"]
    else:
        return case["abandonment_step"]
