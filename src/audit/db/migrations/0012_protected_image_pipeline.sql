-- 0012 — minimal protected image-analysis index source.
--
-- Protected OCR/image bytes and extracted text are intentionally never stored
-- in the ordinary scan tables.  The paired companion can retain only an
-- opaque, review-required image-of-text lead in ``page_a11y_findings``.  A
-- distinct source label keeps it transparent that this is an in-memory image
-- pipeline, not an axe-core rule or an Alfa ACT outcome.

DROP INDEX IF EXISTS idx_a11y_pipeline;
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
