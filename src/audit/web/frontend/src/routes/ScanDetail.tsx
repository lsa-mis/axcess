/**
 * A report's own URL: progress while it runs, why it stopped if it failed,
 * and the report itself once it finishes.
 *
 * This route has three faces, chosen by scan status. Running shows the
 * progress panel and a cancel control. Failed or interrupted shows why and
 * offers a retry. Completed redirects to the Issues table, which is where a
 * report opens: it used to have an Overview tab of its own here, and its
 * numbers and coverage now sit above the table (see ``ReportSummary``). The
 * redirect keeps every existing ``/scans/:id`` link working, and a scan that
 * finishes while the reader watches lands them on its report.
 *
 * The mutations here are the scan's lifecycle actions -- cancel, retry --
 * and each has to reconcile the cache by hand afterwards, since they change
 * records other screens are already showing.
 */
import { Navigate, useNavigate, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { RETRY } from "../components/newScan/copy";
import { PUBLIC_DEFAULTS, quickRetrySettings } from "../components/newScan/scanPolicy";
import { BlockedScanNotice } from "../components/ReportSummary";
import ScanProgressView from "../components/ScanProgress";
import {
  Button,
  Card,
  LinkButton,
  PageHeader,
} from "../components/ui";
import { withoutUserinfo } from "../components/ReportCrumb";
import { SCAN_STATUS_LABEL } from "../lib/terms";
import { useScanQuery } from "../hooks/useScanQuery";

export default function ScanDetailRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [liveUpdates, setLiveUpdates] = useState(true);

  // Polls only while the scan is actually running, and only in a visible
  // tab. Shares the report summary cache entry with the gate and every
  // other report route; see useScanQuery.
  const { data, isLoading, error, isFetching } = useScanQuery(id, {
    refetchInterval: (query) =>
      liveUpdates && query.state.data?.status === "running" ? 2000 : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
  });
  // Invalidating on the `["scan", id]` prefix reaches the identity-
  // partitioned key the shared hook actually uses. Do not narrow it to an
  // exact key here without reading useScanQuery first.
  const cancel = useMutation({
    mutationFn: () => api.cancelScan(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scan", id] }),
  });
  // Two ways back from a scan that failed or was stopped, each saying what
  // it does ("Retry with balanced settings" left readers asking whether
  // their settings were kept; they were not):
  //
  // - "Change settings first" opens New scan with this scan's own
  //   settings filled in (`from=`), the path that keeps what they chose.
  // - "Scan again with faster settings" re-submits the same address at
  //   once with the default profile and Click-Through off
  //   (`quickRetrySettings`), which finishes
  //   quickly enough to show whether the site can be scanned at all. It
  //   keeps the WCAG version the report was audited against. A login scan
  //   has no quick retry: it cannot run without someone signing in.
  //
  // The settings query also says which tab the scan belongs to. A report it
  // cannot describe (a protected report, an older row) still gets an edit
  // link, prefilled with the address only.
  const previousSettings = useQuery({
    queryKey: ["scan-settings", id],
    queryFn: () => api.getScanSettings(id),
    enabled: Boolean(data) && data?.status !== "running" && data?.status !== "completed",
    retry: false,
    staleTime: Infinity,
  });
  const loginScan = previousSettings.data?.mode === "login";
  // A retry may produce a new scan id. When it does, navigate to it,
  // replacing history so Back does not return to a report that is now
  // superseded.
  const quickRetry = useMutation({
    mutationFn: () =>
      api.createScan(
        // A report loaded without a version falls back to the new-scan default.
        quickRetrySettings(data?.seed_url ?? "", data?.wcag_version ?? PUBLIC_DEFAULTS.wcag_version),
      ),
    onSuccess: async ({ scan_id }) => {
      setLiveUpdates(true);
      qc.removeQueries({ queryKey: ["issues", id] });
      await qc.invalidateQueries({ queryKey: ["scan", id] });
      await qc.invalidateQueries({ queryKey: ["scans"] });
      if (scan_id !== id) navigate(`/scans/${scan_id}`, { replace: true });
    },
  });

  if (error) {
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        {error instanceof Error ? error.message : String(error)}
      </Card>
    );
  }
  if (isLoading || !data) return <div className="text-fg-muted">Loading the scan…</div>;

  if (data.status === "running") {
    return (
      <ScanProgressView
        scan={data}
        cancel={cancel}
        liveUpdates={liveUpdates}
        isFetching={isFetching}
        onToggleLiveUpdates={() => setLiveUpdates((current) => !current)}
      />
    );
  }

  if (data.status === "completed") {
    return <Navigate replace to={`/scans/${data.id}/issues`} />;
  }

  return (
    <>
      <PageHeader title={`Report #${data.id}`} subtitle={withoutUserinfo(data.seed_url)} />

      {data.blocked && (
        <BlockedScanNotice scanId={data.id} blocked={data.blocked} />
      )}

      <Card className="p-5">
        {/* "No report was produced" was told to scans that had produced
            thousands of findings across hundreds of pages, because it keyed
            on the status rather than on whether anything was collected. A
            stopped scan keeps everything it reached; what it cannot claim is
            that the site was covered. Say that, and leave the evidence
            reachable.

            `page_count` is the live number of saved pages for any scan that
            has not completed (the server counts them, and Stop writes the
            count with the status). It used to be written only when the crawl
            wound down, so for about 15 seconds after Stop this card said "No
            report was produced" over pages that were saved. */}
        <h2 className="font-semibold text-fg">
          {data.page_count > 0 ? "Partial report" : "No report was produced"}
        </h2>
        <p className="mt-1 text-sm text-fg-muted">
          {data.page_count > 0 ? (
            <>
              This scan ended with the status{" "}
              <strong>{SCAN_STATUS_LABEL[data.status]}</strong> after{" "}
              {data.page_count.toLocaleString()} page
              {data.page_count === 1 ? "" : "s"}. Axcess saved everything it
              reached. The scan did not visit the rest of the site, so this
              report does not cover the whole site.
            </>
          ) : (
            <>
              This scan ended with the status{" "}
              <strong>{SCAN_STATUS_LABEL[data.status]}</strong> before any page
              finished. Axcess did not create a report.
            </>
          )}
        </p>
        {data.failure_reason && (
          <p className="mt-3 rounded-xs border border-sev-critical/30 bg-sev-critical-bg p-3 text-sm text-sev-critical">
            <strong>Why it failed:</strong> {data.failure_reason}
          </p>
        )}
        {quickRetry.error && (
          <p className="mt-3 text-sm text-sev-critical" role="alert">
            Axcess could not start this scan again: {quickRetry.error.message}
          </p>
        )}
        {/* Each action is one row of the same shape: a button of one width
            and, beside it, what it does, so the choice is made on the words
            and not on a guess at "balanced". "Review what the scan found"
            used to be added as a bare button of its own width with no words,
            so the card mixed two patterns (W3C COGA, "Making Content
            Usable": the same kind of thing looks and works the same way).

            One primary button per card, the likeliest next step. With a
            partial report that is reviewing what was saved, so it leads;
            with no report there is nothing to review, and changing the
            settings leads. The retries follow as secondary buttons. */}
        <ul className="mt-4 flex flex-col gap-4">
          {data.page_count > 0 && (
            <li className="flex flex-col gap-1.5 sm:flex-row sm:items-start sm:gap-4">
              <LinkButton
                to={`/scans/${data.id}/issues`}
                variant="primary"
                aria-describedby="review-partial-hint"
                className="shrink-0 sm:w-56"
              >
                Review what the scan found
              </LinkButton>
              {/* Without this the page said evidence "remains available" and
                  then offered no way to reach it, so the only route onward
                  was to run the scan again. */}
              <p id="review-partial-hint" className="text-sm text-fg-muted sm:pt-2">
                Opens the issues found on the {data.page_count.toLocaleString()} page
                {data.page_count === 1 ? "" : "s"} this scan reached.
              </p>
            </li>
          )}
          <li className="flex flex-col gap-1.5 sm:flex-row sm:items-start sm:gap-4">
            <LinkButton
              to={
                previousSettings.data
                  ? `/scans/new?${loginScan ? "mode=login&" : ""}from=${data.id}`
                  : `/scans/new?url=${encodeURIComponent(data.seed_url)}`
              }
              variant={data.page_count > 0 ? "secondary" : "primary"}
              aria-describedby="retry-edit-hint"
              className="shrink-0 sm:w-56"
            >
              {RETRY.edit}
            </LinkButton>
            <p id="retry-edit-hint" className="text-sm text-fg-muted sm:pt-2">
              {RETRY.editHint}
            </p>
          </li>
          {!loginScan && (
            <li className="flex flex-col gap-1.5 sm:flex-row sm:items-start sm:gap-4">
              <Button
                type="button"
                onClick={() => quickRetry.mutate()}
                disabled={quickRetry.isPending}
                aria-describedby="retry-quick-hint"
                className="shrink-0 sm:w-56"
              >
                {quickRetry.isPending ? RETRY.quickPending : RETRY.quick}
              </Button>
              <p id="retry-quick-hint" className="text-sm text-fg-muted sm:pt-2">
                {RETRY.quickHint}
              </p>
            </li>
          )}
        </ul>
      </Card>
    </>
  );
}
