"""
Unit tests for the Case Lifecycle State Machine.

Covers:
  - Only valid transitions from Section 4.5 are permissible.
  - Invalid transitions raise InvalidTransitionError.
  - Terminal states (Recovered, Escalated, Stopped) have no outgoing transitions.
  - All valid execution paths terminate in a terminal state.
"""

import pytest
from reclaim.core.state_machine import (
    CaseStateMachine,
    CaseState,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    InvalidTransitionError,
)


def test_valid_recovery_lifecycle():
    """Detected -> Diagnosed -> Scored -> AwaitingApproval -> Executing -> Recovered."""
    sm = CaseStateMachine("CASE-101")
    assert sm.state == CaseState.DETECTED

    sm.transition(CaseState.DIAGNOSED)
    assert sm.state == CaseState.DIAGNOSED

    sm.transition(CaseState.SCORED)
    assert sm.state == CaseState.SCORED

    sm.transition(CaseState.AWAITING_APPROVAL)
    assert sm.state == CaseState.AWAITING_APPROVAL

    sm.transition(CaseState.EXECUTING)
    assert sm.state == CaseState.EXECUTING

    sm.transition(CaseState.RECOVERED)
    assert sm.state == CaseState.RECOVERED
    assert sm.is_terminal


def test_escalation_lifecycle():
    """Detected -> Diagnosed -> Scored -> AwaitingApproval -> Escalated."""
    sm = CaseStateMachine("CASE-102")
    sm.transition(CaseState.DIAGNOSED)
    sm.transition(CaseState.SCORED)
    sm.transition(CaseState.AWAITING_APPROVAL)
    sm.transition(CaseState.ESCALATED)
    assert sm.state == CaseState.ESCALATED
    assert sm.is_terminal


def test_retry_then_stopped_lifecycle():
    """Detected -> Diagnosed -> Scored -> AwaitingApproval -> Executing -> Scored -> AwaitingApproval -> Executing -> Stopped."""
    sm = CaseStateMachine("CASE-103")
    sm.transition(CaseState.DIAGNOSED)
    sm.transition(CaseState.SCORED)
    sm.transition(CaseState.AWAITING_APPROVAL)
    sm.transition(CaseState.EXECUTING)

    # Negative outcome with budget remaining -> back to Scored
    sm.transition(CaseState.SCORED)
    assert sm.state == CaseState.SCORED

    sm.transition(CaseState.AWAITING_APPROVAL)
    sm.transition(CaseState.EXECUTING)
    sm.transition(CaseState.STOPPED)
    assert sm.state == CaseState.STOPPED
    assert sm.is_terminal


def test_terminal_states_block_further_transitions():
    """Once terminal, no transition can be made."""
    for term_state in TERMINAL_STATES:
        sm = CaseStateMachine(f"CASE-{term_state.value}", initial_state=term_state)
        assert sm.is_terminal
        for any_state in CaseState:
            with pytest.raises(InvalidTransitionError):
                sm.transition(any_state)


def test_disallowed_transitions_raise_error():
    """Test various invalid transition jumps."""
    sm = CaseStateMachine("CASE-INVALID")

    # Cannot skip from Detected directly to Executing
    with pytest.raises(InvalidTransitionError):
        sm.transition(CaseState.EXECUTING)

    # Cannot skip from Detected directly to Recovered
    with pytest.raises(InvalidTransitionError):
        sm.transition(CaseState.RECOVERED)

    # Transition to Diagnosed
    sm.transition(CaseState.DIAGNOSED)
    # Cannot go back to Detected
    with pytest.raises(InvalidTransitionError):
        sm.transition(CaseState.DETECTED)


def test_all_lifecycle_paths_reach_terminal():
    """Validate that every modeled branch leads strictly to terminal states."""
    # Branch 1: direct recovery
    sm1 = CaseStateMachine("B1")
    sm1.transition(CaseState.DIAGNOSED)
    sm1.transition(CaseState.SCORED)
    sm1.transition(CaseState.AWAITING_APPROVAL)
    sm1.transition(CaseState.EXECUTING)
    sm1.transition(CaseState.RECOVERED)
    assert sm1.state in TERMINAL_STATES

    # Branch 2: low confidence escalation
    sm2 = CaseStateMachine("B2")
    sm2.transition(CaseState.DIAGNOSED)
    sm2.transition(CaseState.SCORED)
    sm2.transition(CaseState.AWAITING_APPROVAL)
    sm2.transition(CaseState.ESCALATED)
    assert sm2.state in TERMINAL_STATES

    # Branch 3: retry and stop
    sm3 = CaseStateMachine("B3")
    sm3.transition(CaseState.DIAGNOSED)
    sm3.transition(CaseState.SCORED)
    sm3.transition(CaseState.AWAITING_APPROVAL)
    sm3.transition(CaseState.EXECUTING)
    sm3.transition(CaseState.STOPPED)
    assert sm3.state in TERMINAL_STATES
