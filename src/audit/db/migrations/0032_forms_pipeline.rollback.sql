-- Rollback for 0032. Remove the form error check's findings before restoring
-- the previous list of allowed pipelines.

DELETE FROM page_a11y_findings WHERE pipeline = 'forms';

DROP INDEX IF EXISTS idx_a11y_pipeline;
DROP INDEX IF EXISTS idx_a11y_rule_lookup;
ALTER TABLE page_a11y_findings ADD COLUMN _pipeline_tmp TEXT;
UPDATE page_a11y_findings SET _pipeline_tmp = pipeline;
ALTER TABLE page_a11y_findings DROP COLUMN pipeline;
ALTER TABLE page_a11y_findings
    ADD COLUMN pipeline TEXT NOT NULL DEFAULT 'axe'
    CHECK (pipeline IN (
        'axe', 'semantic', 'keyboard', 'responsive', 'focus', 'visual',
        'alfa', 'protected_image'
    ));
UPDATE page_a11y_findings SET pipeline = _pipeline_tmp
 WHERE _pipeline_tmp IS NOT NULL;
ALTER TABLE page_a11y_findings DROP COLUMN _pipeline_tmp;
CREATE INDEX idx_a11y_pipeline ON page_a11y_findings(scan_id, pipeline);
CREATE INDEX idx_a11y_rule_lookup
    ON page_a11y_findings(scan_id, pipeline, rule_id, page_id);
