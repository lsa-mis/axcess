-- 0032 — accept findings from the form error check (WCAG 3.3.1).
--
-- page_a11y_findings.pipeline names the check that produced each row, and a
-- CHECK constraint lists the allowed names. The form error check
-- (audit.analyzer.forms) stores its findings beside the other browser
-- checks' with pipeline = 'forms'. SQLite cannot change a CHECK constraint
-- in place, so the column is rebuilt as 0012 did, keeping every value. The
-- two indexes that cover the column are dropped first, because SQLite will
-- not drop an indexed column, and recreated after.

DROP INDEX IF EXISTS idx_a11y_pipeline;
DROP INDEX IF EXISTS idx_a11y_rule_lookup;
ALTER TABLE page_a11y_findings ADD COLUMN _pipeline_tmp TEXT;
UPDATE page_a11y_findings SET _pipeline_tmp = pipeline;
ALTER TABLE page_a11y_findings DROP COLUMN pipeline;
ALTER TABLE page_a11y_findings
    ADD COLUMN pipeline TEXT NOT NULL DEFAULT 'axe'
    CHECK (pipeline IN (
        'axe', 'semantic', 'keyboard', 'responsive', 'focus', 'visual',
        'alfa', 'protected_image', 'forms'
    ));
UPDATE page_a11y_findings SET pipeline = _pipeline_tmp
 WHERE _pipeline_tmp IS NOT NULL;
ALTER TABLE page_a11y_findings DROP COLUMN _pipeline_tmp;
CREATE INDEX idx_a11y_pipeline ON page_a11y_findings(scan_id, pipeline);
CREATE INDEX idx_a11y_rule_lookup
    ON page_a11y_findings(scan_id, pipeline, rule_id, page_id);
