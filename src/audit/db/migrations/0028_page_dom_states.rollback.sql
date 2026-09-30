-- Roll back 0028 in reverse order.
ALTER TABLE page_a11y_findings DROP COLUMN revealed_state_key;
DROP INDEX IF EXISTS idx_dom_states_scan;
DROP TABLE page_dom_states;
