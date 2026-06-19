-- 0005 — admit the responsive-probe pipeline (SC 1.4.4 / 1.4.10 / 1.4.12).
--
-- Phase 10 adds a fourth source of page-scoped findings: a Playwright
-- responsive/zoom probe that resizes the live page to 320px (reflow),
-- the 200%-zoom proxy viewport (text clipping), and applies WCAG's
-- text-spacing override (clipping again). Its rows go into
-- ``page_a11y_findings`` with ``pipeline='responsive'`` — same schema,
-- same triage workflow, same Issues-view rendering.
--
-- Same CHECK-widening dance as migration 0004 (see its header for why
-- the drop/re-add route beats a 12-step table rebuild): SQLite can't
-- ALTER a CHECK in place, so we stash values, swap the column, and
-- restore — all inside one transaction.

DROP INDEX IF EXISTS idx_a11y_pipeline;

ALTER TABLE page_a11y_findings ADD COLUMN _pipeline_tmp TEXT;
UPDATE page_a11y_findings SET _pipeline_tmp = pipeline;

ALTER TABLE page_a11y_findings DROP COLUMN pipeline;

ALTER TABLE page_a11y_findings
    ADD COLUMN pipeline TEXT NOT NULL DEFAULT 'axe'
    CHECK (pipeline IN ('axe', 'semantic', 'keyboard', 'responsive'));

UPDATE page_a11y_findings SET pipeline = _pipeline_tmp
 WHERE _pipeline_tmp IS NOT NULL;

ALTER TABLE page_a11y_findings DROP COLUMN _pipeline_tmp;

CREATE INDEX idx_a11y_pipeline ON page_a11y_findings(scan_id, pipeline);
