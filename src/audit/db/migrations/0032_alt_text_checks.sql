-- 0032 — keep what the local model said about one image's alt text.
--
-- The Images tab (web/image_inventory.py) lets a person ask the local model,
-- for one image at a time, whether its alt text is good and what better alt
-- text could say. The answer is kept here, one row per image per report, so
-- the tab shows it again without asking the model a second time.
--
-- This is a person's request after the scan, not part of the scan: nothing
-- here changes `analyses` or `findings`, so a completed scan's evidence and
-- its reproducibility stay as they were. `model` and `prompt_version` say
-- exactly what wrote each row.
--
-- verdict is the model's view of alt text that exists: 'good' or
-- 'needs_better'. An image with no alt text needs alt text whatever a model
-- says, so that verdict is never stored; NULL means the model was asked only
-- for a suggestion. Deleting a report deletes its rows.
CREATE TABLE alt_text_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    verdict TEXT CHECK (verdict IS NULL OR verdict IN ('good', 'needs_better')),
    reason TEXT NOT NULL DEFAULT '',
    suggestion TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (scan_id, image_id)
);
