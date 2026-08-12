-- 0019 — durable audit trail for DOM/accessibility finding status decisions.
--
-- Image findings have had ``finding_history`` since the initial schema. The
-- page-scoped axe/Alfa/probe table needs the same accountability boundary so
-- remediation, accepted-risk, and false-positive decisions retain who made
-- the change, when, the prior state, and the (redacted) rationale.

CREATE TABLE a11y_finding_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL
        REFERENCES page_a11y_findings(id) ON DELETE CASCADE,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    change_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    actor TEXT NOT NULL DEFAULT 'system'
        CHECK (actor IN ('system', 'user')),
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note TEXT CHECK (note IS NULL OR length(note) <= 2000)
);

CREATE INDEX idx_a11y_finding_history_finding
    ON a11y_finding_history(finding_id);
CREATE INDEX idx_a11y_finding_history_scan
    ON a11y_finding_history(scan_id, changed_at);
