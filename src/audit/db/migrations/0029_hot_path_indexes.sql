-- 0029 — index the three lookups that were reading whole tables.
--
-- None of these change what a query returns. Each one replaces a scan with
-- a covering index seek on a predicate the code already writes, verified
-- with EXPLAIN QUERY PLAN against a 3,390-finding database.

-- 1. Which jobs belong to this scan?
--
-- Every queue operation asks this: leasing the next page, counting the
-- frontier between leases, purging out-of-scope jobs, reporting crawl
-- progress, cancelling and deleting a scan. The scan id lives inside
-- payload_json, so `idx_jobs_state_kind` could only narrow to
-- (state, kind) and SQLite then evaluated json_extract row by row over
-- everything still pending. Lease cost therefore grew with the size of the
-- frontier, which is the one thing that grows during a crawl.
--
-- An index on the expression, rather than a generated column, because the
-- callers already spell the predicate exactly this way: SQLite matches the
-- indexed expression against the query text, so queue.py, the orchestrator
-- and the progress endpoints all start using this with no code change.
-- Keep the expression here byte-identical to the one in those queries.
--
-- state, kind and id trail the expression so the lease query -- filter on
-- (scan, state, kind), take the lowest id -- is answered by the index alone.
CREATE INDEX idx_jobs_scan
    ON jobs(json_extract(payload_json, '$.scan_id'), state, kind, id);

-- 2. Which finding owns this screenshot blob?
--
-- `serve_blob` resolves a content hash back to the finding that captured it
-- to decide whether the caller may see it. That ran as a full table scan of
-- page_a11y_findings, once per thumbnail, and an evidence page requests many.
--
-- Partial: about two thirds of findings have no screenshot, and a NULL hash
-- is never looked up. This keeps the index to the rows that can match and
-- keeps the write cost off findings that captured nothing.
CREATE INDEX idx_a11y_screenshot
    ON page_a11y_findings(screenshot_hash)
    WHERE screenshot_hash IS NOT NULL;

-- 3. Group a scan's findings by rule, and list the pages for one rule.
--
-- These two shapes are the Issues projection. `idx_a11y_pipeline` stopped at
-- (scan_id, pipeline), so the rule filter was a per-row comparison and the
-- page grouping needed a temporary B-tree. Carrying rule_id and page_id in
-- the index answers both from the index alone, sorted.
--
-- This supersedes what `idx_a11y_rule` (rule_id alone) was being used for;
-- that index is kept because a cross-scan rule lookup has no leading
-- scan_id to offer this one.
CREATE INDEX idx_a11y_rule_lookup
    ON page_a11y_findings(scan_id, pipeline, rule_id, page_id);

-- Give the planner statistics for the new indexes. Without a sqlite_stat1
-- table SQLite guesses selectivity, and these three all overlap with an
-- existing index it could pick instead.
ANALYZE;
