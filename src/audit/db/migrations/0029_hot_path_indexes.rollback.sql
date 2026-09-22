-- Roll back 0029. Dropping an index only costs the queries their speed;
-- no row data lives here. The stats table is left in place: it is derived,
-- and ANALYZE is safe to have run.
DROP INDEX IF EXISTS idx_a11y_rule_lookup;
DROP INDEX IF EXISTS idx_a11y_screenshot;
DROP INDEX IF EXISTS idx_jobs_scan;
