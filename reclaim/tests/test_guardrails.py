"""
Unit tests for the Guardrail Engine.

Covers:
  - Confidence below floor (< 5) -> ESCALATE
  - Max attempts reached (>= 3) -> STOP
  - Action outside allowlist -> rejected (raises ValueError)
  - Valid action with sufficient confidence and budget -> APPROVE
"""

import pytest
from reclaim.agents.guardrails import check, GuardrailResult, CONFIDENCE_FLOOR, MAX_ATTEMPTS
from reclaim.agents.policy_agent import ACTION_ALLOWLIST


def test_confidence_below_floor_escalates():
    """Verify that any action with confidence < CONFIDENCE_FLOOR escalates."""
    for conf in [0, 1, 2, 3, 4, 4.9]:
        res, reason = check("retry_payment", confidence=conf, attempts_so_far=0)
        assert res == GuardrailResult.ESCALATE
        assert "below floor" in reason.lower()


def test_max_attempts_stops():
    """Verify that reaching or exceeding MAX_ATTEMPTS forces a STOP."""
    for attempts in [3, 4, 5]:
        # Even with high confidence, max attempts must stop
        res, reason = check("retry_payment", confidence=20, attempts_so_far=attempts)
        assert res == GuardrailResult.STOP
        assert "exhausted" in reason.lower() or "stopping" in reason.lower()


def test_out_of_allowlist_rejected():
    """Verify that an invalid or unapproved action is rejected outright."""
    invalid_actions = [
        "call_customer",
        "issue_refund",
        "drop_charge",
        "random_action",
        "retry_payment_v2",
        "",
    ]
    for action in invalid_actions:
        with pytest.raises(ValueError, match="GUARDRAIL VIOLATION"):
            check(action, confidence=10, attempts_so_far=0)


def test_approved_action():
    """Verify that valid allowlist actions with confidence >= floor and attempts < max approve."""
    for action in ACTION_ALLOWLIST:
        res, reason = check(action, confidence=CONFIDENCE_FLOOR, attempts_so_far=0)
        assert res == GuardrailResult.APPROVE
        assert "passed" in reason.lower()

        res2, _ = check(action, confidence=15, attempts_so_far=2)
        assert res2 == GuardrailResult.APPROVE
