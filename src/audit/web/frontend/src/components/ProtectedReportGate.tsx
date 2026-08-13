import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useParams } from "react-router";
import { api } from "../api/client";
import { useProtectedIdentityContext } from "../hooks/useProtectedIdentityContext";
import { Card } from "./ui";

/**
 * Keep protected reports on their separate, permission-aware workflow.
 *
 * The browser API already rejects protected evidence for an unauthenticated
 * caller. This gate is the complementary UX control: it prevents a valid
 * protected user from landing on public-report navigation and export controls
 * that are intentionally unavailable for their report.
 */
export default function ProtectedReportGate({ children }: { children: ReactNode }) {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const validId = Number.isSafeInteger(id) && id > 0;
  const protectedIdentity = useProtectedIdentityContext();
  // This gate has to perform one generic lookup so legacy /scans/:id links
  // can redirect protected reports. Partition even that tiny response by the
  // current opaque proxy identity. A changed proxy session therefore cannot
  // reuse a prior user's cached protection summary to decide this gate.
  const identityPartition =
    protectedIdentity.fingerprint ?? "identity-context-unavailable";
  const scan = useQuery({
    queryKey: ["scan", id, "identity", identityPartition],
    queryFn: () => api.getScan(id),
    // Wait for a pending identity assertion. If protected identity is not
    // configured at all, its failed response makes this query available so
    // ordinary public reports remain usable.
    enabled: validId && !protectedIdentity.isChecking,
  });
  const isKnownPublicReport = scan.data !== undefined && scan.data.protection === undefined;

  if (!validId) return <>{children}</>;
  // A background identity refresh must continue to hide an authorized
  // protected report, but it must not unmount a report already established
  // as public. Unmounting every public report on the 15-second identity poll
  // collapsed long issue tables and reset the reader's scroll position.
  if (scan.isLoading || (protectedIdentity.isChecking && !isKnownPublicReport)) {
    return <p className="text-sm text-fg-muted" aria-live="polite">Loading report…</p>;
  }
  if (scan.error) {
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        {scan.error instanceof Error
          ? scan.error.message
          : "This report is unavailable."}
      </Card>
    );
  }
  if (scan.data?.protection?.mode === "protected") {
    if (protectedIdentity.error || !protectedIdentity.isReady) {
      return (
        <Card className="p-4 text-sm text-sev-critical" role="alert">
          {protectedIdentity.error instanceof Error
            ? protectedIdentity.error.message
            : "Protected-report access is unavailable."}
        </Card>
      );
    }
    return <Navigate to={`/scans/${id}/protected`} replace />;
  }
  return <>{children}</>;
}
