"""
Audit Trail for RECLAIM.

One row per decision (a case may have several across retries):
  case_id, timestamp, root_cause, action_taken, confidence_at_decision,
  outcome, stop_reason (nullable — populated only for Stopped/Escalated).

This table is the evidence for the "compliant escalation, stopping rules,
audit trail" requirement.
"""

import sqlite3
from datetime import datetime


class AuditTrail:
    """
    Append-only audit log backed by SQLite.

    Every decision — successful recovery, failed attempt, escalation,
    or stop — gets a row with full context.
    """

    def __init__(self, conn: sqlite3.Connection):
        """
        Initialize with an existing SQLite connection.
        The audit_trail table must already exist (created by schema.sql).
        """
        self._conn = conn

    def log_decision(
        self,
        case_id: str,
        root_cause: str,
        action_taken: str,
        confidence_at_decision: float,
        outcome: str,
        stop_reason: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        """
        Log a single decision to the audit trail.

        Args:
            case_id: The case this decision belongs to.
            root_cause: The diagnosed root cause.
            action_taken: The action that was taken (or proposed, for escalation).
            confidence_at_decision: The ERV scorer's confidence at decision time.
            outcome: One of 'recovered', 'not_recovered', 'escalated', 'stopped'.
            stop_reason: Human-readable reason (required for 'escalated'/'stopped').
            timestamp: ISO timestamp (defaults to now).
        """
        if outcome in ("escalated", "stopped") and stop_reason is None:
            raise ValueError(
                f"stop_reason is required for outcome '{outcome}' "
                f"(case {case_id})"
            )

        ts = timestamp or datetime.now().isoformat()

        self._conn.execute(
            """
            INSERT INTO audit_trail
                (case_id, timestamp, root_cause, action_taken,
                 confidence_at_decision, outcome, stop_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (case_id, ts, root_cause, action_taken,
             confidence_at_decision, outcome, stop_reason),
        )
        self._conn.commit()

    def get_case_history(self, case_id: str) -> list[dict]:
        """Get all audit entries for a specific case, in chronological order."""
        cursor = self._conn.execute(
            """
            SELECT case_id, timestamp, root_cause, action_taken,
                   confidence_at_decision, outcome, stop_reason
            FROM audit_trail
            WHERE case_id = ?
            ORDER BY id ASC
            """,
            (case_id,),
        )
        return [dict(zip(
            ["case_id", "timestamp", "root_cause", "action_taken",
             "confidence_at_decision", "outcome", "stop_reason"],
            row
        )) for row in cursor.fetchall()]

    def get_all_entries(self) -> list[dict]:
        """Get all audit entries, in insertion order."""
        cursor = self._conn.execute(
            """
            SELECT case_id, timestamp, root_cause, action_taken,
                   confidence_at_decision, outcome, stop_reason
            FROM audit_trail
            ORDER BY id ASC
            """
        )
        return [dict(zip(
            ["case_id", "timestamp", "root_cause", "action_taken",
             "confidence_at_decision", "outcome", "stop_reason"],
            row
        )) for row in cursor.fetchall()]

    def get_terminal_entries(self) -> list[dict]:
        """Get all entries for terminal cases (stopped/escalated) — for verification."""
        cursor = self._conn.execute(
            """
            SELECT case_id, timestamp, root_cause, action_taken,
                   confidence_at_decision, outcome, stop_reason
            FROM audit_trail
            WHERE outcome IN ('stopped', 'escalated')
            ORDER BY id ASC
            """
        )
        return [dict(zip(
            ["case_id", "timestamp", "root_cause", "action_taken",
             "confidence_at_decision", "outcome", "stop_reason"],
            row
        )) for row in cursor.fetchall()]

    def clear(self) -> None:
        """Clear all audit entries (for re-running evaluations)."""
        self._conn.execute("DELETE FROM audit_trail")
        self._conn.commit()
