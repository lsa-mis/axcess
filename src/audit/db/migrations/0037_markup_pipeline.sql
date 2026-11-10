-- 0037 — accept findings from the page code check, and count its pages.
--
-- page_a11y_findings.pipeline names the check that produced each row, and a
-- CHECK constraint lists the allowed names. The page code check
-- (audit.analyzer.markup) reads the rendered page code after the rule check
-- (axe) and stores its findings beside the other browser checks' with
-- pipeline = 'markup'. SQLite cannot change a CHECK constraint in place, so
-- the column is rebuilt as 0034 did, keeping every value. The two indexes
-- that cover the column are dropped first, because SQLite will not drop an
-- indexed column, and recreated after.
--
-- scans.markup_pages_checked counts the pages the check ran on, so the
-- report's "What was checked" can say how many pages it checked, and a scan
-- with nothing found reads as a count, not as a missing record.

DROP INDEX IF EXISTS idx_a11y_pipeline;
DROP INDEX IF EXISTS idx_a11y_rule_lookup;
ALTER TABLE page_a11y_findings ADD COLUMN _pipeline_tmp TEXT;
UPDATE page_a11y_findings SET _pipeline_tmp = pipeline;
ALTER TABLE page_a11y_findings DROP COLUMN pipeline;
ALTER TABLE page_a11y_findings
    ADD COLUMN pipeline TEXT NOT NULL DEFAULT 'axe'
    CHECK (pipeline IN (
        'axe', 'semantic', 'keyboard', 'responsive', 'focus', 'visual',
        'alfa', 'protected_image', 'forms', 'markup'
    ));
UPDATE page_a11y_findings SET pipeline = _pipeline_tmp
 WHERE _pipeline_tmp IS NOT NULL;
ALTER TABLE page_a11y_findings DROP COLUMN _pipeline_tmp;
CREATE INDEX idx_a11y_pipeline ON page_a11y_findings(scan_id, pipeline);
CREATE INDEX idx_a11y_rule_lookup
    ON page_a11y_findings(scan_id, pipeline, rule_id, page_id);

ALTER TABLE scans ADD COLUMN markup_pages_checked INTEGER NOT NULL DEFAULT 0;
