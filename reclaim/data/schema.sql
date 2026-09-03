-- RECLAIM SQLite Schema
-- Two tables: cases (generated data) and audit_trail (decision log)

CREATE TABLE IF NOT EXISTS cases (
    case_id         TEXT PRIMARY KEY,
    scenario        TEXT NOT NULL CHECK (scenario IN ('payment_failure', 'checkout_abandonment')),
    -- payment_failure fields
    decline_reason  TEXT,
    retry_count_so_far INTEGER,
    -- checkout_abandonment fields
    abandonment_step TEXT,
    minutes_since_abandonment REAL,
    -- common fields
    amount          REAL NOT NULL,
    -- hidden true recovery probabilities per action (JSON blob)
    -- Format: {"retry_payment": 0.75, "alternate_payment_method": 0.10, ...}
    -- NEVER read by the scorer — only by the Executor
    hidden_probabilities TEXT NOT NULL,
    -- populated by Risk Detector (Phase 2)
    risk_score      REAL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_trail (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         TEXT NOT NULL,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    root_cause      TEXT NOT NULL,
    action_taken    TEXT NOT NULL,
    confidence_at_decision REAL NOT NULL,
    outcome         TEXT NOT NULL,
    stop_reason     TEXT,  -- populated only for Stopped/Escalated
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

CREATE INDEX IF NOT EXISTS idx_audit_case_id ON audit_trail(case_id);
