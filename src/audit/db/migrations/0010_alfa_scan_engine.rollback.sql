-- Roll back 0010 in reverse order. SQLite requires rebuilding the pipeline
-- discriminator by dropping/re-adding the checked column, as in 0004–0007.
DROP INDEX IF EXISTS idx_a11y_pipeline;
ALTER TABLE page_a11y_findings ADD COLUMN _pipeline_tmp TEXT;
UPDATE page_a11y_findings SET _pipeline_tmp = pipeline;
ALTER TABLE page_a11y_findings DROP COLUMN pipeline;
ALTER TABLE page_a11y_findings
    ADD COLUMN pipeline TEXT NOT NULL DEFAULT 'axe'
    CHECK (pipeline IN ('axe', 'semantic', 'keyboard', 'responsive', 'focus', 'visual'));
UPDATE page_a11y_findings SET pipeline = _pipeline_tmp
 WHERE _pipeline_tmp <> 'alfa' AND _pipeline_tmp IS NOT NULL;
ALTER TABLE page_a11y_findings DROP COLUMN _pipeline_tmp;
CREATE INDEX idx_a11y_pipeline ON page_a11y_findings(scan_id, pipeline);

ALTER TABLE page_a11y_findings DROP COLUMN engine_evidence_json;
ALTER TABLE page_a11y_findings DROP COLUMN engine_outcome;
ALTER TABLE scans DROP COLUMN alfa_cant_tell_total;
ALTER TABLE scans DROP COLUMN alfa_failed_total;
ALTER TABLE scans DROP COLUMN alfa_pages_scanned;
