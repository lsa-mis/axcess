import type {
  A11yByRuleResponse,
  A11yDrillFinding,
  A11yRollup,
  AbilityLabel,
  ConformanceLabel,
  IssueDetail,
  DiffReport,
  FindingDetail,
  FindingsFilter,
  FindingsPage,
  FindingStatus,
  GroupedFindingsResponse,
  IssuesResponse,
  NewScanPayload,
  ScanDetail,
  ScanSummary,
  ScopePreview,
  TrackingData,
} from "./types";

/**
 * Thin fetch wrapper for the /api/* surface. Throws on non-2xx with the
 * response body text attached so React Query surfaces useful errors.
 */
async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const res = await fetch(input, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(
      `${init?.method ?? "GET"} ${input} → ${res.status}: ${body.slice(0, 200)}`,
    );
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listScans: () => request<ScanSummary[]>("/api/scans"),
  getScan: (id: number) => request<ScanDetail>(`/api/scans/${id}`),
  scopePreview: (url: string, wholeHost: boolean) => {
    const params = new URLSearchParams({ url });
    if (wholeHost) params.set("whole_host", "1");
    return request<ScopePreview>(`/api/scope-preview?${params}`);
  },
  createScan: (payload: NewScanPayload) =>
    request<{ scan_id: number }>("/api/scans", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  cancelScan: (id: number) =>
    request<{ ok: boolean }>(`/api/scans/${id}/cancel`, { method: "POST" }),
  /**
   * Permanently delete a scan and its findings/pages/jobs. Backend refuses
   * (409) if the scan is currently running — caller must `cancelScan` first.
   * Idempotent at the UI layer because we invalidate ["scans"] after.
   */
  deleteScan: (id: number) =>
    request<{ ok: boolean; deleted_scan_id: number }>(`/api/scans/${id}`, {
      method: "DELETE",
    }),
  /**
   * Image-of-text findings grouped by `(classification, alt_adequacy)`.
   * Each group's findings share one remediation hint — same key the
   * `rules/remediation.yaml` rule book uses. Optional `status` filter
   * narrows to a single triage state.
   */
  getGroupedFindings: (scanId: number, status?: FindingStatus | "") => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    return request<GroupedFindingsResponse>(
      `/api/scans/${scanId}/findings/grouped?${params}`,
    );
  },
  listFindings: (scanId: number, filter: FindingsFilter) => {
    const params = new URLSearchParams();
    params.set("page", String(filter.page));
    params.set("page_size", String(filter.page_size));
    if (filter.severity) params.set("severity", filter.severity);
    if (filter.status) params.set("status", filter.status);
    if (filter.classification) params.set("classification", filter.classification);
    if (filter.q) params.set("q", filter.q);
    return request<FindingsPage>(`/api/scans/${scanId}/findings?${params}`);
  },
  getFinding: (id: number) => request<FindingDetail>(`/api/findings/${id}`),
  setStatus: (id: number, status: FindingStatus) =>
    request<{ status: FindingStatus }>(`/api/findings/${id}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),
  getDiff: (currentId: number, compareToId: number) =>
    request<DiffReport>(
      `/api/scans/${currentId}/diff?compare_to=${compareToId}`,
    ),
  /**
   * Per-scan WCAG axe-core roll-up: coverage + counts by SC, level,
   * and impact. Empty arrays are valid (a scan with no axe pages or
   * no violations).
   */
  getA11yRollup: (scanId: number) =>
    request<A11yRollup>(`/api/scans/${scanId}/a11y`),
  /**
   * Per-rule rollup — the actionable cut. Where `getA11yRollup`
   * groups by WCAG SC (the reporting axis), this groups by axe
   * `rule_id` (the fixing axis): one CSS class fails contrast on
   * 800 pages → one group of 800, ready for one bulk-status decision.
   */
  getA11yByRule: (scanId: number, status?: FindingStatus | "") => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    return request<A11yByRuleResponse>(
      `/api/scans/${scanId}/a11y/by-rule?${params}`,
    );
  },
  /**
   * Drill-down list of individual axe violations for one WCAG SC.
   * Pass `null` (or omit) to get findings with no SC mapping —
   * axe's best-practice rules land there. The server treats an
   * empty-string query param as "SC IS NULL," so we have to
   * distinguish: undefined → no filter, null → best-practice only.
   *
   * Optional ``status`` narrows to a single triage state; pass
   * empty/undefined for "all statuses."
   */
  getA11yFindings: (
    scanId: number,
    wcagSc: string | null | undefined,
    status?: FindingStatus | "",
  ) => {
    const params = new URLSearchParams();
    if (wcagSc !== undefined) params.set("wcag_sc", wcagSc ?? "");
    if (status) params.set("status", status);
    return request<{ findings: A11yDrillFinding[] }>(
      `/api/scans/${scanId}/a11y/findings?${params}`,
    );
  },
  /**
   * Update an axe finding's triage status. Mirrors `setStatus` for the
   * image-of-text findings; same status enum, separate table.
   */
  setA11yStatus: (id: number, status: FindingStatus) =>
    request<{ status: FindingStatus }>(
      `/api/a11y-findings/${id}/status`,
      {
        method: "POST",
        body: JSON.stringify({ status }),
      },
    ),
  /**
   * Bulk-update a set of image-of-text findings to the same status.
   * The natural call site is the grouped-by-issue view: every finding
   * in a group shares one fix, so one POST replaces N per-row calls.
   * Returns `{status, updated}` — the count is how many DB rows
   * changed (≤ length of finding_ids; ids that don't exist are dropped
   * silently in SQL).
   */
  bulkSetStatus: (findingIds: number[], status: FindingStatus) =>
    request<{ status: FindingStatus; updated: number }>(
      "/api/findings/bulk-status",
      {
        method: "POST",
        body: JSON.stringify({ finding_ids: findingIds, status }),
      },
    ),
  bulkSetA11yStatus: (findingIds: number[], status: FindingStatus) =>
    request<{ status: FindingStatus; updated: number }>(
      "/api/a11y-findings/bulk-status",
      {
        method: "POST",
        body: JSON.stringify({ finding_ids: findingIds, status }),
      },
    ),
  /**
   * Per-issue detail — Siteimprove-style "page 2".
   * Includes the IssueRow header data + every page that contributes
   * findings to this issue + the YAML-sourced description / fix /
   * verify content. The pages list is server-sorted; pass `sort` to
   * change the order.
   */
  getIssueDetail: (
    scanId: number,
    issueKey: string,
    sort: string = "occurrences_desc",
  ) => {
    const params = new URLSearchParams();
    params.set("sort", sort);
    return request<IssueDetail>(
      `/api/scans/${scanId}/issues/${encodeURIComponent(issueKey)}?${params}`,
    );
  },
  /**
   * Unified Issues table — one row per issue across both pipelines.
   * Filter args are flat strings (comma-separated for the multi-value
   * ones if we ever need that; today the backend takes single values).
   */
  listIssues: (
    scanId: number,
    filters: {
      conformance?: ConformanceLabel | "";
      responsibility?: string;
      abilities?: AbilityLabel | "";
      status?: FindingStatus | "";
      q?: string;
      sort?: string;
    } = {},
  ) => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(filters)) {
      if (v) params.set(k, v);
    }
    return request<IssuesResponse>(
      `/api/scans/${scanId}/issues?${params}`,
    );
  },
  /**
   * Coverage & feature tracker data — what's shipped vs. planned across
   * every detection pipeline. Served from the same source of truth as
   * docs/coverage-tracker.md (coverage_status.py), so the page can't
   * drift from the code.
   */
  getTracking: () => request<TrackingData>("/api/tracking"),
};

/** Direct URL (bypass fetch) for image blobs — used in <img src=…>. */
export const blobUrl = (contentHash: string): string =>
  `/blobs/${contentHash}`;

/** Download URL for a scan export; triggers a download via an <a> click. */
export const exportUrl = (scanId: number, format: string): string =>
  `/api/scans/${scanId}/export/${format}`;
