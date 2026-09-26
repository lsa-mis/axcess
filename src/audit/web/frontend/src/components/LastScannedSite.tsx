import { Link } from "react-router";
import { parseServerTime, serverDate } from "../lib/serverTime";
import { ArrowRight } from "lucide-react";
import type { ScanSummary, SiteGroup } from "../api/types";
import BreakableUrl from "./BreakableUrl";
import { siteLabel } from "./ReportCrumb";
import { Card, LinkButton } from "./ui";

/**
 * The Reports page's lead card: which site was scanned last, named in the
 * largest type on the card, and one way into its report.
 *
 * It is the newest *completed* report of any site. It is not "where you left
 * off": Axcess has no user identity, a shared host can have several people
 * scanning, and the server cannot know what this reader last opened.
 *
 * It deliberately carries no findings summary. The report opens with one,
 * and the table below already has each site's issue count. A second summary
 * here read as a verdict on the site, and needed the full issue list fetched
 * just to draw the landing page.
 */
export default function LastScannedSite({ sites }: { sites: SiteGroup[] }) {
  const latest = newestCompleted(sites);
  const running = sites.flatMap((site) => site.scans).find((scan) => scan.status === "running");

  if (!latest && !running) return null;
  const site = latest ? siteLabel(latest.seed_url) : "";

  return (
    <div className="mb-6 space-y-3">
      {running && (
        <Card className="flex flex-wrap items-center justify-between gap-3 border-umich-blue/30 bg-umich-blue/5 p-4">
          <p className="flex items-center gap-2 text-sm text-fg">
            <span className="inline-block h-2 w-2 shrink-0 animate-pulse rounded-full bg-umich-maize motion-reduce:animate-none" aria-hidden />
            <span className="break-all">
              A scan of <strong>{siteLabel(running.seed_url)}</strong> is running now.
            </span>
          </p>
          <Link
            to={`/scans/${running.id}`}
            className="text-sm font-semibold text-umich-blue underline underline-offset-2"
          >
            See its progress
          </Link>
        </Card>
      )}

      {latest && (
        <section aria-label="Last scanned site">
          <Card className="flex flex-wrap items-center justify-between gap-x-6 gap-y-4 p-5 sm:p-6">
            <div className="min-w-0 max-w-3xl flex-1 basis-80">
              <p className="text-sm font-medium text-fg-muted">
                Last scanned
                {latest.finished_at && (
                  <>
                    {" · "}
                    <time dateTime={latest.finished_at} title={serverDate(latest.finished_at).toLocaleString()}>
                      {timeAgo(latest.finished_at)}
                    </time>
                  </>
                )}
              </p>
              <h2
                className="mt-1 text-2xl font-semibold leading-tight tracking-tight text-fg"
                title={latest.seed_url}
              >
                <BreakableUrl text={site} />
              </h2>
            </div>
            <LinkButton to={`/scans/${latest.id}/issues`} variant="primary" size="lg" className="shrink-0">
              Open latest scan
              <span className="sr-only"> of {site}</span>
              <ArrowRight className="h-5 w-5" aria-hidden />
            </LinkButton>
          </Card>
        </section>
      )}
    </div>
  );
}

/** Report ids increase with creation, so the highest completed id is newest. */
function newestCompleted(sites: SiteGroup[]): ScanSummary | undefined {
  let newest: ScanSummary | undefined;
  for (const site of sites) {
    const scan = site.most_recent_completed;
    if (scan && (!newest || scan.id > newest.id)) newest = scan;
  }
  return newest;
}

/** "2 hours ago", "yesterday": whole words, where `relativeTime` abbreviates. */
function timeAgo(iso: string): string {
  const seconds = (parseServerTime(iso) - Date.now()) / 1000;
  if (Number.isNaN(seconds)) return "";
  const format = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 31_536_000],
    ["month", 2_592_000],
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit);
  }
  return "just now";
}
