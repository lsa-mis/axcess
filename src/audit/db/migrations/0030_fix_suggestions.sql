-- 0030 — AI fix suggestions, one row per request for one occurrence.
--
-- A suggestion is advice written by a local AI model on request. It never
-- changes the occurrence it is about: findings, statuses, issue grouping and
-- exports read none of this table. "Suggest again" adds a new row, so older
-- versions stay as history and the newest row is the one shown.
--
-- An occurrence lives in one of two tables, so it is named by kind + id:
--   * 'a11y'  → page_a11y_findings.id (rule checks, browser checks, AI review)
--   * 'image' → page_images.id (one image on one page)
-- There is no foreign key on occurrence_id because it can point at either
-- table. The service checks that it belongs to scan_id on every request, and
-- the scan and page cascades below remove the rows with their report.
CREATE TABLE fix_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    occurrence_kind TEXT NOT NULL CHECK (occurrence_kind IN ('a11y', 'image')),
    occurrence_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'ready', 'failed', 'cancelled')),
    audience_default TEXT NOT NULL CHECK (audience_default IN ('developer', 'editor')),
    text_model TEXT NOT NULL,
    vision_model TEXT,
    prompt_version TEXT NOT NULL,
    -- Validated model answer (audit.suggest.models.SuggestionResult). NULL
    -- until the row is ready.
    result_json TEXT,
    check_outcome TEXT
        CHECK (check_outcome IS NULL OR check_outcome IN ('passed', 'still_fails', 'not_checked')),
    -- A short machine code; the interface turns it into words.
    error_code TEXT,
    -- Only ever a model tag (for "Run: ollama pull <tag>"), never model or
    -- page text.
    error_detail TEXT,
    feedback TEXT CHECK (feedback IS NULL OR feedback IN ('helpful', 'not_helpful')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    started_at TEXT,
    finished_at TEXT
);

-- "Latest suggestion for this occurrence" and the per-occurrence version cap.
CREATE INDEX idx_fix_suggestions_occurrence
    ON fix_suggestions(scan_id, occurrence_kind, occurrence_id, id);

-- The worker's "next queued row" and the queue-length check.
CREATE INDEX idx_fix_suggestions_status ON fix_suggestions(status, id);
