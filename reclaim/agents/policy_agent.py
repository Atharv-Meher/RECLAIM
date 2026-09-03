"""
Recovery Policy Agent for RECLAIM.

Given a diagnosed root cause, proposes 2–4 candidate recovery actions
from the fixed allowlist. This module proposes options — it does NOT
choose between them (that's the ERV Scorer's job).
"""

# ── Action allowlist (defense-only boundary) ────────────────────────────────
# These are the ONLY actions the system may ever take. This constant is the
# single source of truth for the allowlist, imported by guardrails.py.
ACTION_ALLOWLIST = frozenset([
    "retry_payment",
    "alternate_payment_method",
    "reminder_message",
    "otp_assist_link",
    "manual_escalation",
])

# ── Candidate actions per root cause ────────────────────────────────────────
# Each root cause maps to 2–4 candidate actions, ordered by domain preference
# (but ordering doesn't affect selection — the ERV Scorer ranks them).

_CANDIDATES_BY_ROOT_CAUSE = {
    "retry_likely_to_succeed": [
        "retry_payment",
        "manual_escalation",
    ],
    "customer_action_needed": [
        "alternate_payment_method",
        "reminder_message",
        "manual_escalation",
    ],
    "requires_verification": [
        "manual_escalation",
        "reminder_message",
    ],
    "low_intent_drop_off": [
        "reminder_message",
        "manual_escalation",
    ],
    "payment_friction": [
        "alternate_payment_method",
        "reminder_message",
        "manual_escalation",
    ],
    "otp_friction": [
        "otp_assist_link",
        "retry_payment",
        "manual_escalation",
    ],
}


def get_candidates(root_cause: str) -> list[str]:
    """
    Get candidate recovery actions for a given root cause.

    Args:
        root_cause: A root cause label from the RCA classifier.

    Returns:
        A list of 2–4 action strings from the allowlist.

    Raises:
        ValueError: If the root cause is unknown.
    """
    candidates = _CANDIDATES_BY_ROOT_CAUSE.get(root_cause)
    if candidates is None:
        raise ValueError(f"Unknown root cause: '{root_cause}'")

    # Structural assertion: every candidate must be in the allowlist
    for action in candidates:
        assert action in ACTION_ALLOWLIST, (
            f"BUG: candidate '{action}' is not in the action allowlist"
        )

    return list(candidates)  # return a copy to prevent mutation
