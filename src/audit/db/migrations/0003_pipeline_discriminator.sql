-- 0003 — distinguish axe-derived from semantic-LLM-derived findings.
--
-- `page_a11y_findings` was originally axe-only. Phase 9 introduces a
-- second source of page-scoped findings: per-criterion LLM analyzers
-- (the GenA11y-style semantic pipeline). Both produce *the same row
-- shape* — page-scoped, has a rule/criterion identifier, has a
-- triage status — so it's cleaner to extend this table with a
-- discriminator column than to fork into a sibling table that would
-- duplicate the schema, status workflow, indexes, and history.
--
-- Backward compatibility: existing rows default to `pipeline = 'axe'`.
-- The Issues view and exports keep working unchanged because every
-- IssueRow already carries a `pipeline` field at the Python level —
-- this migration just teaches the DB the same vocabulary.

-- The pipeline discriminator. Two values today; intentionally open for
-- additional values later (e.g. `'manual'` for human-entered findings).
-- The CHECK is updated when a new value is added so we never write a
-- typo into the column unnoticed.
ALTER TABLE page_a11y_findings
    ADD COLUMN pipeline TEXT NOT NULL DEFAULT 'axe'
    CHECK (pipeline IN ('axe', 'semantic'));

-- The WCAG SC this row is *about*. Axe rows already carry `wcag_sc` (the
-- rule's mapped SC, often the same), but the semantic pipeline does NOT
-- have a `rule_id` — it has a criterion. Storing both lets the UI and
-- exports group by criterion across pipelines cleanly.
ALTER TABLE page_a11y_findings ADD COLUMN criterion_sc TEXT;

-- Indexes for the new access patterns:
--   * "All semantic findings on a scan" → `(scan_id, pipeline)`
--   * "All findings for SC 2.4.4 across pipelines" → `(scan_id, criterion_sc)`
-- The criterion_sc index is partial because most axe rows leave it NULL
-- (axe's `wcag_sc` covers that case); skipping NULLs keeps the index small.
CREATE INDEX idx_a11y_pipeline ON page_a11y_findings(scan_id, pipeline);
CREATE INDEX idx_a11y_criterion ON page_a11y_findings(scan_id, criterion_sc)
    WHERE criterion_sc IS NOT NULL;
