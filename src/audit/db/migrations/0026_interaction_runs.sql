-- Per-page ledger for "Click Through DOM States".
--
-- The scan-level counters added in 0024 answer "how many pages were probed"
-- and "how many DOM states were reached". They cannot answer the question an
-- auditor actually asks of an exploratory pass: of the controls this page
-- exposes, which ones were operated, and what stopped the rest. Discovery,
-- successful operation, refusal, and the bound that ended the sweep are
-- distinct facts, so they are stored as distinct columns rather than folded
-- into one "coverage" number that would have to be believed.
--
-- One row per (scan, page): the probe runs once per page load, and rerunning
-- a page (e.g. a re-fetch) replaces its ledger instead of double counting.
CREATE TABLE scan_interaction_runs (
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    -- Distinct controls the page exposed, including ones revealed by a click.
    controls_found INTEGER NOT NULL DEFAULT 0,
    -- Controls chosen for operation, whether or not the click landed.
    clicks_attempted INTEGER NOT NULL DEFAULT 0,
    -- Clicks actually dispatched, replays included.
    clicks_succeeded INTEGER NOT NULL DEFAULT 0,
    -- Distinct controls operated at least once. The honest coverage
    -- numerator against controls_found: reopening a menu to reach its next
    -- sibling is another click, not another control.
    controls_operated INTEGER NOT NULL DEFAULT 0,
    -- Clicks that changed the DOM, mirroring scans.interaction_states_total.
    states INTEGER NOT NULL DEFAULT 0,
    -- Controls refused because their label matched a blocked action.
    blocked_controls INTEGER NOT NULL DEFAULT 0,
    -- Dialogs a click opened, and how many refused to close again. A stuck
    -- dialog ends the page: its overlay covers every remaining control, so
    -- continuing would record clicks that only ever hit the overlay.
    dialogs_opened INTEGER NOT NULL DEFAULT 0,
    dialogs_stuck INTEGER NOT NULL DEFAULT 0,
    -- Comma-separated bounds that stopped the sweep: clicks, time, depth,
    -- repeated_controls, dialog_not_dismissed. Empty means no bound was
    -- reached on this page.
    limits TEXT NOT NULL DEFAULT '',
    -- Bounded reproduction note for a stuck dialog: which dialog, which
    -- control opened it, and what dismissal was attempted.
    detail TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (scan_id, page_id)
);
