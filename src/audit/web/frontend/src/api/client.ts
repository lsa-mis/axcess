import type {
  DiffReport,
  FindingDetail,
  FindingsFilter,
  FindingsPage,
  FindingStatus,
  NewScanPayload,
  ScanDetail,
  ScanSummary,
  ScopePreview,
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
};

/** Direct URL (bypass fetch) for image blobs — used in <img src=…>. */
export const blobUrl = (contentHash: string): string =>
  `/blobs/${contentHash}`;

/** Download URL for a scan export; triggers a download via an <a> click. */
export const exportUrl = (scanId: number, format: string): string =>
  `/api/scans/${scanId}/export/${format}`;
