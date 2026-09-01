-- Roll back 0024.
ALTER TABLE scans DROP COLUMN interaction_pages_probed;
ALTER TABLE scans DROP COLUMN interaction_states_total;
