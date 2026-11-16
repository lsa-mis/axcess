-- 0033 — a review's yes/no "confirmed" becomes a three-way decision.
--
-- A person's choice about an element in the page inspector is one of:
--
-- * NULL: not checked yet;
-- * 'report': checked, a real problem to put in the report;
-- * 'repeat': checked, a real problem that repeats one already reported,
--   so it stays out of the report. Which elements are repeats is the
--   person's call; Axcess does not decide it.
--
-- SQLite cannot change a column's constraint in place, so the table is
-- rebuilt and every review kept: confirmed = 1 becomes 'report', 0 becomes
-- NULL. The table's keys, cascades and indexes are as 0032 made them.
CREATE TABLE occurrence_reviews_0033 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    a11y_finding_id INTEGER REFERENCES page_a11y_findings(id) ON DELETE CASCADE,
    page_image_id INTEGER REFERENCES page_images(id) ON DELETE CASCADE,
    decision TEXT CHECK (decision IN ('report', 'repeat')),
    notes TEXT NOT NULL DEFAULT '' CHECK (length(notes) <= 2000),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((a11y_finding_id IS NULL) != (page_image_id IS NULL))
);

INSERT INTO occurrence_reviews_0033
    (id, scan_id, page_id, a11y_finding_id, page_image_id, decision, notes, updated_at)
SELECT id, scan_id, page_id, a11y_finding_id, page_image_id,
       CASE WHEN confirmed = 1 THEN 'report' END, notes, updated_at
  FROM occurrence_reviews;

DROP TABLE occurrence_reviews;
ALTER TABLE occurrence_reviews_0033 RENAME TO occurrence_reviews;

CREATE UNIQUE INDEX idx_occurrence_reviews_a11y
    ON occurrence_reviews(a11y_finding_id) WHERE a11y_finding_id IS NOT NULL;
CREATE UNIQUE INDEX idx_occurrence_reviews_image
    ON occurrence_reviews(page_image_id) WHERE page_image_id IS NOT NULL;
CREATE INDEX idx_occurrence_reviews_page ON occurrence_reviews(scan_id, page_id);
