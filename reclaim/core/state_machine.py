"""
Case lifecycle state machine for RECLAIM.

States and transitions (from build brief §4.5):
  Detected → Diagnosed → Scored → AwaitingApproval →
    {Executing (approved) | Escalated (low confidence)}
  Executing →
    {Recovered (positive outcome) | Scored (negative, attempts remaining) |
     Stopped (attempts exhausted)}

Terminal states: Recovered, Escalated, Stopped
"""

from enum import Enum


class CaseState(Enum):
    """All possible states in the case lifecycle."""
    DETECTED = "Detected"
    DIAGNOSED = "Diagnosed"
    SCORED = "Scored"
    AWAITING_APPROVAL = "AwaitingApproval"
    EXECUTING = "Executing"
    RECOVERED = "Recovered"
    ESCALATED = "Escalated"
    STOPPED = "Stopped"


# Terminal states — once a case enters one of these, it's done
TERMINAL_STATES = frozenset([
    CaseState.RECOVERED,
    CaseState.ESCALATED,
    CaseState.STOPPED,
])

# Valid transitions: maps each state to the set of states it can move to
VALID_TRANSITIONS: dict[CaseState, frozenset[CaseState]] = {
    CaseState.DETECTED: frozenset([CaseState.DIAGNOSED]),
    CaseState.DIAGNOSED: frozenset([CaseState.SCORED]),
    CaseState.SCORED: frozenset([CaseState.AWAITING_APPROVAL]),
    CaseState.AWAITING_APPROVAL: frozenset([
        CaseState.EXECUTING,
        CaseState.ESCALATED,
    ]),
    CaseState.EXECUTING: frozenset([
        CaseState.RECOVERED,
        CaseState.SCORED,      # negative outcome, attempts remaining
        CaseState.STOPPED,     # attempts exhausted
    ]),
    # Terminal states have no outgoing transitions
    CaseState.RECOVERED: frozenset(),
    CaseState.ESCALATED: frozenset(),
    CaseState.STOPPED: frozenset(),
}


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


class CaseStateMachine:
    """
    Tracks the state of a single case through the recovery pipeline.

    Usage:
        sm = CaseStateMachine("PF-0001")
        sm.transition(CaseState.DIAGNOSED)
        sm.transition(CaseState.SCORED)
        ...
    """

    def __init__(self, case_id: str, initial_state: CaseState = CaseState.DETECTED):
        self.case_id = case_id
        self._state = initial_state
        self._history: list[tuple[CaseState, CaseState]] = []

    @property
    def state(self) -> CaseState:
        """Current state of the case."""
        return self._state

    @property
    def is_terminal(self) -> bool:
        """Whether the case is in a terminal state."""
        return self._state in TERMINAL_STATES

    @property
    def history(self) -> list[tuple[CaseState, CaseState]]:
        """List of (from_state, to_state) transitions."""
        return list(self._history)

    def transition(self, new_state: CaseState) -> None:
        """
        Transition to a new state.

        Args:
            new_state: The target state.

        Raises:
            InvalidTransitionError: If the transition is not valid.
        """
        if self.is_terminal:
            raise InvalidTransitionError(
                f"Case {self.case_id}: Cannot transition from terminal state "
                f"'{self._state.value}'"
            )

        valid_next = VALID_TRANSITIONS.get(self._state, frozenset())
        if new_state not in valid_next:
            raise InvalidTransitionError(
                f"Case {self.case_id}: Invalid transition "
                f"'{self._state.value}' → '{new_state.value}'. "
                f"Valid transitions: {[s.value for s in valid_next]}"
            )

        old_state = self._state
        self._state = new_state
        self._history.append((old_state, new_state))

    def __repr__(self) -> str:
        return f"CaseStateMachine({self.case_id}, state={self._state.value})"
