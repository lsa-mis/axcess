import type {
  A11yByRuleResponse,
  A11yDrillFinding,
  A11yRollup,
  AbilityLabel,
  AlfaCapability,
  ConformanceLabel,
  IssueDetail,
  EvaluationRecord,
  ManualChecksResponse,
  ManualOutcome,
  PageEvidence,
  DiffReport,
  FindingDetail,
  FindingsFilter,
  FindingsPage,
  FindingStatus,
  GroupedFindingsResponse,
  IssuesResponse,
  LocalLoginScanPayload,
  LocalLoginScanState,
  NewScanPayload,
  ProtectedAgentEnrollmentResponse,
  ProtectedCompanionStartResponse,
  ProtectedCompanionStatusResponse,
  ProtectedIdentityContextResponse,
  ProtectedManualChecksResponse,
  ProtectedIssueIndexResponse,
  ProtectedScansResponse,
  ProtectedScanCreateResponse,
  ProtectedScanCapability,
  ProtectedScanPayload,
  ProtectedScanRecord,
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

/**
 * Deliver the protected report's deliberately redacted Markdown summary.
 *
 * This is intentionally not an ``exportUrl`` anchor: the server requires an
 * explicit same-origin POST so it can verify the proxy identity, enforce
 * retention/completion state, and record the authorized download. The browser
 * receives a one-shot Blob only to trigger the recipient-controlled download;
 * Axcess never writes a generated protected export to server storage.
 */
async function downloadProtectedRedactedExport(scanId: number): Promise<void> {
  const input = `/api/protected-scans/${scanId}/exports/redacted`;
  const res = await fetch(input, {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: { Accept: "text/markdown" },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`POST ${input} → ${res.status}: ${body.slice(0, 200)}`);
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = `protected_scan_${scanId}_redacted.md`;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

export const api = {
  listScans: () => request<ScanSummary[]>("/api/scans"),
  getScan: (id: number) => request<ScanDetail>(`/api/scans/${id}`),
  getAlfaCapability: () => request<AlfaCapability>("/api/capabilities/alfa"),
  getProtectedScanCapability: () =>
    request<ProtectedScanCapability>("/api/capabilities/protected-scans"),
  createLocalLoginScan: (payload: LocalLoginScanPayload) =>
    request<LocalLoginScanState>("/api/local-login-scans", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getLocalLoginScan: (scanId: number) =>
    request<LocalLoginScanState>(`/api/local-login-scans/${scanId}`, {
      cache: "no-store",
    }),
  confirmLocalLogin: (scanId: number) =>
    request<LocalLoginScanState>(`/api/local-login-scans/${scanId}/confirm`, {
      method: "POST",
    }),
  getEvaluation: (scanId: number) =>
    request<EvaluationRecord>(`/api/scans/${scanId}/evaluation`),
  updateEvaluation: (scanId: number, payload: Partial<EvaluationRecord>) =>
    request<EvaluationRecord>(`/api/scans/${scanId}/evaluation`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  getManualChecks: (scanId: number) =>
    request<ManualChecksResponse>(`/api/scans/${scanId}/manual-checks`),
  updateManualCheck: (
    scanId: number,
    criterion: string,
    payload: { outcome: ManualOutcome; rationale: string },
  ) =>
    request(`/api/scans/${scanId}/manual-checks/${encodeURIComponent(criterion)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  addManualEvidence: (
    scanId: number,
    criterion: string,
    payload: { note: string; page_id?: number; evidence_url?: string },
  ) =>
    request(`/api/scans/${scanId}/manual-checks/${encodeURIComponent(criterion)}/evidence`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getPageEvidence: (scanId: number, pageId: number) =>
    request<PageEvidence>(`/api/scans/${scanId}/pages/${pageId}`),
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
  /**
   * Create an authorized protected-scan draft. This request contains scope
   * and acknowledgement metadata only — never browser/session credentials.
   * The auditor completes 1FA/MFA later in the paired local companion.
   */
  createProtectedScan: (payload: ProtectedScanPayload) =>
    request<ProtectedScanCreateResponse>("/api/protected-scans", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  /**
   * An opaque identity partition for protected browser cache isolation.
   * Never persist this response; it is refreshed on mount, focus, and a
   * short bounded interval by ``useProtectedIdentityContext``.
   */
  getProtectedIdentityContext: () =>
    request<ProtectedIdentityContextResponse>("/api/protected-scans/identity-context", {
      cache: "no-store",
    }),
  /** Non-secret protected-scan status / retention metadata. */
  getProtectedScan: (id: number) =>
    request<ProtectedScanRecord>(`/api/protected-scans/${id}`),
  listProtectedScans: () => request<ProtectedScansResponse>("/api/protected-scans"),
  getProtectedIssueIndex: (scanId: number) =>
    request<ProtectedIssueIndexResponse>(`/api/protected-scans/${scanId}/issue-index`),
  /**
   * Protected reports retain only manual outcomes. The server never returns
   * or accepts a rationale, page link, evidence URL, or evidence note here.
   */
  getProtectedManualChecks: (scanId: number) =>
    request<ProtectedManualChecksResponse>(
      `/api/protected-scans/${scanId}/manual-checks`,
    ),
  updateProtectedManualCheck: (
    scanId: number,
    criterion: string,
    payload: { outcome: ManualOutcome },
  ) =>
    request(
      `/api/protected-scans/${scanId}/manual-checks/${encodeURIComponent(criterion)}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    ),
  /**
   * Create one scan-bound companion enrollment. The code in the response is
   * intentionally available only from this POST response; the UI never
   * retrieves or copies it automatically.
   */
  createProtectedAgentEnrollment: (scanId: number, certificateFingerprint: string) =>
    request<ProtectedAgentEnrollmentResponse>(
      `/api/protected-scans/${scanId}/agent-enrollments`,
      {
        method: "POST",
        body: JSON.stringify({ certificate_fingerprint: certificateFingerprint }),
      },
    ),
  /** Safe re-run command for the already paired companion; never a pairing secret. */
  getProtectedCompanion: (scanId: number) =>
    request<ProtectedCompanionStatusResponse>(
      `/api/protected-scans/${scanId}/companion`,
    ),
  /** Ask a paired companion to open its headed browser for manual sign-in. */
  startProtectedCompanion: (scanId: number) =>
    request<ProtectedCompanionStartResponse>(
      `/api/protected-scans/${scanId}/companion-start`,
      { method: "POST" },
    ),
  stopProtectedScan: (scanId: number) =>
    request<ProtectedScanRecord>(`/api/protected-scans/${scanId}/stop`, { method: "POST" }),
  /** Explicit, identity-protected download of the minimal redacted summary. */
  downloadProtectedRedactedExport,
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
  setStatus: (id: number, status: FindingStatus, rationale?: string) =>
    request<{ status: FindingStatus }>(`/api/findings/${id}/status`, {
      method: "POST",
      body: JSON.stringify({ status, rationale }),
    }),
  getDiff: (currentId: number, compareToId: number) =>
    request<DiffReport>(
      `/api/scans/${currentId}/diff?compare_to=${compareToId}`,
    ),
  /**
   * Per-scan WCAG DOM-engine roll-up: source-attributed coverage + counts
   * by SC, level, and impact. Empty arrays are valid when no selected engine
   * produced a retained finding.
   */
  getA11yRollup: (scanId: number) =>
    request<A11yRollup>(`/api/scans/${scanId}/a11y`),
  /**
   * Per-rule rollup — the actionable cut. Where `getA11yRollup`
   * groups by WCAG SC (the reporting axis), this groups by engine and
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
  setA11yStatus: (id: number, status: FindingStatus, rationale?: string) =>
    request<{ status: FindingStatus }>(
      `/api/a11y-findings/${id}/status`,
      {
        method: "POST",
        body: JSON.stringify({ status, rationale }),
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
  bulkSetStatus: (findingIds: number[], status: FindingStatus, rationale?: string) =>
    request<{ status: FindingStatus; updated: number }>(
      "/api/findings/bulk-status",
      {
        method: "POST",
        body: JSON.stringify({ finding_ids: findingIds, status, rationale }),
      },
    ),
  bulkSetA11yStatus: (findingIds: number[], status: FindingStatus, rationale?: string) =>
    request<{ status: FindingStatus; updated: number }>(
      "/api/a11y-findings/bulk-status",
      {
        method: "POST",
        body: JSON.stringify({ finding_ids: findingIds, status, rationale }),
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
      review_lane?: "likely_barrier" | "expert_review" | "informational" | "";
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

/** Download URL for a scan export; incomplete reports require explicit draft acknowledgement. */
export const exportUrl = (scanId: number, format: string, acknowledgedDraft = false): string =>
  `/api/scans/${scanId}/export/${format}${acknowledgedDraft ? "?draft=acknowledged" : ""}`;
