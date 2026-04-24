/**
 * Shared types for the /api/* surface the FastAPI backend exposes.
 * Keep these in sync with the Pydantic response models in
 * ``src/audit/web/server.py``.
 */

export type Severity = "critical" | "major" | "minor" | "info";

export type FindingStatus =
  | "new"
  | "reviewing"
  | "in_progress"
  | "remediated"
  | "accepted_risk"
  | "false_positive";

export type Classification =
  | "essential"
  | "informational"
  | "logo"
  | "decorative"
  | "no_meaningful_text";

export type ScanStatus =
  | "running"
  | "completed"
  | "failed"
  | "interrupted";

export interface ScanSummary {
  id: number;
  seed_url: string;
  status: ScanStatus;
  page_count: number;
  finding_count: number;
  started_at: string | null;
  finished_at: string | null;
}

export interface ScanProgress {
  pending: number;
  leased: number;
  failed: number;
  images_seen: number;
  recent_pages: {
    url_normalized: string;
    status_code: number | null;
    render_mode: string;
    fetched_at: string | null;
  }[];
}

export interface ScanDetail extends ScanSummary {
  error_count: number;
  by_severity: Record<Severity, number>;
  previous_scan_id: number | null;
  blocked: null | {
    status_code: number;
    title: string | null;
    seed_url: string;
    page_count: number;
  };
  progress: ScanProgress | null;
}

export interface FindingListItem {
  id: number;
  severity: Severity;
  priority_score: number;
  status: FindingStatus;
  vlm_classification: Classification | null;
  ocr_text: string | null;
  src_url_canonical: string;
  src_url_short: string;
  content_hash: string | null;
  has_svg_text: boolean;
  mime: string | null;
  width: number | null;
  height: number | null;
  sample_alt: string | null;
  sample_page: string | null;
}

export interface FindingOccurrence {
  page_id: number;
  page_url: string;
  alt_text: string | null;
  above_fold: boolean;
}

export interface FindingDetail {
  id: number;
  scan_id: number;
  severity: Severity;
  status: FindingStatus;
  priority_score: number;
  wcag_criterion: string;
  remediation_hint: string | null;
  content_hash: string | null;
  blob_path: string | null;
  mime: string | null;
  width: number | null;
  height: number | null;
  has_svg_text: boolean;
  src_url_canonical: string;
  ocr_text: string | null;
  ocr_confidence: number | null;
  vlm_classification: Classification | null;
  vlm_rationale: string | null;
  occurrences: FindingOccurrence[];
}

export interface FindingsPage {
  findings: FindingListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface Pagination {
  page: number;
  page_size: number;
}

export interface FindingsFilter extends Pagination {
  severity?: Severity | "";
  status?: FindingStatus | "";
  classification?: Classification | "";
  q?: string;
}

export interface ScopePreview {
  normalized_url: string;
  host: string;
  path_prefix: string;
  auto_slash_added: boolean;
  whole_host: boolean;
  error: string | null;
}

export interface NewScanPayload {
  url: string;
  max_pages: number;
  max_depth: number;
  rps: number;
  workers: number;
  include_subdomain: boolean;
  whole_host: boolean;
  ignore_robots: boolean;
  skip_ocr: boolean;
  skip_vlm: boolean;
  js_eager: boolean;
}

export interface DiffEntry {
  content_hash: string;
  url_normalized: string;
  image_id: number;
  severity: Severity | null;
  previous_severity: Severity | null;
  current_finding_id: number | null;
  previous_finding_id: number | null;
  current_status: FindingStatus | null;
  previous_status: FindingStatus | null;
}

export interface DiffReport {
  current_scan_id: number;
  compare_to_scan_id: number;
  counts: Record<"new" | "resolved" | "still_open" | "status_changed", number>;
  new: DiffEntry[];
  resolved: DiffEntry[];
  still_open: DiffEntry[];
  status_changed: DiffEntry[];
}
