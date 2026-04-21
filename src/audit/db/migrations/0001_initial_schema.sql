-- Initial schema for the image-text audit tool.
-- Covers scans, pages, images, page_images, analyses, findings, finding_history, jobs.

CREATE TABLE scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_url TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'interrupted')),
    config_json TEXT NOT NULL,
    page_count INTEGER NOT NULL DEFAULT 0,
    image_count INTEGER NOT NULL DEFAULT 0,
    finding_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    url_normalized TEXT NOT NULL,
    status_code INTEGER,
    title TEXT,
    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    render_mode TEXT NOT NULL CHECK (render_mode IN ('static', 'js')),
    html_hash TEXT,
    UNIQUE (scan_id, url_normalized)
);
CREATE INDEX idx_pages_scan ON pages(scan_id);
CREATE INDEX idx_pages_url ON pages(url_normalized);

CREATE TABLE images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL UNIQUE,
    src_url_canonical TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    bytes INTEGER,
    mime TEXT,
    blob_path TEXT,
    has_svg_text INTEGER NOT NULL DEFAULT 0,
    first_seen_scan_id INTEGER REFERENCES scans(id)
);
CREATE INDEX idx_images_hash ON images(content_hash);

CREATE TABLE page_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    alt_text TEXT,
    role TEXT,
    context_snippet TEXT,
    position INTEGER NOT NULL,
    bbox_json TEXT,
    above_fold INTEGER NOT NULL DEFAULT 0,
    UNIQUE (page_id, image_id, position)
);
CREATE INDEX idx_page_images_page ON page_images(page_id);
CREATE INDEX idx_page_images_image ON page_images(image_id);

CREATE TABLE analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    ocr_text TEXT,
    ocr_confidence REAL,
    vlm_classification TEXT,
    vlm_rationale TEXT,
    has_text INTEGER NOT NULL DEFAULT 0,
    analyzed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    model_versions_json TEXT NOT NULL,
    UNIQUE (image_id, model_versions_json)
);
CREATE INDEX idx_analyses_image ON analyses(image_id);

CREATE TABLE findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'major', 'minor', 'info')),
    wcag_criterion TEXT NOT NULL DEFAULT '1.4.5',
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'reviewing', 'in_progress', 'remediated', 'accepted_risk', 'false_positive')),
    priority_score REAL NOT NULL,
    remediation_hint TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (image_id, scan_id)
);
CREATE INDEX idx_findings_scan ON findings(scan_id);
CREATE INDEX idx_findings_image ON findings(image_id);
CREATE INDEX idx_findings_severity ON findings(severity);
CREATE INDEX idx_findings_status ON findings(status);

CREATE TABLE finding_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    scan_id INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    change_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    actor TEXT NOT NULL DEFAULT 'system' CHECK (actor IN ('system', 'user')),
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note TEXT
);
CREATE INDEX idx_finding_history_finding ON finding_history(finding_id);

CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'leased', 'completed', 'failed')),
    lease_until TIMESTAMP,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dedupe_key TEXT UNIQUE
);
CREATE INDEX idx_jobs_state_kind ON jobs(state, kind);
CREATE INDEX idx_jobs_lease ON jobs(lease_until) WHERE state = 'leased';
