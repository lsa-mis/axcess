-- Rollback for 0003 — drop the discriminator columns + their indexes.
--
-- SQLite ≥ 3.35 (which we require for `UPDATE … RETURNING` elsewhere)
-- supports `ALTER TABLE ... DROP COLUMN`. The drops here are
-- column-deletions, not column-resets to the original default, so a
-- downgraded DB will lose the `pipeline` and `criterion_sc` values
-- entirely. That's the intended semantics — the rollback returns the
-- schema to its pre-0003 state.

DROP INDEX IF EXISTS idx_a11y_criterion;
DROP INDEX IF EXISTS idx_a11y_pipeline;

ALTER TABLE page_a11y_findings DROP COLUMN criterion_sc;
ALTER TABLE page_a11y_findings DROP COLUMN pipeline;
