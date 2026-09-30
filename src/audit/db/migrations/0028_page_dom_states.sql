-- 0028 — keep the markup of the DOM states a click revealed.
--
-- pages.rendered_html is the *load* state: it is captured before the
-- interaction probe operates anything. A defect the probe only reached by
-- opening a menu or a dialog therefore has no markup anywhere in the report,
-- and the inspector could only tell the reviewer it had not found the element
-- "in this capture" — true, but it was never going to be there. This table is
-- the missing document.
--
-- Keyed on state_key, not on the control's name. An unlabelled control falls
-- back to its tag name, so every unnamed icon button on a page answers to the
-- string "<button>"; state_key is the probe's own interaction key
-- (scope|selector|label) and stays distinct per DOM location. Showing a
-- finding the wrong control's markup would put the reviewer back in front of
-- an element that is not there, which is the failure this whole table exists
-- to remove.
--
-- One row per (page, state). A page that is fetched again replaces its rows
-- wholesale: upsert_page overwrites rendered_html, so states captured against
-- the previous document describe markup the report no longer holds.
CREATE TABLE page_dom_states (
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    -- The probe's interaction key for the control that produced this state.
    state_key TEXT NOT NULL,
    -- Accessible name of that control, for display. Not unique.
    revealed_by TEXT NOT NULL DEFAULT '',
    -- JSON array of the control labels operated to arrive here, ending with
    -- this state's own. A depth number tells an auditor nothing; the chain is
    -- the reproduction recipe.
    path_labels TEXT NOT NULL DEFAULT '[]',
    -- How `dom` is encoded. Only 'gzip' is written today; the column exists so
    -- a future format does not need another migration to tell them apart.
    encoding TEXT NOT NULL DEFAULT 'gzip',
    dom BLOB NOT NULL,
    captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (page_id, state_key)
);

-- The inspector asks "which states does this page have?" on every open, and
-- the export path asks per scan.
CREATE INDEX idx_dom_states_scan ON page_dom_states(scan_id);

-- A finding's link to the state it was first flagged in. NULL for findings
-- present at page load, and for reports that predate this column.
ALTER TABLE page_a11y_findings ADD COLUMN revealed_state_key TEXT;
