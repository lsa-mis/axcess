-- Roll back 0033: back to 0032's yes/no "confirmed". Both kinds of checked
-- ('report' and 'repeat') become confirmed = 1, so which elements were
-- repeats is lost; not checked yet becomes 0. Notes are kept.
CREATE TABLE occurrence_reviews_0032 (
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

INSERT INTO occurrence_reviews_0032
    (id, scan_id, page_id, a11y_finding_id, page_image_id, confirmed, notes, updated_at)
SELECT id, scan_id, page_id, a11y_finding_id, page_image_id,
       CASE WHEN decision IS NULL THEN 0 ELSE 1 END, notes, updated_at
  FROM occurrence_reviews;

DROP TABLE occurrence_reviews;
ALTER TABLE occurrence_reviews_0032 RENAME TO occurrence_reviews;

CREATE UNIQUE INDEX idx_occurrence_reviews_a11y
    ON occurrence_reviews(a11y_finding_id) WHERE a11y_finding_id IS NOT NULL;
CREATE UNIQUE INDEX idx_occurrence_reviews_image
    ON occurrence_reviews(page_image_id) WHERE page_image_id IS NOT NULL;
CREATE INDEX idx_occurrence_reviews_page ON occurrence_reviews(scan_id, page_id);
