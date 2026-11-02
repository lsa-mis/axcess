import { Link } from "react-router";
import { checkedPercent } from "../lib/scanProgress";
import type { ScanSummary, SiteGroup } from "../api/types";
import { siteLabel } from "./ReportCrumb";
import { Card } from "./ui";
import { useScanQuery } from "../hooks/useScanQuery";

/**
 * The Reports page's notice of a scan that is running now, with how far it
 * has got, above the table. Nothing when no scan is running.
 *
 * Until 2026-10-30 this was the "Last scanned" card, with the newest
 * completed site in large type and "Open latest scan", and this banner above
 * it. The developer removed the card: the table's first row is that site,
 * with the same link (routes/Scans.tsx). The running scan stays, since the
 * table shows a running scan only once its site is opened.
 */
export default function RunningScanNotice({ sites }: { sites: SiteGroup[] }) {
  const running = sites.flatMap((site) => site.scans).find((scan) => scan.status === "running");
  if (!running) return null;
  return (
    <div className="mb-6">
      <RunningScanBanner scan={running} />
    </div>
  );
}

/**
 * The scan running now, with how far it has got: a percent first, then the page counts it comes from. It refreshes while the
 * scan runs. The bar is decoration: the sentence above says the same in words.
 */
function RunningScanBanner({ scan }: { scan: ScanSummary }) {
  const { data } = useScanQuery(scan.id, { refetchInterval: PROGRESS_REFRESH_MS });
  const progress = data?.progress;
  const checked = progress?.completed ?? 0;
  const found = progress?.discovered ?? 0;
  const percent = checkedPercent(progress);
  return (
    <Card className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-umich-blue/30 bg-umich-blue/5 p-4">
      <div className="min-w-0 flex-1 basis-72">
        <p className="flex items-center gap-2 text-sm text-fg">
          <span
            className="inline-block h-2 w-2 shrink-0 animate-pulse rounded-full bg-umich-maize motion-reduce:animate-none"
            aria-hidden
          />
          <span className="break-all">
            Scanning <strong>{siteLabel(scan.seed_url)}</strong>
            {found > 0 && (
              <>
                {" · "}
                <strong className="tabular-nums">{percent}%</strong> checked
                <span className="text-fg-muted">
                  {" "}
                  ({checked.toLocaleString()} of {found.toLocaleString()} pages found so far)
                </span>
              </>
            )}
          </span>
        </p>
        {found > 0 && (
          <div className="mt-2 h-1.5 w-full max-w-md overflow-hidden rounded-full bg-border" aria-hidden>
            <div className="h-full rounded-full bg-umich-blue" style={{ width: `${percent}%` }} />
          </div>
        )}
      </div>
      <Link
        to={`/scans/${scan.id}`}
        className="text-sm font-semibold text-umich-blue underline underline-offset-2"
      >
        View progress<span className="sr-only"> of the scan of {siteLabel(scan.seed_url)}</span>
      </Link>
    </Card>
  );
}

/** How often the banner refreshes its count while the scan runs. */
const PROGRESS_REFRESH_MS = 3_000;
