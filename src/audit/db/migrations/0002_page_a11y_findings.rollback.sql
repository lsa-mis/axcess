-- Rollback for 0002 — drop the axe table and the two scan columns.
--
-- SQLite ≥ 3.35 supports `ALTER TABLE ... DROP COLUMN`. The Makefile's
-- `migrate-rollback` target uses yoyo, which runs this as a single
-- transaction; if the SQLite version is too old to drop columns, the
-- whole rollback aborts and the forward migration stays applied. That's
-- the safer failure mode.

DROP INDEX IF EXISTS idx_a11y_status;
DROP INDEX IF EXISTS idx_a11y_impact;
DROP INDEX IF EXISTS idx_a11y_level;
DROP INDEX IF EXISTS idx_a11y_wcag_sc;
DROP INDEX IF EXISTS idx_a11y_rule;
DROP INDEX IF EXISTS idx_a11y_page;
DROP INDEX IF EXISTS idx_a11y_scan;
DROP TABLE IF EXISTS page_a11y_findings;

ALTER TABLE scans DROP COLUMN axe_violations_total;
ALTER TABLE scans DROP COLUMN axe_pages_scanned;
