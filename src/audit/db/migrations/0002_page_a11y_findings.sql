-- 0002 — per-page axe-core violations.
--
-- The original `findings` table is keyed on `(image_id, scan_id)` and
-- exists to track WCAG 1.4.5 (Images of Text) — the product's first and
-- most-developed criterion. Adding axe-core's general WCAG 2.1 AA pass
-- means we now produce *page-scoped* DOM violations whose identity is
-- `(page_id, rule_id, target_selector)`, not `(image, scan)`. Different
-- key, different lifecycle (image findings dedupe by `content_hash`
-- across pages; axe findings live and die with their page), and a
-- different audience (image findings drive Sam's content-editor work;
-- axe findings drive a developer's CSS/template work).
--
-- Two tables, one UI. Cleaner than overloading `findings` with a kind
-- column and a sparse mass of nullable fields per kind.

CREATE TABLE page_a11y_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    -- axe rule id, e.g. "color-contrast", "image-alt", "label".
    rule_id TEXT NOT NULL,
    -- Primary WCAG SC the rule maps to, e.g. "1.4.3". One axe rule can
    -- map to multiple SCs; we store the most-specific one and keep the
    -- rest in the comma-separated `wcag_scs` column for completeness.
    wcag_sc TEXT,
    wcag_scs TEXT,                       -- "1.4.3,1.4.6" if multi-mapped
    wcag_level TEXT,                     -- "A" | "AA" | "AAA" — most strict applicable
    -- Axe's own severity. We surface this alongside our 1.4.5 severity
    -- enum (`critical|major|minor|info`) so the operator can choose.
    impact TEXT CHECK (impact IN ('critical', 'serious', 'moderate', 'minor') OR impact IS NULL),
    help TEXT NOT NULL,                  -- one-liner from axe ("Elements must have sufficient color contrast")
    help_url TEXT,                       -- deeplink to dequeuniversity / Deque docs
    target_selector TEXT NOT NULL,       -- CSS selector axe returns for the failing node
    failure_summary TEXT,                -- multi-line why-it-failed, plain text
    html_snippet TEXT,                   -- short snippet of the failing element
    -- Dedupe key for the (page, rule, target) tuple. Re-running an axe
    -- pass on the same page upserts, doesn't pile up rows.
    target_hash TEXT NOT NULL,
    -- Triage workflow — reuses the same vocabulary as `findings.status`
    -- so the SPA's StatusChip / shortcuts work without a second enum.
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'reviewing', 'in_progress', 'remediated', 'accepted_risk', 'false_positive')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (page_id, rule_id, target_hash)
);
CREATE INDEX idx_a11y_scan ON page_a11y_findings(scan_id);
CREATE INDEX idx_a11y_page ON page_a11y_findings(page_id);
CREATE INDEX idx_a11y_rule ON page_a11y_findings(rule_id);
CREATE INDEX idx_a11y_wcag_sc ON page_a11y_findings(wcag_sc);
CREATE INDEX idx_a11y_level ON page_a11y_findings(wcag_level);
CREATE INDEX idx_a11y_impact ON page_a11y_findings(impact);
CREATE INDEX idx_a11y_status ON page_a11y_findings(status);

-- Per-scan summary of axe coverage. Lets the UI say "axe ran on 47 of 50
-- pages" (static pages aren't axe-able without a browser; this column
-- counts the ones we actually scanned) without a heavy join.
ALTER TABLE scans ADD COLUMN axe_pages_scanned INTEGER NOT NULL DEFAULT 0;
ALTER TABLE scans ADD COLUMN axe_violations_total INTEGER NOT NULL DEFAULT 0;
