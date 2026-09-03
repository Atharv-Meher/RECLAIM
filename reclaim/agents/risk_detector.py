"""
Risk Detector for RECLAIM.

Produces a 0–1 risk score for each case. Every case is already known to be
at-risk (created by an upstream signal); this score prioritizes cases for
the audit trail and any human review queue.

Rule-based: weighted combination of amount, retry/time factors, and
decline-reason / abandonment-step severity.
"""

# ── Severity weights for decline reasons ────────────────────────────────────
_DECLINE_SEVERITY = {
    "risky_transaction": 0.95,
    "insufficient_funds": 0.60,
    "card_expired": 0.55,
    "gateway_timeout": 0.40,
    "technical_decline": 0.30,
}

# ── Severity weights for abandonment steps ──────────────────────────────────
# Later steps = customer was more committed = higher urgency to recover
_ABANDONMENT_SEVERITY = {
    "otp": 0.90,
    "payment_method": 0.70,
    "address": 0.40,
    "cart": 0.25,
}

# ── Normalization constants ─────────────────────────────────────────────────
_MAX_AMOUNT = 20000.0      # upper bound for amount normalization
_MAX_RETRIES = 2           # max retry_count_so_far
_MAX_MINUTES = 120.0       # max minutes_since_abandonment

# ── Component weights in the final score ────────────────────────────────────
_W_AMOUNT = 0.30
_W_SIGNAL = 0.45
_W_URGENCY = 0.25


def compute_risk_score(case: dict) -> float:
    """
    Compute a 0–1 risk score for a case.

    Higher score = higher priority for intervention.

    Components:
      - amount_factor: larger amounts → higher risk (more revenue at stake)
      - signal_factor: decline reason or abandonment step severity
      - urgency_factor: retry count (payment) or time elapsed (abandonment)
    """
    amount = case["amount"]
    scenario = case["scenario"]

    # Amount factor: normalized to [0, 1], clamped
    amount_factor = min(amount / _MAX_AMOUNT, 1.0)

    if scenario == "payment_failure":
        # Signal severity from decline reason
        signal_factor = _DECLINE_SEVERITY.get(case["decline_reason"], 0.5)

        # Urgency: more retries = higher urgency (running out of chances)
        retry_count = case.get("retry_count_so_far", 0) or 0
        urgency_factor = retry_count / _MAX_RETRIES

    elif scenario == "checkout_abandonment":
        # Signal severity from abandonment step
        signal_factor = _ABANDONMENT_SEVERITY.get(case["abandonment_step"], 0.5)

        # Urgency: more time elapsed = customer cooling off = higher risk
        minutes = case.get("minutes_since_abandonment", 0) or 0
        urgency_factor = min(minutes / _MAX_MINUTES, 1.0)

    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    # Weighted combination, clamped to [0, 1]
    score = (
        _W_AMOUNT * amount_factor
        + _W_SIGNAL * signal_factor
        + _W_URGENCY * urgency_factor
    )
    return round(min(max(score, 0.0), 1.0), 4)


def score_batch(cases: list[dict]) -> list[dict]:
    """
    Score a batch of cases in-place, adding 'risk_score' to each case dict.
    Returns the cases sorted by risk_score descending (highest priority first).
    """
    for case in cases:
        case["risk_score"] = compute_risk_score(case)
    return sorted(cases, key=lambda c: c["risk_score"], reverse=True)
