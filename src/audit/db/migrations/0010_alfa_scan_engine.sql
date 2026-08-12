-- 0010 — add Siteimprove Alfa as an independently selectable scan engine.
--
-- Alfa produces two actionable outcome types: `failed` (a deterministic
-- failure) and `cantTell` (an explicitly unresolved, human-review lead).
-- Keeping those separate prevents an ACT outcome from being misreported as a
-- WCAG failure. The raw, bounded engine evidence is additive; existing axe
-- and probe rows remain `failed` with no engine-specific payload.

ALTER TABLE page_a11y_findings ADD COLUMN engine_outcome TEXT NOT NULL DEFAULT 'failed'
    CHECK (engine_outcome IN ('failed', 'cant_tell'));
ALTER TABLE page_a11y_findings ADD COLUMN engine_evidence_json TEXT;

-- SQLite cannot widen an existing CHECK in place. Preserve every current
-- pipeline while allowing the new `alfa` discriminator.
DROP INDEX IF EXISTS idx_a11y_pipeline;
ALTER TABLE page_a11y_findings ADD COLUMN _pipeline_tmp TEXT;
UPDATE page_a11y_findings SET _pipeline_tmp = pipeline;
ALTER TABLE page_a11y_findings DROP COLUMN pipeline;
ALTER TABLE page_a11y_findings
    ADD COLUMN pipeline TEXT NOT NULL DEFAULT 'axe'
    CHECK (pipeline IN ('axe', 'semantic', 'keyboard', 'responsive', 'focus', 'visual', 'alfa'));
UPDATE page_a11y_findings SET pipeline = _pipeline_tmp
 WHERE _pipeline_tmp IS NOT NULL;
ALTER TABLE page_a11y_findings DROP COLUMN _pipeline_tmp;
CREATE INDEX idx_a11y_pipeline ON page_a11y_findings(scan_id, pipeline);

-- Definite Alfa coverage is recorded independently from axe so reports can
-- say exactly which engine ran and how many unresolved ACT outcomes remain.
ALTER TABLE scans ADD COLUMN alfa_pages_scanned INTEGER NOT NULL DEFAULT 0;
ALTER TABLE scans ADD COLUMN alfa_failed_total INTEGER NOT NULL DEFAULT 0;
ALTER TABLE scans ADD COLUMN alfa_cant_tell_total INTEGER NOT NULL DEFAULT 0;
