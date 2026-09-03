"""
Executor for RECLAIM — deterministic simulator.

Uses each case's hidden true recovery probabilities to draw outcomes,
seeded by (case_id, action, attempt_number) for reproducibility.
Supports force-failure mode for demo scenarios.
"""

import json
import random


class SimulatedExecutor:
    """
    Deterministic outcome simulator.

    For each (case, action, attempt), draws a random outcome using the
    case's hidden true probabilities, seeded deterministically so re-runs
    produce identical results.
    """

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

        # Parse hidden probabilities
        hidden_probs = case["hidden_probabilities"]
        if isinstance(hidden_probs, str):
            hidden_probs = json.loads(hidden_probs)

        true_prob = hidden_probs.get(action, 0.0)

        # Deterministic seed based on (case_id, action, attempt_number)
        seed = hash((case["case_id"], action, attempt_number))
        rng = random.Random(seed)

        return rng.random() < true_prob
