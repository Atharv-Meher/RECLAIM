"""
Executor for RECLAIM — deterministic simulator.

Uses each case's hidden true recovery probabilities to draw outcomes,
seeded by (case_id, action, attempt_number) for reproducibility.
Supports force-failure mode for demo scenarios.
"""

import hashlib
import json
import random


def deterministic_seed(case_id: str, action: str, attempt_number: int) -> int:
    """Generate a reproducible integer seed across process launches."""
    key = f"{case_id}:{action}:{attempt_number}".encode("utf-8")
    return int(hashlib.sha256(key).hexdigest()[:15], 16)


from reclaim.core.razorpay_adapter import RazorpayAdapter


class SimulatedExecutor:
    """
    Deterministic outcome simulator with optional Razorpay test-mode API swap-in.

    For each (case, action, attempt), draws an outcome using the case's
    hidden true probabilities. When Razorpay API keys are configured,
    the `alternate_payment_method` action will also generate real live
    Razorpay payment links (test mode).
    """

    def __init__(self, enable_real_razorpay: bool = True):
        self.razorpay_adapter = RazorpayAdapter() if enable_real_razorpay else None

    def execute(
        self,
        case: dict,
        action: str,
        attempt_number: int,
        force_failure: bool = False,
    ) -> bool:
        """
        Simulate execution of an action on a case.

        Args:
            case: The case dict (must have 'case_id' and 'hidden_probabilities').
            action: The action to execute (from the allowlist).
            attempt_number: Which attempt this is (0-indexed), used for seeding.
            force_failure: If True, always returns False (for demo scenarios).

        Returns:
            True if the case was recovered, False otherwise.
        """
        if force_failure:
            return False

        # Optional real Razorpay API swap-in for alternate_payment_method
        if action == "alternate_payment_method" and self.razorpay_adapter and self.razorpay_adapter.is_configured():
            try:
                link_data = self.razorpay_adapter.create_payment_link(
                    case_id=case["case_id"],
                    amount=case["amount"],
                    root_cause=case.get("root_cause"),
                )
                case["razorpay_payment_link"] = link_data
            except Exception as e:
                case["razorpay_error"] = str(e)

        # Parse hidden probabilities
        hidden_probs = case["hidden_probabilities"]
        if isinstance(hidden_probs, str):
            hidden_probs = json.loads(hidden_probs)

        true_prob = hidden_probs.get(action, 0.0)

        # Deterministic seed based on (case_id, action, attempt_number)
        seed = deterministic_seed(case["case_id"], action, attempt_number)
        rng = random.Random(seed)

        return rng.random() < true_prob
