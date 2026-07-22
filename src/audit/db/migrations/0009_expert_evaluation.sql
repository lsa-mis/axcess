-- 0009 — expert evaluation records layered on immutable crawl evidence.
--
-- A scan is a machine-collected snapshot. An evaluation records the
-- accessibility professional's scope, method, limitations, and manual WCAG
-- decisions without mutating the crawler's findings.

CREATE TABLE evaluation_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL UNIQUE REFERENCES scans(id) ON DELETE CASCADE,
    target_standard TEXT NOT NULL DEFAULT 'WCAG 2.2',
    target_level TEXT NOT NULL DEFAULT 'AA'
        CHECK (target_level IN ('A', 'AA', 'AAA')),
    purpose TEXT NOT NULL DEFAULT '',
    scope_included TEXT NOT NULL DEFAULT '',
    scope_excluded TEXT NOT NULL DEFAULT '',
    sample_description TEXT NOT NULL DEFAULT '',
    reviewer TEXT NOT NULL DEFAULT '',
    methods_note TEXT NOT NULL DEFAULT '',
    limitations TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'in_progress', 'completed')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_evaluation_reports_scan ON evaluation_reports(scan_id);

CREATE TABLE manual_check_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_report_id INTEGER NOT NULL
        REFERENCES evaluation_reports(id) ON DELETE CASCADE,
    criterion_sc TEXT NOT NULL,
    outcome TEXT NOT NULL DEFAULT 'not_started'
        CHECK (outcome IN ('not_started', 'pass', 'fail', 'not_tested', 'needs_follow_up')),
    rationale TEXT NOT NULL DEFAULT '',
    tested_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (evaluation_report_id, criterion_sc)
);
CREATE INDEX idx_manual_check_results_evaluation ON manual_check_results(evaluation_report_id);

CREATE TABLE manual_check_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manual_check_result_id INTEGER NOT NULL
        REFERENCES manual_check_results(id) ON DELETE CASCADE,
    page_id INTEGER REFERENCES pages(id) ON DELETE SET NULL,
    evidence_url TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_manual_check_evidence_result ON manual_check_evidence(manual_check_result_id);
