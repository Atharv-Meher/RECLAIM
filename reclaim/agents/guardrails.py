"""
Guardrail Engine for RECLAIM.

Evaluated before any action executes, every time. Enforces three rules:
  1. Action must be in the defense-only allowlist (structural assertion)
  2. Case has exceeded max attempts → STOP
  3. Confidence below floor → ESCALATE

If all checks pass → APPROVE.
"""

from enum import Enum
from reclaim.agents.policy_agent import ACTION_ALLOWLIST


class GuardrailResult(Enum):
    """Possible outcomes of a guardrail check."""
    APPROVE = "approve"
    ESCALATE = "escalate"
    STOP = "stop"


# ── Thresholds ──────────────────────────────────────────────────────────────
CONFIDENCE_FLOOR = 5    # minimum real observations before auto-executing
MAX_ATTEMPTS = 3        # maximum action attempts per case


def check(
    action: str,
    confidence: float,
    attempts_so_far: int,
) -> tuple[GuardrailResult, str]:
    """
    Run all guardrail checks for a proposed action.

    Args:
        action: The proposed action string.
        confidence: The ERV scorer's confidence (observations count) for this
                    (root_cause, action) pair.
        attempts_so_far: How many actions have already been attempted on this case.

    Returns:
        (result, reason) where result is a GuardrailResult and reason is
        a human-readable explanation (populated for ESCALATE and STOP).

    Raises:
        ValueError: If the action is not in the allowlist. This should be
                    structurally impossible if the Policy Agent and ERV Scorer
                    are implemented correctly — it's an assertion, not a
                    runtime check.
    """
    # Check 1: Action must be in the allowlist (defense-only boundary)
    if action not in ACTION_ALLOWLIST:
        raise ValueError(
            f"GUARDRAIL VIOLATION: Action '{action}' is not in the allowlist "
            f"{sorted(ACTION_ALLOWLIST)}. This should be structurally impossible."
        )

    # Check 2: Max attempts exceeded → STOP
    if attempts_so_far >= MAX_ATTEMPTS:
        return (
            GuardrailResult.STOP,
            f"Case has exhausted {MAX_ATTEMPTS} attempts — stopping recovery.",
        )

    # Check 3: Low confidence → ESCALATE
    if confidence < CONFIDENCE_FLOOR:
        return (
            GuardrailResult.ESCALATE,
            f"Confidence ({confidence:.0f} observations) is below floor "
            f"({CONFIDENCE_FLOOR}) — escalating to human review.",
        )

    # All checks passed
    return (GuardrailResult.APPROVE, "All guardrail checks passed.")
