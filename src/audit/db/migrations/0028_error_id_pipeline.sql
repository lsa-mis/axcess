-- 0028 — admit the error-identification probe pipeline (SC 3.3.1).
--
-- A new source of page-scoped findings: a Playwright form-validation probe
-- that triggers each invalid form's client-side validation (never submitting)
-- and checks whether the resulting error is identified in text and associated
-- with the field. Its rows go into ``page_a11y_findings`` with
-- ``pipeline='error_id'`` — same schema, same triage workflow, same Issues
-- view rendering as the keyboard/focus/responsive probes.
--
-- Migration 0012 last widened the pipeline CHECK to
-- ('axe','semantic','keyboard','responsive','focus','visual','alfa','protected_image').
-- SQLite can't ALTER a CHECK in place, so we use the same drop-and-re-add
-- dance the earlier pipeline migrations (0004, 0012) established:
--   * No external code refers to the CHECK constraint by name.
--   * ``pipeline`` has a DEFAULT, so existing rows keep their value.
--   * The whole migration runs in one transaction, so no reader observes the
--     brief NULL window between DROP and ADD.

-- Drop the index that references ``pipeline`` before dropping the column.
DROP INDEX IF EXISTS idx_a11y_pipeline;

-- Stash the current values so we can restore them after the CHECK swap.
ALTER TABLE page_a11y_findings ADD COLUMN _pipeline_tmp TEXT;
UPDATE page_a11y_findings SET _pipeline_tmp = pipeline;

ALTER TABLE page_a11y_findings DROP COLUMN pipeline;

ALTER TABLE page_a11y_findings
    ADD COLUMN pipeline TEXT NOT NULL DEFAULT 'axe'
    CHECK (pipeline IN (
        'axe', 'semantic', 'keyboard', 'responsive', 'focus', 'visual',
        'alfa', 'protected_image', 'error_id'
    ));

UPDATE page_a11y_findings SET pipeline = _pipeline_tmp
 WHERE _pipeline_tmp IS NOT NULL;

ALTER TABLE page_a11y_findings DROP COLUMN _pipeline_tmp;

CREATE INDEX idx_a11y_pipeline ON page_a11y_findings(scan_id, pipeline);
