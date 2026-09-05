"""
Standalone narrative generation script for RECLAIM.

Runs AFTER `run_evaluation.py` — reads the already-written `audit_trail` table
from `reclaim.db`, generates LLM narratives for escalated and relevant recovered/
stopped cases, and writes results into a `narratives` table.

Never modifies `cases` or `audit_trail` — read-then-append only.

Usage:
    python -m reclaim.evaluation.generate_narratives
"""

import os
import sys
import sqlite3

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from reclaim.agents.narrator import draft_customer_message, draft_escalation_briefing


def _ensure_narratives_table(conn: sqlite3.Connection) -> None:
    """Create the narratives table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS narratives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL,
            narrative_type TEXT NOT NULL,
            action TEXT,
            root_cause TEXT,
            narrative_text TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def generate_all_narratives(db_path: str = "reclaim.db") -> None:
    """
    Read audit_trail, generate narratives, write to narratives table.
    """
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found. Run evaluation first:")
        print("  python -m reclaim.evaluation.run_evaluation")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _ensure_narratives_table(conn)

    # Clear previous narratives
    conn.execute("DELETE FROM narratives")
    conn.commit()

    # Read all audit entries
    rows = conn.execute("""
        SELECT case_id, root_cause, action_taken, confidence_at_decision,
               outcome, stop_reason
        FROM audit_trail
        ORDER BY id ASC
    """).fetchall()

    # Also read case data for context
    cases = {}
    case_rows = conn.execute("""
        SELECT case_id, scenario, amount, decline_reason, retry_count_so_far,
               abandonment_step, minutes_since_abandonment
        FROM cases
    """).fetchall()
    for cr in case_rows:
        cases[cr["case_id"]] = dict(cr)

    # Track terminal outcomes per case (use last entry per case)
    terminal_entries = {}
    for row in rows:
        terminal_entries[row["case_id"]] = dict(row)

    escalation_count = 0
    message_count = 0
    skipped = 0

    print("\n" + "=" * 70)
    print("    RECLAIM — LLM NARRATIVE GENERATION")
    print("=" * 70)

    for case_id, entry in terminal_entries.items():
        case = cases.get(case_id, {"case_id": case_id, "amount": 0, "scenario": "unknown"})
        outcome = entry["outcome"]
        action = entry["action_taken"]
        root_cause = entry["root_cause"]
        confidence = float(entry["confidence_at_decision"])
        stop_reason = entry.get("stop_reason") or ""

        if outcome == "escalated":
            narrative = draft_escalation_briefing(case, root_cause, confidence, stop_reason)
            conn.execute(
                "INSERT INTO narratives (case_id, narrative_type, action, root_cause, narrative_text) VALUES (?, ?, ?, ?, ?)",
                (case_id, "escalation_briefing", action, root_cause, narrative),
            )
            escalation_count += 1
        elif action in ("reminder_message", "otp_assist_link"):
            narrative = draft_customer_message(case, root_cause, action)
            conn.execute(
                "INSERT INTO narratives (case_id, narrative_type, action, root_cause, narrative_text) VALUES (?, ?, ?, ?, ?)",
                (case_id, "customer_message", action, root_cause, narrative),
            )
            message_count += 1
        else:
            skipped += 1
            continue

    conn.commit()

    total = escalation_count + message_count
    print(f"\nGenerated {total} narratives:")
    print(f"  • Escalation briefings: {escalation_count}")
    print(f"  • Customer messages:    {message_count}")
    print(f"  • Skipped (no narration needed): {skipped}")

    # Show a few samples
    samples = conn.execute(
        "SELECT case_id, narrative_type, narrative_text FROM narratives LIMIT 3"
    ).fetchall()

    if samples:
        print("\n--- Sample Narratives ---")
        for s in samples:
            print(f"\n[{s['narrative_type'].upper()}] {s['case_id']}:")
            print(f"  {s['narrative_text'][:200]}{'...' if len(s['narrative_text']) > 200 else ''}")

    conn.close()
    print(f"\n✔ Narratives saved to '{db_path}' → 'narratives' table")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    db_file = os.path.join(REPO_ROOT, "reclaim.db")
    generate_all_narratives(db_path=db_file)
