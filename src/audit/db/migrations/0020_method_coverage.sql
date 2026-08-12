-- 0020 — persist completed-page coverage for non-engine scan methods.
--
-- These counters record that a method actually evaluated a page even when it
-- produced zero findings.  Configuration alone is not evidence that a method
-- ran: the semantic provider may be unavailable and browser-only probes cannot
-- run on a static response.

ALTER TABLE scans ADD COLUMN semantic_pages_analyzed INTEGER NOT NULL DEFAULT 0
    CHECK (semantic_pages_analyzed >= 0);
ALTER TABLE scans ADD COLUMN keyboard_pages_probed INTEGER NOT NULL DEFAULT 0
    CHECK (keyboard_pages_probed >= 0);
ALTER TABLE scans ADD COLUMN responsive_pages_probed INTEGER NOT NULL DEFAULT 0
    CHECK (responsive_pages_probed >= 0);
