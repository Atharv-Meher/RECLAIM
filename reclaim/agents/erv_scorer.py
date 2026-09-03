"""
Confidence-Aware Expected Recovery Value (ERV) Scorer for RECLAIM.

The most important component in the system. Maintains a Beta(α, β) posterior
per (root_cause, action) pair, updated after every observed outcome during
batch processing. This is what makes the system learn across the batch —
case #200 benefits from everything observed in cases #1–199.

ERV(a) = P(recovery | root_cause, a) × recoverable_amount
         − intervention_cost(a) − friction_penalty(a) − risk_penalty(a)

Confidence = alpha + beta - 2 (number of real observations).
Low confidence (< 5 observations) triggers the guardrail escalation.
"""

from collections import defaultdict


# ── Cost tables (§4.4) ──────────────────────────────────────────────────────
# These are the costs subtracted from the expected recovery value.
# Tuned to keep retry_payment cheap and manual_escalation expensive.

ACTION_COSTS = {
    "retry_payment": {
        "intervention_cost": 0,
        "friction_penalty": 0,
        "risk_penalty": 0,
    },
    "alternate_payment_method": {
        "intervention_cost": 0,
        "friction_penalty": 5,
        "risk_penalty": 0,
    },
    "reminder_message": {
        "intervention_cost": 2,
        "friction_penalty": 3,
        "risk_penalty": 0,
    },
    "otp_assist_link": {
        "intervention_cost": 2,
        "friction_penalty": 3,
        "risk_penalty": 0,
    },
    "manual_escalation": {
        "intervention_cost": 50,
        "friction_penalty": 10,
        "risk_penalty": 5,
    },
}


class ERVScorer:
    """
    Bayesian ERV scorer with Beta posterior per (root_cause, action) pair.

    Usage:
        scorer = ERVScorer()

        # Score candidates for a case
        best_action, erv, confidence = scorer.select_best(
            root_cause="retry_likely_to_succeed",
            candidates=["retry_payment", "manual_escalation"],
            amount=5000.0
        )

        # After observing outcome, update the posterior
        scorer.update(root_cause="retry_likely_to_succeed",
                      action="retry_payment", recovered=True)
    """

    def __init__(self, alpha_prior: float = 1.0, beta_prior: float = 1.0):
        """
        Initialize with weak uninformative priors (α₀=β₀=1 = uniform).

        Args:
            alpha_prior: Initial alpha for all (root_cause, action) pairs.
            beta_prior: Initial beta for all (root_cause, action) pairs.
        """
        self._alpha_prior = alpha_prior
        self._beta_prior = beta_prior
        # Stores (alpha, beta) per (root_cause, action) key
        self._alpha: dict[tuple[str, str], float] = defaultdict(
            lambda: alpha_prior
        )
        self._beta: dict[tuple[str, str], float] = defaultdict(
            lambda: beta_prior
        )

    def get_posterior(
        self, root_cause: str, action: str
    ) -> tuple[float, float]:
        """
        Get the current posterior mean and confidence for a
        (root_cause, action) pair.

        Returns:
            (p_recovery, confidence) where:
              - p_recovery = alpha / (alpha + beta), the posterior mean
              - confidence = alpha + beta - 2, the number of real observations
        """
        key = (root_cause, action)
        alpha = self._alpha[key]
        beta = self._beta[key]
        p_recovery = alpha / (alpha + beta)
        confidence = alpha + beta - (self._alpha_prior + self._beta_prior)
        return p_recovery, confidence

    def score(
        self, root_cause: str, action: str, amount: float
    ) -> tuple[float, float]:
        """
        Compute ERV for a single (root_cause, action, amount) triple.

        Returns:
            (erv, confidence)
        """
        p_recovery, confidence = self.get_posterior(root_cause, action)

        costs = ACTION_COSTS.get(action)
        if costs is None:
            raise ValueError(f"Unknown action '{action}' — not in cost table")

        total_cost = (
            costs["intervention_cost"]
            + costs["friction_penalty"]
            + costs["risk_penalty"]
        )

        erv = p_recovery * amount - total_cost
        return erv, confidence

    def select_best(
        self,
        root_cause: str,
        candidates: list[str],
        amount: float,
    ) -> tuple[str, float, float]:
        """
        Score all candidate actions and return the one with the highest ERV.

        Args:
            root_cause: The diagnosed root cause label.
            candidates: List of candidate action strings from the Policy Agent.
            amount: The recoverable amount for this case.

        Returns:
            (best_action, best_erv, confidence_for_best_action)
        """
        if not candidates:
            raise ValueError("No candidate actions provided")

        best_action = None
        best_erv = float("-inf")
        best_confidence = 0.0

        for action in candidates:
            erv, confidence = self.score(root_cause, action, amount)
            if erv > best_erv:
                best_action = action
                best_erv = erv
                best_confidence = confidence

        return best_action, best_erv, best_confidence

    def score_all(
        self,
        root_cause: str,
        candidates: list[str],
        amount: float,
    ) -> list[dict]:
        """
        Score all candidate actions and return detailed results for each.

        Returns a list of dicts with keys: action, erv, p_recovery, confidence,
        total_cost — sorted by ERV descending.
        """
        results = []
        for action in candidates:
            p_recovery, confidence = self.get_posterior(root_cause, action)
            costs = ACTION_COSTS[action]
            total_cost = sum(costs.values())
            erv = p_recovery * amount - total_cost

            results.append({
                "action": action,
                "erv": round(erv, 2),
                "p_recovery": round(p_recovery, 4),
                "confidence": confidence,
                "total_cost": total_cost,
            })

        return sorted(results, key=lambda r: r["erv"], reverse=True)

    def update(self, root_cause: str, action: str, recovered: bool) -> None:
        """
        Update the Beta posterior after observing an outcome.

        Args:
            root_cause: The root cause label.
            action: The action that was taken.
            recovered: True if the case was recovered, False otherwise.
        """
        key = (root_cause, action)
        if recovered:
            self._alpha[key] += 1
        else:
            self._beta[key] += 1

    def get_state(self) -> dict:
        """Return the current state of all posteriors (for debugging/audit)."""
        state = {}
        all_keys = set(self._alpha.keys()) | set(self._beta.keys())
        for key in sorted(all_keys):
            alpha = self._alpha[key]
            beta = self._beta[key]
            state[f"{key[0]}|{key[1]}"] = {
                "alpha": alpha,
                "beta": beta,
                "p_recovery": round(alpha / (alpha + beta), 4),
                "observations": alpha + beta - (self._alpha_prior + self._beta_prior),
            }
        return state

    def reset(self) -> None:
        """Reset all posteriors to the prior (for re-running evaluations)."""
        self._alpha.clear()
        self._beta.clear()
