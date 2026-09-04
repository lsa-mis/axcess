-- Bounded search outcomes, separate from page counts and DOM click probes.
CREATE TABLE scan_search_runs (
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    states INTEGER NOT NULL DEFAULT 0,
    discovered INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (scan_id, page_id)
);
