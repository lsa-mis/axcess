-- 0022 — record which control had to be operated to reveal a finding.
--
-- The interaction probe clicks controls on an already-rendered page and
-- re-runs axe on each state a click reveals (an opened menu, an expanded
-- form, a switched tab). Everything it produces IS an axe violation; the
-- only new fact is that a load-time pass could not see it.
--
-- Dedupe falls out of the existing UNIQUE (page_id, rule_id, target_hash):
-- a violation that was already visible at page load yields the identical
-- (rule_id, target_selector, html_snippet) triple in every revealed state,
-- so it collides and updates in place instead of being re-reported once
-- per click. Only genuinely new markup produces a new row.
--
-- NULL means "visible when the page loaded". A non-NULL value is the
-- accessible name of the control an auditor must operate to reproduce it.
-- The upsert never overwrites this column, so the first pass to observe a
-- finding wins — and the load-state pass always runs first, which keeps a
-- finding that is visible at load from being mislabelled as click-only.
ALTER TABLE page_a11y_findings ADD COLUMN revealed_by TEXT;

-- Partial: the overwhelming majority of rows are load-state (NULL), so
-- indexing only the interaction rows keeps this small while still making
-- "what did clicking find on this page" a cheap lookup.
CREATE INDEX idx_a11y_revealed ON page_a11y_findings(page_id)
    WHERE revealed_by IS NOT NULL;
