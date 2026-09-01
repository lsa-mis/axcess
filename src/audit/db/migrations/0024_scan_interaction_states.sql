-- 0024 — record how many DOM states a scan actually reached.
--
-- A page count alone understates an authenticated application. Most of it
-- does not exist until a control is used: menus closed, dialogs unopened,
-- tabs unswitched. The interaction probe operates those controls and tests
-- each state a click reveals, and without a count of them a report cannot
-- say how much of the application it saw — only how many URLs it visited.
--
-- Counted per state reached, not per finding: a state that turned out to be
-- clean is still coverage the scan gained.
ALTER TABLE scans ADD COLUMN interaction_states_total INTEGER NOT NULL DEFAULT 0;
ALTER TABLE scans ADD COLUMN interaction_pages_probed INTEGER NOT NULL DEFAULT 0;
