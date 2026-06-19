-- 0004 — admit the keyboard-probe pipeline (SC 2.1.2).
--
-- Phase 9.5 adds a third source of page-scoped findings: a Playwright
-- keyboard-trap probe that simulates Tab/Shift-Tab/Escape and watches
-- ``document.activeElement``. Its rows go into ``page_a11y_findings``
-- with ``pipeline='keyboard'`` — same schema, same triage workflow,
-- same Issues-view rendering.
--
-- Migration 0003 introduced the ``pipeline`` discriminator with a
-- CHECK constraint hardcoded to ``('axe', 'semantic')``. That CHECK
-- needs to also allow ``'keyboard'``, otherwise upsert_keyboard_finding
-- raises sqlite3.IntegrityError on every row.
--
-- SQLite can't ALTER a CHECK constraint in place. The canonical
-- workaround on this column is a 12-step table rebuild, which is
-- heavy and error-prone. We take the simpler route: drop the column,
-- re-add it with the wider CHECK. This is safe because:
--   * No external code refers to the CHECK constraint by name.
--   * `pipeline` has a DEFAULT, so existing rows keep their value.
--   * Dropping a column under SQLite >= 3.35 is supported and
--     atomic; the table rewrite happens server-side.
-- The trade-off: the column is briefly NULL between DROP and ADD,
-- but the migration runs inside a single transaction, so no concurrent
-- reader observes the intermediate state.

-- Drop the index that references `pipeline` BEFORE dropping the
-- column — SQLite validates surviving indexes after each DDL step.
DROP INDEX IF EXISTS idx_a11y_pipeline;

-- Capture each row's current pipeline value into a temp column so we
-- can restore it after the CHECK swap.
ALTER TABLE page_a11y_findings ADD COLUMN _pipeline_tmp TEXT;
UPDATE page_a11y_findings SET _pipeline_tmp = pipeline;

ALTER TABLE page_a11y_findings DROP COLUMN pipeline;

ALTER TABLE page_a11y_findings
    ADD COLUMN pipeline TEXT NOT NULL DEFAULT 'axe'
    CHECK (pipeline IN ('axe', 'semantic', 'keyboard'));

-- Restore the values.
UPDATE page_a11y_findings SET pipeline = _pipeline_tmp
 WHERE _pipeline_tmp IS NOT NULL;

ALTER TABLE page_a11y_findings DROP COLUMN _pipeline_tmp;

-- Re-create the index now that the column is back.
CREATE INDEX idx_a11y_pipeline ON page_a11y_findings(scan_id, pipeline);
