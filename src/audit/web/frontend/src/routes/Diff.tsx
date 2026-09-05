import { Link, useParams, useSearchParams } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Button, Card } from "../components/ui";
import ReportHeader, { ReportMeta } from "../components/ReportHeader";
import type { ComparisonCategory, ComparisonCoverageState, ComparisonLink, ComparisonRow, ComparisonSnapshot } from "../api/types";

const CATEGORIES: Record<ComparisonCategory, string> = {
  new: "New",
  still_detected: "Still detected",
  changed: "Changed",
  no_longer_detected: "No longer detected",
  cannot_compare: "Cannot compare reliably",
};
const CATEGORY_HELP: Record<ComparisonCategory, string> = {
  new: "Found only in the later report. Check whether it is a new barrier.",
  still_detected: "The same findings were recorded in both reports. Check the issue’s review status for next steps.",
  changed: "Locations, counts, results, or review statuses differ. This does not always mean improvement.",
  no_longer_detected: "Not found again with comparable checks. Confirm the fix on the page before marking it remediated.",
  cannot_compare: "Missing evidence or different coverage prevents a reliable conclusion. Recheck the affected pages.",
};
const PIPELINES: Record<string, string> = {
  axe: "axe-core", alfa: "Siteimprove Alfa", keyboard: "Keyboard", responsive: "Responsive",
  focus: "Focus", visual: "Visual", semantic: "Semantic", image: "Images",
};

export default function DiffRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
  const compareToParam = params.get("compare_to");
  const compareTo = compareToParam === null ? undefined : Number(compareToParam);
  const category = (params.get("category") ?? "") as ComparisonCategory | "";
  const pipeline = params.get("pipeline") ?? "";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const scanQuery = useQuery({ queryKey: ["scan", id], queryFn: () => api.getScan(id), enabled: Number.isFinite(id) });
  const query = useQuery({
    queryKey: ["comparison", id, compareTo, category, pipeline, page],
    queryFn: () => api.getComparison(id, { compare_to: compareTo, category, pipeline, page }),
    enabled: Number.isFinite(id),
    // Keep the controls mounted during filtering, but never retain another
    // report pair's results while changing scope.
    placeholderData: (previous, previousQuery) => previousQuery?.queryKey[1] === id
      && previousQuery.queryKey[2] === compareTo ? keepPreviousData(previous) : undefined,
  });
  const data = query.data;
  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  };
  const error = scanQuery.error ?? query.error;
  return (
    <>
      <ReportHeader
        scanId={id}
        previousScanId={data?.baseline?.id ?? scanQuery.data?.previous_scan_id ?? null}
        title="Verify changes"
        meta={<ReportMeta counts={data?.baseline ? `Report #${id} compared with #${data.baseline.id}` : `Report #${id}`} note="" />}
      />
      <p className="mb-5 max-w-3xl text-sm leading-relaxed text-fg-muted">
        See what was found before and after your fixes, then decide what to check next.
      </p>
      <Card className="mb-5 p-4 text-sm leading-relaxed">
        <h2 className="font-semibold">How to read this comparison</h2>
        <ol className="mt-2 grid list-decimal gap-x-8 gap-y-2 pl-5 md:grid-cols-3">
          <li><strong>Check the reports.</strong> Before is the earlier scan; After is the later scan. Use the same site and checks after publishing fixes.</li>
          <li><strong>Read the change label.</strong> Counts below are issue groups, not individual findings. One group can affect many elements and pages.</li>
          <li><strong>Verify on the page.</strong> Open an issue for evidence. “No longer detected” needs manual confirmation before you mark it remediated.</li>
        </ol>
        <p className="mt-3 text-fg-muted">These are changes in recorded evidence, not a compliance verdict. Review statuses track your team’s decisions separately.</p>
      </Card>
      {error && <Card className="mb-4 p-4 text-sm text-sev-critical" role="alert">{error instanceof Error ? error.message : "The comparison could not be loaded."} <Link className="report-link" to={`/scans/${id}/issues`}>Return to issues</Link></Card>}
      {!data && !error && <p role="status" className="text-sm text-fg-muted">Loading comparison…</p>}
      {data && !error && <>
        {data.baseline && <section aria-label="Reports being compared" className="mb-5 grid gap-3 md:grid-cols-2">
          {[{ label: "Before · Earlier scan", report: data.baseline }, { label: "After · Later scan", report: data.current }].map(({ label, report }) => <Card key={label} className="min-w-0 p-4">
            <h2 className="text-sm font-semibold text-fg-muted">{label}</h2>
            <Link className="report-link inline-flex min-h-target items-center text-lg font-semibold" to={`/scans/${report.id}`}>Report #{report.id}</Link>
            <p className="break-words text-sm">{report.seed_url}</p>
            <p className="mt-1 text-sm text-fg-muted">{report.started_at ? `Scanned ${report.started_at}` : "Scan time not recorded"}</p>
          </Card>)}
        </section>}
        {(data.limitations.length > 0 || data.coverage?.length > 0) && <Card className="mb-5 px-4 py-2 text-sm">
          <p className="py-2 text-fg-muted">{data.limitations.length > 0 ? "Some checks have gaps or differences. Read these before treating a missing finding as a fix." : "Check which methods ran in each report before interpreting the results."}</p>
          <details open={!data.baseline}>
            <summary className="min-h-target cursor-pointer focus-visible:outline-none focus-visible:shadow-focus content-center py-2 font-semibold">Comparison coverage{data.limitations.length > 0 ? ` · ${data.limitations.length} notes` : ""}</summary>
            {data.coverage?.length > 0 && <table className="my-2 w-full text-xs">
              <caption className="sr-only">Detection method coverage in the compared reports</caption>
              <thead><tr><th scope="col" className="p-2 text-left">Method</th><th scope="col" className="p-2 text-left">Before</th><th scope="col" className="p-2 text-left">After</th></tr></thead>
              <tbody>{data.coverage.map((coverage) => <tr key={coverage.pipeline} className="border-t border-border">
                <th scope="row" className="p-2 text-left font-semibold">{PIPELINES[coverage.pipeline] ?? coverage.pipeline}</th>
                <td className="p-2">{coverageLabel(coverage.before)}</td><td className="p-2">{coverageLabel(coverage.after)}</td>
              </tr>)}</tbody>
            </table>}
            <ul className="mb-2 mt-2 list-disc space-y-1 pl-5 text-fg-muted">{data.limitations.map((warning) => <li key={warning}>{warning}</li>)}</ul>
          </details>
        </Card>}
        {data.baseline ? <>
          <section aria-labelledby="comparison-summary" className="mb-6">
            <h2 id="comparison-summary" className="text-lg font-semibold">What changed?</h2>
            <p className="mb-3 mt-1 text-sm text-fg-muted">Issue groups across both reports. Use the filters below to focus your review.</p>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              {Object.entries(CATEGORIES).map(([key, label]) => <Card key={key} className="p-4">
                <h3 className="text-sm font-semibold">{label}</h3>
                <p className="my-2 text-2xl font-semibold tabular-nums">{data.counts[key as ComparisonCategory]} <span className="text-xs font-normal text-fg-muted">{data.counts[key as ComparisonCategory] === 1 ? "group" : "groups"}</span></p>
                <p className="text-sm leading-relaxed text-fg-muted">{CATEGORY_HELP[key as ComparisonCategory]}</p>
              </Card>)}
            </div>
          </section>
          <h2 className="mb-3 text-lg font-semibold">Review the issues</h2>
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <label className="min-w-0 text-sm font-semibold">Change category
              <select value={category} onChange={(event) => setParam("category", event.target.value)} className="field mt-1 text-base focus-visible:outline-none focus-visible:shadow-focus">
                <option value="">All categories</option>
                {Object.entries(CATEGORIES).map(([key, label]) => <option key={key} value={key}>{label} ({data.counts[key as ComparisonCategory]})</option>)}
              </select>
            </label>
            <label className="min-w-0 text-sm font-semibold">Detection method
              <select value={pipeline} onChange={(event) => setParam("pipeline", event.target.value)} className="field mt-1 text-base focus-visible:outline-none focus-visible:shadow-focus">
                <option value="">All methods</option>
                {Object.entries(PIPELINES).map(([key, label]) => <option key={key} value={key}>{label} ({data.pipeline_counts[key] ?? 0})</option>)}
              </select>
            </label>
          </div>
          <p role="status" className="mb-3 text-sm text-fg-muted">{query.isFetching ? "Updating comparison…" : `${data.total} issue groups · Page ${data.page} of ${Math.max(1, Math.ceil(data.total / data.page_size))}`}</p>
          <section aria-label="Compared issue groups" aria-busy={query.isFetching} className="space-y-4">
            {data.rows.length === 0 && <Card className="p-4 text-sm text-fg-muted">No issue groups match these filters.</Card>}
            {data.rows.map((row) => <Card key={row.key} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h2 className="min-w-0 break-words text-base font-semibold">{row.title}</h2>
                <span className="rounded-xs border border-border bg-surface-muted px-2 py-1 text-xs font-semibold">{CATEGORIES[row.category]}</span>
              </div>
              <p className="mt-1 text-sm text-fg-muted">{PIPELINES[row.pipeline] ?? row.pipeline}</p>
              <p className="mt-3 text-sm leading-relaxed">{changeSummary(row)}</p>
              {row.limitations.length > 0 && <details className="mt-2 text-sm text-fg-muted">
                <summary className="min-h-target cursor-pointer focus-visible:outline-none focus-visible:shadow-focus content-center py-2 font-semibold">Why this comparison needs care ({row.limitations.length})</summary>
                <ul className="list-disc pl-5">{row.limitations.map((warning) => <li key={warning}>{warning}</li>)}</ul>
              </details>}
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <Snapshot label={`Before · Report #${data.baseline!.id}`} snapshot={row.before} />
                <Snapshot label={`After · Report #${data.current.id}`} snapshot={row.after} />
              </div>
            </Card>)}
          </section>
          <nav aria-label="Comparison pages" className="mt-5 flex flex-wrap items-center gap-3">
            <Button disabled={page <= 1 || query.isFetching} onClick={() => setParam("page", String(page - 1))}>Previous page</Button>
            <Button disabled={page * data.page_size >= data.total || query.isFetching} onClick={() => setParam("page", String(page + 1))}>Next page</Button>
          </nav>
        </> : <Link className="report-link inline-flex min-h-target items-center" to={`/scans/${id}/issues`}>Review this report’s issues</Link>}
      </>}
    </>
  );
}

function Snapshot({ label, snapshot }: { label: string; snapshot: ComparisonSnapshot | null }) {
  return <section className="min-w-0 rounded-xs border border-border bg-surface-subtle p-3">
    <h3 className="text-sm font-semibold">{label}</h3>
    {snapshot ? <>
      <p className="mt-1 text-sm">{snapshot.occurrences} {snapshot.occurrences === 1 ? "finding" : "findings"} on {snapshot.pages} {snapshot.pages === 1 ? "page" : "pages"}</p>
      <p className="mt-1 text-xs text-fg-muted"><strong>Review status:</strong> {countsLabel(snapshot.statuses)}</p>
      {Object.keys(snapshot.outcomes).length > 0 && <p className="mt-1 text-xs text-fg-muted"><strong>Check results:</strong> {countsLabel(snapshot.outcomes)}</p>}
      <Links links={snapshot.issues} label="Open issue details" />
      {snapshot.evidence.length > 0 && <details className="mt-2">
        <summary className="min-h-target cursor-pointer content-center py-2 text-sm font-semibold focus-visible:outline-none focus-visible:shadow-focus">Example evidence ({snapshot.evidence.length})</summary>
        <Links links={snapshot.evidence} label="Finding links" />
      </details>}
    </> : <p className="mt-1 text-sm text-fg-muted">No findings recorded for this group in this report. This alone does not prove it was fixed.</p>}
  </section>;
}
function countsLabel(counts: Record<string, number>) {
  return Object.entries(counts).map(([key, count]) => `${key === "cant_tell" ? "Cannot tell (manual review)" : key.replaceAll("_", " ")}: ${count}`).join(" · ") || "No recorded status";
}
function Links({ links, label }: { links: ComparisonLink[]; label: string }) {
  if (links.length === 0) return null;
  return <div className="mt-2"><p className="text-xs font-semibold">{label}</p><ul className="text-sm">{links.map((link) => <li key={link.url}><Link className="report-link inline-flex min-h-target max-w-full items-center break-all py-1" to={link.url.replace(/^\/app(?=\/)/, "")}>{link.label}</Link></li>)}</ul></div>;
}

function coverageLabel(coverage: ComparisonCoverageState) {
  return `${coverage.state}${coverage.checked === null ? " · pages checked not recorded" : ` · ${coverage.checked}/${coverage.total} pages`}`;
}

function changeSummary(row: ComparisonRow): string {
  const before = row.before;
  const after = row.after;
  if (row.category === "cannot_compare") return CATEGORY_HELP.cannot_compare;
  if (row.category === "no_longer_detected") return CATEGORY_HELP.no_longer_detected;
  if (row.category === "new") return CATEGORY_HELP.new;
  if (row.category === "still_detected") return CATEGORY_HELP.still_detected;
  if (before && after) {
    const counts = before.occurrences !== after.occurrences || before.pages !== after.pages
      ? `Recorded findings: ${before.occurrences} → ${after.occurrences}. Affected pages: ${before.pages} → ${after.pages}.`
      : "The finding and page counts are unchanged, but locations, check results, or review statuses differ.";
    const statusesDiffer = !sameCounts(before.statuses, after.statuses);
    const outcomesDiffer = !sameCounts(before.outcomes, after.outcomes);
    const details = [
      statusesDiffer ? `Review status changed: ${countsLabel(before.statuses)} → ${countsLabel(after.statuses)}.` : "",
      outcomesDiffer ? `Check results changed: ${countsLabel(before.outcomes)} → ${countsLabel(after.outcomes)}.` : "",
    ].filter(Boolean).join(" ");
    return `${counts}${details ? ` ${details}` : ""} Compare the evidence below to understand the change.`;
  }
  return CATEGORY_HELP.changed;
}

function sameCounts(before: Record<string, number>, after: Record<string, number>): boolean {
  return Object.keys(before).length === Object.keys(after).length
    && Object.entries(before).every(([key, value]) => after[key] === value);
}
