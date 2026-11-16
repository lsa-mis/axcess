-- Roll back 0032. Every saved review (confirmed marks and notes) is deleted.
DROP INDEX IF EXISTS idx_occurrence_reviews_page;
DROP INDEX IF EXISTS idx_occurrence_reviews_image;
DROP INDEX IF EXISTS idx_occurrence_reviews_a11y;
DROP TABLE occurrence_reviews;
