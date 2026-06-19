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
  /**
   * URLs currently leased by a worker — the things being fetched *right
   * now*, not yet recorded in the pages table. Useful for live activity.
   */
  in_flight_pages: {
    url: string;
    depth: number;
    attempts: number;
    lease_until: string | null;
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
  /** Pages on which axe successfully ran. Always ≤ page_count. */
  axe_pages_scanned: number;
  /** Total axe-core violation rows for the scan, across all pages. */
  axe_violations_total: number;
  /**
   * Coverage truth: which detection methods were enabled for this scan,
   * derived server-side from the stored scan config + counters. Lets
   * the detail page flag partial / static-only runs at a glance.
   */
  methods_used: { key: string; label: string; enabled: boolean }[];
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
  /**
   * Opt-OUT fast path: fetch pages with plain HTTP instead of rendering
   * each one in Playwright. Disables the axe, keyboard, and responsive
   * checks on statically-fetched pages — full rendering is the default
   * because three of the four pipelines need a live DOM.
   */
  static_only: boolean;
  skip_axe: boolean;
  skip_keyboard: boolean;
  skip_responsive: boolean;
  axe_level: "A" | "AA" | "AAA";
}

// ---------------------------------------------------------------
// WCAG axe-core findings (separate pipeline from 1.4.5 image-of-text).
// Sourced from the `page_a11y_findings` table; per-scan roll-up is
// served by /api/scans/{id}/a11y, drill-down by .../findings.
// ---------------------------------------------------------------

export type AxeImpact = "critical" | "serious" | "moderate" | "minor";
export type WcagLevel = "A" | "AA" | "AAA";

export interface A11yRuleSummary {
  rule_id: string;
  impact: AxeImpact | null;
  help: string;
  help_url: string;
  violation_count: number;
  page_count: number;
}

export interface A11ySCGroup {
  wcag_sc: string | null; // null for best-practice (no SC)
  wcag_level: WcagLevel | null;
  violation_count: number;
  page_count: number;
  worst_impact: AxeImpact | null;
  rules: A11yRuleSummary[];
}

export interface A11yRollup {
  coverage: {
    pages_total: number;
    axe_pages_scanned: number;
    axe_violations_total: number;
  };
  by_level: { A: number; AA: number; AAA: number; best_practice: number };
  by_impact: Record<string, number>;
  by_status: Record<FindingStatus, number>;
  groups: A11ySCGroup[];
}

// ---------------------------------------------------------------
// Image-of-text findings (WCAG 1.4.5 pipeline) grouped by
// `(classification, alt_adequacy)` — every group shares one
// remediation hint. Served by /api/scans/{id}/findings/grouped.
// ---------------------------------------------------------------

export type AltAdequacy = "missing" | "inadequate" | "partial" | "adequate";

export interface GroupedFindingOccurrence {
  page_id: number;
  page_url: string;
  page_title: string | null;
  alt_text: string | null;
  above_fold: boolean;
  position: number;
  context_snippet: string | null;
}

export interface GroupedFinding {
  id: number;
  severity: Severity;
  status: FindingStatus;
  priority_score: number;
  classification: Classification | null;
  alt_adequacy: AltAdequacy;
  remediation_hint: string | null;
  ocr_text: string | null;
  ocr_confidence: number | null;
  vlm_rationale: string | null;
  image_url: string;
  content_hash: string;
  mime: string | null;
  has_svg_text: boolean;
  occurrences: GroupedFindingOccurrence[];
}

export interface FindingsGroup {
  classification: Classification | null;
  alt_adequacy: AltAdequacy;
  label: string;
  remediation_hint: string | null;
  finding_count: number;
  occurrence_count: number;
  severity_breakdown: Record<Severity, number>;
  status_breakdown: Partial<Record<FindingStatus, number>>;
  worst_severity: Severity;
  findings: GroupedFinding[];
}

export interface GroupedFindingsResponse {
  coverage: {
    finding_count: number;
    page_count: number;
    occurrence_total: number;
  };
  groups: FindingsGroup[];
}

// ---------------------------------------------------------------
// Unified Issues view (Siteimprove-style). Both pipelines collapsed
// to one IssueRow per "issue", served by /api/scans/{id}/issues.
// ---------------------------------------------------------------

export type ConformanceLabel = "A" | "AA" | "AAA" | "BP";
export type AbilityLabel = "vision" | "cognition" | "motor" | "hearing";

export interface IssueRow {
  pipeline: "axe" | "image";
  issue_key: string;
  title: string;
  conformance: ConformanceLabel;
  wcag_sc: string | null;
  wcag_name: string | null;
  responsibility: string;
  abilities_affected: AbilityLabel[];
  difficulty: string;
  occurrence_count: number;
  page_count: number;
  priority: number;
  impact: string | null;
  status_summary: Record<string, number>;
  detail_url: string;
  finding_ids: number[];
  // Inline expansion content — populated from rules/audit_report.yaml.
  // The Issues list cards surface what/why/how directly from these
  // fields without a second API call to the detail endpoint.
  description: string | null;
  why_matters: string | null;
  fix_steps: string[];
  acceptance: string | null;
  help_url: string | null;
}

export interface IssuePage {
  page_id: number;
  page_url: string;
  page_title: string | null;
  occurrence_count: number;
  status_summary: Record<string, number>;
}

export interface IssueDetail {
  row: IssueRow;
  pages: IssuePage[];
  description: string | null;
  why_matters: string | null;
  fix_steps: string[];
  verify_manual: string | null;
  verify_automated: string | null;
  acceptance: string | null;
  help_url: string | null;
}

export interface IssuesResponse {
  rows: IssueRow[];
  conformance_counts: Record<ConformanceLabel, number>;
  responsibility_counts: Record<string, number>;
  abilities_counts: Record<AbilityLabel | string, number>;
  total_unfiltered: number;
}

// ---------------------------------------------------------------
// WCAG axe findings grouped by *rule* — the fixing axis. Pairs with
// the by-SC rollup at /api/scans/{id}/a11y, which is the reporting axis.
// Served by /api/scans/{id}/a11y/by-rule.
// ---------------------------------------------------------------

export interface A11yRuleGroupFinding {
  id: number;
  page_id: number;
  page_url: string;
  page_title: string | null;
  target_selector: string;
  failure_summary: string | null;
  html_snippet: string | null;
  status: FindingStatus;
}

export interface A11yRuleGroup {
  rule_id: string;
  impact: AxeImpact | null;
  help: string;
  help_url: string;
  wcag_sc: string | null;
  wcag_scs: string | null;
  wcag_level: WcagLevel | null;
  violation_count: number;
  page_count: number;
  status_breakdown: Record<FindingStatus, number>;
  findings: A11yRuleGroupFinding[];
}

export interface A11yByRuleResponse {
  coverage: {
    pages_total: number;
    axe_pages_scanned: number;
    axe_violations_total: number;
  };
  groups: A11yRuleGroup[];
}

export interface A11yDrillFinding {
  id: number;
  rule_id: string;
  impact: AxeImpact | null;
  help: string;
  help_url: string;
  target_selector: string;
  failure_summary: string | null;
  html_snippet: string | null;
  status: FindingStatus;
  wcag_sc: string | null;
  wcag_level: WcagLevel | null;
  page_id: number;
  page_url: string;
  page_title: string | null;
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
