-- Rollback for 0019 — the history rows are intentionally removed with their
-- table; the finding status itself remains on ``page_a11y_findings``.

DROP INDEX IF EXISTS idx_a11y_finding_history_scan;
DROP INDEX IF EXISTS idx_a11y_finding_history_finding;
DROP TABLE IF EXISTS a11y_finding_history;
