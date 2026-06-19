-- Rollback for 0005 — return the pipeline CHECK to the 0004 set
-- ('axe', 'semantic', 'keyboard'). Any rows with
-- ``pipeline='responsive'`` would violate the tighter constraint,
-- so we first drop them.

DELETE FROM page_a11y_findings WHERE pipeline = 'responsive';

DROP INDEX IF EXISTS idx_a11y_pipeline;

ALTER TABLE page_a11y_findings ADD COLUMN _pipeline_tmp TEXT;
UPDATE page_a11y_findings SET _pipeline_tmp = pipeline;

ALTER TABLE page_a11y_findings DROP COLUMN pipeline;

ALTER TABLE page_a11y_findings
    ADD COLUMN pipeline TEXT NOT NULL DEFAULT 'axe'
    CHECK (pipeline IN ('axe', 'semantic', 'keyboard'));

UPDATE page_a11y_findings SET pipeline = _pipeline_tmp
 WHERE _pipeline_tmp IS NOT NULL;

ALTER TABLE page_a11y_findings DROP COLUMN _pipeline_tmp;

CREATE INDEX idx_a11y_pipeline ON page_a11y_findings(scan_id, pipeline);
