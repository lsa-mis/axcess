-- 0032 — a person's review of one occurrence: confirmed or not, and notes.
--
-- An auditor reviews each circled element in the page inspector, one page
-- state at a time, and either confirms it is a real problem or leaves it.
-- The notes are what they would write in the Issue notes column of the
-- U-M ITS technical review. One row per occurrence:
--
-- * a rule-check occurrence is a page_a11y_findings row (a11y_finding_id);
-- * an image-text occurrence is an image placed on a page, a page_images row
--   (page_image_id), the unit the inspector outlines.
--
-- Exactly one of the two is set. This is separate from the occurrence's
-- status: "In progress" means a fix is planned, which is not the same as
-- "a person looked at it and agrees". scan_id and page_id are kept so a
-- review is always read and written within one report. Every foreign key
-- cascades, so deleting a scan, a page, or an occurrence deletes its review.
--
-- 0033 replaces the yes/no "confirmed" with a three-way decision. This file
-- stays as it was first applied: a migration already applied to a database
-- is never edited, because the migration tool does not run it again.
CREATE TABLE occurrence_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    a11y_finding_id INTEGER REFERENCES page_a11y_findings(id) ON DELETE CASCADE,
    page_image_id INTEGER REFERENCES page_images(id) ON DELETE CASCADE,
    confirmed INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1)),
    notes TEXT NOT NULL DEFAULT '' CHECK (length(notes) <= 2000),
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((a11y_finding_id IS NULL) != (page_image_id IS NULL))
);

CREATE UNIQUE INDEX idx_occurrence_reviews_a11y
    ON occurrence_reviews(a11y_finding_id) WHERE a11y_finding_id IS NOT NULL;
CREATE UNIQUE INDEX idx_occurrence_reviews_image
    ON occurrence_reviews(page_image_id) WHERE page_image_id IS NOT NULL;
CREATE INDEX idx_occurrence_reviews_page ON occurrence_reviews(scan_id, page_id);
