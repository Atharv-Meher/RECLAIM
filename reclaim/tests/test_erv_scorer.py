"""
Unit tests for the Confidence-Aware ERV Scorer.

Covers:
  - Posterior mean moves toward the observed empirical rate as observations accumulate.
  - Higher recoverable_amount strictly increases ERV, all else equal.
  - Confidence metric matches alpha + beta - 2.
  - Intervention/friction/risk penalties are subtracted correctly.
  - Best candidate selection identifies highest ERV intervention.
"""

import pytest
from reclaim.agents.erv_scorer import ERVScorer, ACTION_COSTS


def test_posterior_converges_to_observed_rate():
    """Verify that Beta posterior mean converges to empirical recovery rate."""
    scorer = ERVScorer(alpha_prior=1.0, beta_prior=1.0)
    root_cause = "retry_likely_to_succeed"
    action = "retry_payment"

    # Initially prior is 1/(1+1) = 0.50, confidence = 0
    p_init, conf_init = scorer.get_posterior(root_cause, action)
    assert p_init == 0.50
    assert conf_init == 0.0

    # Feed 70 successes and 30 failures (empirical rate = 70%)
    for _ in range(70):
        scorer.update(root_cause, action, recovered=True)
    for _ in range(30):
        scorer.update(root_cause, action, recovered=False)

    p_final, conf_final = scorer.get_posterior(root_cause, action)
    # Posterior mean should be (1 + 70) / (2 + 100) = 71 / 102 = 0.6961 ~ 0.70
    assert abs(p_final - 0.70) < 0.02
    assert conf_final == 100.0


def test_higher_amount_increases_erv():
    """Verify that larger amounts strictly increase ERV for identical posterior state."""
    scorer = ERVScorer()
    root_cause = "payment_friction"
    action = "alternate_payment_method"

    # Observe a few outcomes
    scorer.update(root_cause, action, True)
    scorer.update(root_cause, action, True)
    scorer.update(root_cause, action, False)

    erv_low, _ = scorer.score(root_cause, action, amount=500.0)
    erv_med, _ = scorer.score(root_cause, action, amount=5000.0)
    erv_high, _ = scorer.score(root_cause, action, amount=25000.0)

    assert erv_low < erv_med < erv_high


def test_penalties_subtracted_correctly():
    """Verify intervention cost, friction penalty, and risk penalty subtraction."""
    scorer = ERVScorer()
    root_cause = "requires_verification"

    # Action with heavy penalties: manual_escalation (cost=50, friction=10, risk=5 -> total 65)
    # Action with 0 penalties: retry_payment (cost=0, friction=0, risk=0 -> total 0)
    amount = 1000.0
    p_rec, _ = scorer.get_posterior(root_cause, "manual_escalation")
    erv_manual, _ = scorer.score(root_cause, "manual_escalation", amount)
    assert erv_manual == (p_rec * amount - 65.0)

    p_retry, _ = scorer.get_posterior(root_cause, "retry_payment")
    erv_retry, _ = scorer.score(root_cause, "retry_payment", amount)
    assert erv_retry == (p_retry * amount - 0.0)


def test_select_best_picks_highest_erv():
    """Verify select_best chooses the action with the maximum ERV among candidates."""
    scorer = ERVScorer()
    root_cause = "otp_friction"
    candidates = ["otp_assist_link", "retry_payment", "manual_escalation"]

    # Teach the scorer that otp_assist_link succeeds 90% of the time,
    # while retry_payment only 20%
    for _ in range(9):
        scorer.update(root_cause, "otp_assist_link", True)
    scorer.update(root_cause, "otp_assist_link", False)

    for _ in range(2):
        scorer.update(root_cause, "retry_payment", True)
    for _ in range(8):
        scorer.update(root_cause, "retry_payment", False)

    best_action, best_erv, conf = scorer.select_best(root_cause, candidates, amount=5000.0)
    assert best_action == "otp_assist_link"
    assert conf >= 10.0
