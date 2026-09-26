import { useMemo, useState, type ReactNode } from "react";
import { useModalDialog } from "../hooks/useModalDialog";
import { Link, useParams, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, CircleHelp, Info, X } from "lucide-react";
import { api } from "../api/client";
import type { ComparisonChange, ComparisonCoverageState, ComparisonReport, DetectionPipeline } from "../api/types";
import { Button, Card } from "../components/ui";
import ReportHeader from "../components/ReportHeader";
import ChangeTag, { CHANGES } from "../components/compare/ChangeTag";
import ComparedIssuesTable, {
  parseChanges,
  parseSort,
  serializeSort,
  sortRows,
  unsureChange,
} from "../components/compare/ComparedIssuesTable";
import TrendChart from "../components/compare/TrendChart";
import { count, plural } from "../components/compare/format";
import { useScanQuery } from "../hooks/useScanQuery";
import { cn } from "../lib/cn";
import { CHECK_LABEL } from "../lib/terms";

// Each check by its shared interface name (terms.ts), keyed as the API names it.
const PIPELINE_KEYS: DetectionPipeline[] = ["axe", "alfa", "keyboard", "responsive", "focus", "visual", "semantic", "image"];
const PIPELINES: Record<string, string> = Object.fromEntries(PIPELINE_KEYS.map((key) => [key, CHECK_LABEL[key]]));

const isChange = (value: string | null): value is ComparisonChange =>
  (CHANGES as string[]).includes(value ?? "");

/**
 * Compare scans: what changed between this report and an earlier scan of the
 * same site, and how the site has trended across every completed scan.
 *
 * The page reads top down: which two scans, how many issue groups are new,
 * resolved or remaining (each a filter for the table), the coverage notes,
 * the trend, then every compared group in a table.
 *
 * "Resolved" means only that a later scan did not detect the group again.
 * The terms dialog says so, a row whose checks differed between the scans
 * says so, and the coverage notes list every reason a comparison may not be
 * like for like.
 */
export default function CompareRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
  const compareToParam = params.get("compare_to");
  const compareTo = compareToParam === null ? undefined : Number(compareToParam);
  // The checked changes, comma-separated ("new,resolved"); "" is every row.
  // A stat card sets exactly one.
  const change = parseChanges(params.get("change"));
  const q = params.get("q") ?? "";
  const rawSort = params.get("sort");
  // The same object until ?sort= changes, so the rows below re-sort only then.
  const sort = useMemo(() => parseSort(rawSort), [rawSort]);
  const [termsOpen, setTermsOpen] = useState(false);

  const scanQuery = useScanQuery(id);
  const comparisonQuery = useQuery({
    queryKey: ["comparison", id, compareTo ?? null, "all"],
    queryFn: () => api.getFullComparison(id, compareTo),
    enabled: Number.isFinite(id),
  });
  const historyQuery = useQuery({
    queryKey: ["site-history", id],
    queryFn: () => api.getSiteHistory(id),
    enabled: Number.isFinite(id),
  });

  // Against the live query string, as the Issues table does: the search
  // publishes on a debounce and must not be overwritten by a later click.
  const setParam = (key: string, value: string) => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (value) next.set(key, value);
        else next.delete(key);
        if (key !== "page") next.delete("page");
        return next;
      },
      { replace: true },
    );
  };
  // The change and the search in one write: two `setParam` calls in one
  // event each start from this render's query string, so the second would
  // put back what the first removed.
  const clearFilters = () => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        for (const key of ["change", "q", "page"]) next.delete(key);
        return next;
      },
      { replace: true },
    );
  };

  const data = comparisonQuery.data;
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const changes = new Set(change ? change.split(",") : []);
    const filtered = (data?.rows ?? []).filter(
      (row) =>
        (changes.size === 0 || changes.has(row.change)) &&
        (!needle || row.title.toLowerCase().includes(needle) || (row.wcag_sc ?? "").includes(needle)),
    );
    return sortRows(filtered, sort);
  }, [data, change, q, sort]);

  const backTo = `/scans/${id}/compare${params.toString() ? `?${params.toString()}` : ""}`;
  const history = historyQuery.data;
  const error = scanQuery.error ?? comparisonQuery.error;

  return (
    <>
      <ReportHeader
        tabs
        scanId={id}
        previousScanId={scanQuery.data?.previous_scan_id ?? null}
        title="Compare scans"
        meta="What changed since an earlier scan of this site: new issues, issues still found, and issues no longer found. The trend shows how the site changed over time."
        actions={
          <Button type="button" onClick={() => setTermsOpen(true)} className="rounded-full">
            <CircleHelp className="h-4 w-4" aria-hidden />
            What do these terms mean?
          </Button>
        }
      />
      <TermsDialog
        open={termsOpen}
        onClose={() => setTermsOpen(false)}
        baselineId={data?.baseline?.id ?? null}
        currentId={id}
      />

      {error && (
        <Card className="mb-4 p-4 text-sm text-sev-critical" role="alert">
          {error instanceof Error ? error.message : "The comparison could not load. Try again later."}{" "}
          <Link className="report-link" to={`/scans/${id}/issues`}>Return to issues</Link>
        </Card>
      )}
      {!data && !error && <p role="status" className="text-sm text-fg-muted">Loading comparison…</p>}

      {data && !error && (
        <>
          {/* Trend first, the long view; then what changed since the
              chosen scan, the table of it, and last the coverage notes. */}
          <Card className="mb-5 p-4" role="region" aria-labelledby="trend-heading">
            {historyQuery.error ? (
              <>
                <h2 id="trend-heading" className="text-base font-semibold">Trend over time</h2>
                <p className="mt-1 text-sm text-sev-critical" role="alert">The trend could not load. Try again later. The comparison below still works.</p>
              </>
            ) : !history ? (
              <>
                <h2 id="trend-heading" className="text-base font-semibold">Trend over time</h2>
                <p className="mt-1 text-sm text-fg-muted" role="status">Loading trend…</p>
              </>
            ) : history.scans.length < 2 ? (
              <>
                <h2 id="trend-heading" className="text-base font-semibold">Trend over time</h2>
                <p className="mt-1 text-sm text-fg-muted">This site has one completed scan so far. The trend appears after you scan the site again.</p>
              </>
            ) : (
              <TrendChart
                points={history.scans}
                total={history.total}
                currentId={id}
                baselineId={data.baseline?.id ?? null}
              />
            )}
          </Card>

          {data.baseline ? (
            <Comparison
              data={data}
              total={history?.total ?? null}
              previousId={scanQuery.data?.previous_scan_id ?? null}
              change={change}
              onChange={(next) => setParam("change", next)}
            />
          ) : (
            <Card className="mb-5 p-4 text-sm leading-relaxed">
              <h2 className="font-semibold">Nothing earlier to compare with</h2>
              <p className="mt-1 text-fg-muted">
                This is the first completed scan of this site. Scan the site again after you fix issues, then compare the two here.
                {history && history.scans.length > 1 && " To compare a later scan with this one, choose it in the trend above."}
              </p>
            </Card>
          )}

          {data.baseline && (
            // Not a region of its own: the table's scroll region inside is
            // already the "Compared issues" landmark. Nothing clips
            // it either: the Filter menu's panel hangs below the table's bar.
            <Card>
              <h2 className="sr-only">Compared issues</h2>
              <ComparedIssuesTable
                rows={rows}
                counts={{ ...data.changes, all: data.rows.length }}
                change={change}
                onChange={(next) => setParam("change", next)}
                q={q}
                onQuery={(next) => setParam("q", next)}
                onClearFilters={clearFilters}
                sort={sort}
                onSort={(next) => setParam("sort", serializeSort(next))}
                baselineId={data.baseline.id}
                currentId={id}
                backTo={backTo}
                // Said once above the cards when it is true of every new or
                // resolved group; marked per row only when it is not.
                rowCaveats={
                  data.rows.filter(unsureChange).length < data.changes.new + data.changes.resolved
                }
              />
            </Card>
          )}
          {data.baseline && data.rows.length < data.total && (
            <p className="mt-2 text-xs text-fg-muted">
              Showing the first {data.rows.length} of {data.total} issues.
            </p>
          )}
          {/* Last: the caveats behind the numbers above, read once the
              reader has seen what changed. */}
          {data.baseline && (
            <div className="mt-5">
              <CoverageNotes data={data} />
            </div>
          )}
        </>
      )}
    </>
  );
}

function Comparison({
  data,
  total,
  previousId,
  change,
  onChange,
}: {
  data: ComparisonReport;
  total: number | null;
  previousId: number | null;
  /** The table's checked changes, comma-separated; a card is on only when it is the one. */
  change: string;
  onChange: (next: ComparisonChange | "") => void;
}) {
  const baseline = data.baseline!;
  const settings = data.settings_changed;
  const unsure = data.rows.filter(unsureChange).length;
  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
        <p className="font-semibold">
          Comparing this report with{" "}
          <Link className="report-link" to={`/scans/${baseline.id}/issues`}>report #{baseline.id}</Link>
        </p>
        {total !== null && (
          <span className="rounded-full border border-border bg-surface-muted px-3 py-1 text-xs font-semibold">
            {count(total, "completed scan")} of this site so far
          </span>
        )}
        <p className="text-fg-muted">
          {settings.length === 0
            ? "Same site, same settings."
            : `Same site, but ${count(settings.length, "scan setting")} ${settings.length === 1 ? "differs" : "differ"}.`}{" "}
          Choose a number to filter the table.
        </p>
        {previousId !== null && previousId !== baseline.id && (
          <Link className="report-link" to={`/scans/${data.current.id}/compare?compare_to=${previousId}`}>
            Compare with the previous report (Report #{previousId}) instead
          </Link>
        )}
      </div>
      {unsure > 0 && (
        <p className="mb-3 flex max-w-4xl items-start gap-2 rounded-xs border border-sev-major/30 bg-sev-major-bg px-3 py-2 text-sm text-sev-major">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>
            The checks or pages were different in these two scans. So{" "}
            {unsure === data.changes.new + data.changes.resolved
              ? "the new issues and the issues no longer found"
              : `${unsure} of the new issues and issues no longer found (marked in the table)`}{" "}
            may come from what was scanned, not from changes to the site. Check them on the page. &ldquo;What was checked in each report&rdquo;, at the end of this page, says what was different.
          </span>
        </p>
      )}

      <div role="group" aria-label="Filter the table by change" className="mb-4 grid gap-3 sm:grid-cols-3">
        {CHANGES.map((key) => {
          const active = change === key;
          return (
            <button
              key={key}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(active ? "" : key)}
              className={cn(
                "rounded-xs border bg-surface p-4 text-left shadow-card transition-colors hover:border-umich-blue focus-visible:outline-none focus-visible:shadow-focus",
                active ? "border-umich-blue ring-2 ring-inset ring-umich-blue" : "border-border",
              )}
            >
              <ChangeTag change={key} />
              <span className="mt-2 block text-3xl font-semibold leading-none tabular-nums text-fg">
                {data.changes[key].toLocaleString()}
              </span>
              <span className="sr-only"> {plural(data.changes[key], "issue")}</span>
            </button>
          );
        })}
      </div>
    </>
  );
}

type CoveragePair = ComparisonReport["coverage"][number];

/**
 * What a check ran on, in words, the same in the table and the differences.
 * The state words are the report's "What this scan checked" words: Ran,
 * Partly ran, Not recorded, Not selected.
 */
function coverageText(coverage: ComparisonCoverageState): string {
  if (coverage.state === "disabled") return "Not selected";
  if (coverage.checked === null) return "Not recorded";
  if (coverage.state === "unknown") return `Tried on ${coverage.checked} of ${coverage.total} pages`;
  if (coverage.state === "complete") return `Ran on all ${coverage.total} pages`;
  return `Partly ran on ${coverage.checked} of ${coverage.total} pages`;
}

// Page totals differ whenever the page sets do, which a note already says.
const methodDiffers = ({ before, after }: CoveragePair) =>
  before.state !== after.state || before.checked !== after.checked;

const LEGEND: Array<[string, string]> = [
  ["Tried on", "the check started on these pages. The scan did not record errors or limits within a page."],
  ["Not recorded", "the scan did not count the pages this check ran on."],
  ["Not selected", "the check was not chosen in that scan’s settings."],
];

/**
 * Why a comparison may not be like for like, in the order a reader needs:
 * what differs between the scans (it can make a group look new or
 * resolved), what each check covered, then the limits both scans share.
 *
 * A heading-and-button disclosure, like `Disclosure`, so a screen reader
 * user can reach it from the headings list. The button carries the verdict
 * and the reason to open it, which stay visible while it is closed.
 */
function CoverageNotes({ data }: { data: ComparisonReport }) {
  const [open, setOpen] = useState(false);
  const before = data.baseline!.id;
  const after = data.current.id;
  const methods = data.coverage.filter(methodDiffers);
  const differences: Array<{ key: string; body: ReactNode }> = [
    ...(data.settings_changed.length > 0
      ? [{
          key: "settings",
          body: (
            <>
              <strong>{count(data.settings_changed.length, "setting")}:</strong>{" "}
              {data.settings_changed.map(settingName).join(", ")}.
            </>
          ),
        }]
      : []),
    ...methods.map((pair) => ({
      key: pair.pipeline,
      body: (
        <>
          <strong>{PIPELINES[pair.pipeline] ?? pair.pipeline}:</strong>{" "}
          {coverageText(pair.before).toLowerCase()} in report #{before},{" "}
          {coverageText(pair.after).toLowerCase()} in report #{after}.
        </>
      ),
    })),
    ...data.notes.filter((note) => note.differs).map((note) => ({
      key: note.text,
      body:
        note.scans.length === 1 ? (
          <>
            <strong>Report #{note.scans[0]} only:</strong> {note.text}
          </>
        ) : (
          note.text
        ),
    })),
  ];
  const shared = data.notes.filter((note) => !note.differs);
  const cells = data.coverage.flatMap((pair) => [coverageText(pair.before), coverageText(pair.after)]);
  const legend = LEGEND.filter(([term]) => cells.some((cell) => cell.startsWith(term)));
  // Each setting counts, as the line above the cards counts them, though
  // they share one bullet.
  const total = differences.length + Math.max(0, data.settings_changed.length - 1);
  const verdict = total === 0 ? "No differences between the scans" : `${count(total, "difference")} between the scans`;

  return (
    <Card className="mb-5 overflow-hidden">
      <h2 className="m-0">
        <button
          type="button"
          id="coverage-notes-button"
          aria-expanded={open}
          aria-controls="coverage-notes-panel"
          onClick={() => setOpen((value) => !value)}
          className={cn(
            "flex min-h-target w-full flex-wrap items-center gap-x-2 gap-y-1 px-4 py-3 text-left text-sm text-fg focus-visible:outline-none focus-visible:shadow-focus",
            open ? "bg-surface-muted" : "hover:bg-surface-muted/60",
          )}
        >
          <ChevronRight
            className={cn(
              "h-4 w-4 shrink-0 text-fg-subtle transition-transform duration-200 motion-reduce:transition-none",
              open && "rotate-90",
            )}
            aria-hidden
          />
          <span className="font-semibold">What was checked in each report</span>
          <span className="sr-only">:</span>{" "}
          {/* The verdict is in words, so its tint is never the only signal. */}
          <span
            className={cn(
              "rounded-full border px-2 py-0.5 text-xs font-semibold",
              differences.length > 0
                ? "border-sev-major/30 bg-sev-major-bg text-sev-major"
                : "border-border bg-surface-muted text-fg",
            )}
          >
            {verdict}
          </span>
          <span className="sr-only">.</span>{" "}
          <span className="text-fg-muted">Read these notes before you treat a missing issue as fixed.</span>
        </button>
      </h2>
      <div
        id="coverage-notes-panel"
        role="region"
        aria-label="What was checked in each report"
        hidden={!open}
        className="border-t border-border px-4 pb-5 pt-4 text-sm leading-relaxed"
      >
        <p className="flex max-w-3xl items-start gap-2">
          <Info className="mt-1 h-4 w-4 shrink-0 text-fg-subtle" aria-hidden />
          <span>
            No longer found means the later scan did not find the issue again. That is not proof of a fix. Check the page
            yourself before you mark the issue Fixed.
          </span>
        </p>

        <h3 className="mt-5 font-semibold">What differs between the scans</h3>
        {differences.length === 0 ? (
          <p className="mt-1 max-w-3xl">
            Nothing. Both scans used the same settings, pages, and checks. So a change in the table most likely comes from
            the site, not from what was scanned.
          </p>
        ) : (
          <>
            <p className="mt-1 max-w-3xl text-fg-muted">
              These can make an issue look new or no longer found when the site did not change.
            </p>
            <ul className="mt-2 max-w-3xl list-disc space-y-1.5 pl-5">
              {differences.map((item) => <li key={item.key}>{item.body}</li>)}
            </ul>
          </>
        )}

        {data.coverage.length > 0 && (
          <>
            <h3 id="coverage-table-heading" className="mt-6 font-semibold">What each check covered</h3>
            {/* Ruled on every side: the eye follows a check across to both scans
                without losing the row, as in the report's other tables. */}
            <table
              aria-labelledby="coverage-table-heading"
              className="mt-2 w-full max-w-3xl border-collapse border border-border-strong text-sm"
            >
              <thead className="bg-surface-muted text-fg-muted">
                <tr>
                  <th scope="col" className="border border-border-strong px-4 py-3 text-center font-semibold">Check</th>
                  <th scope="col" className="border border-border-strong px-4 py-3 text-center font-semibold">
                    Report #{before} <span className="font-normal text-fg-muted">(before)</span>
                  </th>
                  <th scope="col" className="border border-border-strong px-4 py-3 text-center font-semibold">
                    Report #{after} <span className="font-normal text-fg-muted">(after)</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.coverage.map((pair) => {
                  const differs = methodDiffers(pair);
                  return (
                    <tr key={pair.pipeline} className={cn(differs && "bg-sev-major-bg")}>
                      <th scope="row" className="border border-border px-4 py-3 text-left align-top font-semibold">
                        {PIPELINES[pair.pipeline] ?? pair.pipeline}
                        {differs && (
                          <>
                            <span className="sr-only">,</span>{" "}
                            <span className="whitespace-nowrap rounded-full border border-sev-major/30 px-2 text-xs text-sev-major">
                              Differs
                            </span>
                          </>
                        )}
                      </th>
                      <td className="border border-border px-4 py-3 text-center align-top tabular-nums">{coverageText(pair.before)}</td>
                      <td className="border border-border px-4 py-3 text-center align-top tabular-nums">{coverageText(pair.after)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {legend.length > 0 && (
              <dl className="mt-3 max-w-3xl space-y-1 text-fg-muted">
                {legend.map(([term, meaning]) => (
                  <div key={term}>
                    <dt className="inline font-semibold text-fg">{term}</dt>
                    <dd className="inline">: {meaning}</dd>
                  </div>
                ))}
              </dl>
            )}
          </>
        )}

        {shared.length > 0 && (
          <>
            <h3 className="mt-6 font-semibold">Limits in both scans</h3>
            <p className="mt-1 max-w-3xl text-fg-muted">
              These apply to both scans equally, so they do not explain a change between them. They can still hide issues
              that neither scan found.
            </p>
            <ul className="mt-2 max-w-3xl list-disc space-y-1.5 pl-5">
              {shared.map((note) => <li key={note.text}>{note.text}</li>)}
            </ul>
          </>
        )}
      </div>
    </Card>
  );
}

/**
 * A changed setting by the name the New scan form gives it. The server sends
 * the stored key ("keyboard_probe_enabled"); a reader should never see that.
 */
const SETTING_NAMES: Record<string, string> = {
  alfa_enabled: CHECK_LABEL.alfa,
  axe_enabled: CHECK_LABEL.axe,
  keyboard_probe_enabled: CHECK_LABEL.keyboard,
  responsive_checks_enabled: CHECK_LABEL.responsive,
  focus_checks_enabled: CHECK_LABEL.focus,
  visual_checks_enabled: CHECK_LABEL.visual,
  semantic_enabled: CHECK_LABEL.semantic,
  ocr_enabled: CHECK_LABEL.image,
  vlm_enabled: "Image text check (vision model)",
  image_extraction_enabled: "Images on pages",
  interaction_checks_enabled: "Click-Through",
  axe_level: "WCAG level",
  wcag_version: "WCAG version",
  max_pages: "Maximum pages",
  max_depth: "Maximum link depth",
  whole_host: "Whole website",
  allow_subdomains: "Subdomains",
  ignore_robots: "robots.txt",
  browser_only: "Use a browser for every page",
  js_eager: "Use a browser for every page",
  store_rendered_html: "Save page copies",
  search: "Search",
  rps: "Pages per second",
  browser_headless: "Show the browser",
  resumable: "Resume after a stop",
};

function settingName(key: string): string {
  return SETTING_NAMES[key] ?? key.replaceAll("_", " ");
}

/** The page's vocabulary. A native modal dialog, like the shortcuts list. */
function TermsDialog({
  open,
  onClose,
  baselineId,
  currentId,
}: {
  open: boolean;
  onClose: () => void;
  baselineId: number | null;
  currentId: number;
}) {
  const ref = useModalDialog(open);
  const earlier = baselineId !== null ? `report #${baselineId}` : "the earlier report";
  const later = `report #${currentId}`;
  const terms: Array<[ComparisonChange | "group" | "occurrence", string, string]> = [
    ["new", "New", `Found in ${later} but not in ${earlier}. Check whether it is a new barrier.`],
    [
      "resolved",
      "No longer found",
      `Found in ${earlier}, but not found again in ${later}. That is not proof of a fix. Check the page yourself before you mark the issue Fixed, especially if the checks were different in the two scans.`,
    ],
    ["remaining", "Still found", "Found in both scans. Its number of occurrences can still go up or down."],
    ["group", "Issue", "One accessibility rule, or one kind of image problem, with every place it was found."],
    ["occurrence", "Occurrence", "One place an issue was found, counted as the Issues table counts it: an element repeated across pages counts once."],
  ];
  return (
    <dialog
      ref={ref}
      aria-labelledby="compare-terms-title"
      onClose={onClose}
      className="w-[min(92vw,34rem)] rounded-xs border border-border bg-surface p-0 text-fg shadow-raised backdrop:bg-black/40"
    >
      <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-3">
        <h2 id="compare-terms-title" className="text-base font-semibold">What these terms mean</h2>
        <Button type="button" variant="ghost" onClick={onClose} aria-label="Close terms">
          <X className="h-5 w-5" aria-hidden />
        </Button>
      </div>
      <dl className="divide-y divide-border px-5 py-2 text-sm">
        {terms.map(([key, term, meaning]) => (
          <div key={key} className="py-3">
            <dt>{isChange(key) ? <ChangeTag change={key} /> : <span className="font-semibold">{term}</span>}</dt>
            <dd className="mt-1 leading-relaxed text-fg-muted">{meaning}</dd>
          </div>
        ))}
      </dl>
      <p className="border-t border-border px-5 py-3 text-xs text-fg-muted">
        This page shows changes in what the scans found. It does not show whether the site meets the Web Content
        Accessibility Guidelines (WCAG). Statuses record your team’s decisions, separately from the scans.
      </p>
    </dialog>
  );
}
