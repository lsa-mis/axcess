-- 0006 — admit the focus-probe pipeline (SC 2.4.11 Focus Not Obscured).
-- Same drop/re-add-column dance as 0005 (SQLite can't ALTER a CHECK).
DROP INDEX IF EXISTS idx_a11y_pipeline;

ALTER TABLE page_a11y_findings ADD COLUMN _pipeline_tmp TEXT;
UPDATE page_a11y_findings SET _pipeline_tmp = pipeline;
ALTER TABLE page_a11y_findings DROP COLUMN pipeline;

ALTER TABLE page_a11y_findings
    ADD COLUMN pipeline TEXT NOT NULL DEFAULT 'axe'
    CHECK (pipeline IN ('axe', 'semantic', 'keyboard', 'responsive', 'focus'));

UPDATE page_a11y_findings SET pipeline = _pipeline_tmp
 WHERE _pipeline_tmp IS NOT NULL;

ALTER TABLE page_a11y_findings DROP COLUMN _pipeline_tmp;

CREATE INDEX idx_a11y_pipeline ON page_a11y_findings(scan_id, pipeline);
