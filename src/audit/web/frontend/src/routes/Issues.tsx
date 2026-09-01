import { useEffect, useId, useRef, useState } from "react";
import { useParams, useSearchParams, Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Download, ExternalLink } from "lucide-react";
import { api, exportUrl } from "../api/client";
import { Card, EmptyState, PageHeader } from "../components/ui";
import type { ConformanceLabel, IssueLocation, IssueRow } from "../api/types";

/**
 * The primary report: one scan-scoped table answering what, why, fix, and where.
 * Every location is bounded server-side and links back to immutable page evidence.
 */
export default function IssuesRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
  const conformance = (params.get("conformance") as ConformanceLabel | null) ?? "";
  const q = params.get("q") ?? "";
  const sort = params.get("sort") ?? "priority_desc";

  const scanQuery = useQuery({
    queryKey: ["scan", id],
    queryFn: () => api.getScan(id),
    enabled: Number.isFinite(id),
  });
  const issuesQuery = useQuery({
    queryKey: ["issues", id, conformance, q, sort],
    queryFn: () => api.listIssues(id, { conformance, q, sort }),
    enabled: Number.isFinite(id),
  });

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const error = scanQuery.error ?? issuesQuery.error;
  if (error) {
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        Couldn&rsquo;t load this issue table. The stored scan evidence is unchanged.
      </Card>
    );
  }
  if (!scanQuery.data || !issuesQuery.data) {
    return <p className="text-sm text-fg-muted" role="status">Loading issue table…</p>;
  }

  const scan = scanQuery.data;
  const data = issuesQuery.data;
  const hasFilter = Boolean(conformance || q);
  const hasAlfaResults = data.rows.some((row) => row.pipeline === "alfa");

  return (
    <>
      <PageHeader
        crumbs={[
          { label: "Reports", to: "/scans" },
          { label: `Report #${scan.id}`, to: `/scans/${scan.id}` },
          { label: "Issues" },
        ]}
        title="Accessibility issues"
        subtitle={<span className="break-all">{scan.seed_url} · {data.rows.length} of {data.total_unfiltered} issue groups</span>}
        actions={
          <>
            <DownloadLink href={exportUrl(scan.id, "xlsx", true)}>
              <Download className="h-4 w-4" aria-hidden />
              Download workbook
            </DownloadLink>
            <DownloadLink href={exportUrl(scan.id, "audit", true)} secondary>
              Download report
            </DownloadLink>
          </>
        }
      />

      <Card className="mb-4 p-4">
        <div className="grid gap-3 md:grid-cols-[minmax(16rem,1fr)_12rem_12rem_auto] md:items-end">
          <label className="flex flex-col text-xs font-semibold uppercase tracking-wide text-fg-subtle">
            Search issues
            <input
              type="search"
              value={q}
              placeholder="Issue name or WCAG criterion"
              onChange={(event) => setParam("q", event.target.value)}
              className="mt-1 min-h-target rounded-xs border border-border bg-surface px-3 py-2 text-base font-normal normal-case tracking-normal text-fg focus:border-umich-blue focus:outline-none"
            />
          </label>
          <FilterSelect
            label="WCAG level"
            value={conformance}
            options={[
              { value: "", label: `All (${data.total_unfiltered})` },
              { value: "A", label: `Level A (${data.conformance_counts.A ?? 0})` },
              { value: "AA", label: `Level AA (${data.conformance_counts.AA ?? 0})` },
              { value: "AAA", label: `Level AAA (${data.conformance_counts.AAA ?? 0})` },
              { value: "BP", label: `Best practice (${data.conformance_counts.BP ?? 0})` },
            ]}
            onChange={(value) => setParam("conformance", value)}
          />
          <FilterSelect
            label="Order"
            value={sort}
            options={[
              { value: "priority_desc", label: "Highest priority" },
              { value: "pages_desc", label: "Most pages" },
              { value: "occurrences_desc", label: "Most occurrences" },
              { value: "conformance", label: "WCAG level" },
            ]}
            onChange={(value) => setParam("sort", value)}
          />
          {hasFilter && (
            <button
              type="button"
              onClick={() => setParams(new URLSearchParams(), { replace: true })}
              className="min-h-target rounded-xs border border-border bg-surface px-4 py-2 text-sm font-semibold text-fg hover:bg-surface-muted"
            >
              Clear filters
            </button>
          )}
        </div>
      </Card>

      {hasAlfaResults && (
        <Card className="mb-4 border-umich-blue/30 bg-umich-blue/5 p-4 text-sm" role="note">
          <strong>What is an ACT rule?</strong> ACT means Accessibility
          Conformance Testing. Each standardized rule checks one specific
          accessibility condition and returns pass, fail, or cannot tell. A
          failed rule is evidence about that condition—not proof that the whole
          page or site fails WCAG. “Cannot tell” needs an expert decision.
        </Card>
      )}

      {data.rows.length === 0 ? (
        <EmptyState
          title={hasFilter ? "No issues match these filters" : "No issue groups were detected"}
          message={hasFilter ? "Clear a filter to see more results." : "Check scan coverage before drawing a conformance conclusion."}
        />
      ) : (
        <IssueTable rows={data.rows} />
      )}

      <p className="mt-4 text-xs text-fg-subtle">
        Automated results are evidence, not a conformance decision. AI-assisted and cannot-tell results are explicitly labeled as needing confirmation.
      </p>
    </>
  );
}

function IssueTable({ rows }: { rows: IssueRow[] }) {
  const tableId = useId();
  const scrollHelpId = useId();
  const topScrollRef = useRef<HTMLDivElement>(null);
  const tableScrollRef = useRef<HTMLDivElement>(null);
  const [scrollPosition, setScrollPosition] = useState(0);
  const [scrollMaximum, setScrollMaximum] = useState(0);

  useEffect(() => {
    const scrollbar = topScrollRef.current;
    if (!scrollbar) return;
    const updateMaximum = () => {
      setScrollMaximum(Math.max(0, scrollbar.scrollWidth - scrollbar.clientWidth));
    };
    updateMaximum();
    const resizeObserver = new ResizeObserver(updateMaximum);
    resizeObserver.observe(scrollbar);
    return () => resizeObserver.disconnect();
  }, []);

  const syncScroll = (
    source: HTMLDivElement,
    target: HTMLDivElement | null,
  ) => {
    if (target && target.scrollLeft !== source.scrollLeft) {
      target.scrollLeft = source.scrollLeft;
    }
  };

  const moveScroll = (requestedPosition: number) => {
    const position = Math.max(0, Math.min(scrollMaximum, requestedPosition));
    if (topScrollRef.current) topScrollRef.current.scrollLeft = position;
    if (tableScrollRef.current) tableScrollRef.current.scrollLeft = position;
    setScrollPosition(position);
  };

  return (
    <Card className="min-w-0 max-w-full overflow-hidden">
      <div className="border-b border-border bg-surface-subtle px-4 pb-2 pt-3">
        <p id={scrollHelpId} className="mb-2 text-xs text-fg-muted">
          More columns are available horizontally. Use the scrollbar below, or
          focus it and press the Left and Right Arrow keys.
        </p>
        <div
          ref={topScrollRef}
          className="w-full overflow-x-auto overflow-y-hidden rounded-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-umich-blue"
          role="scrollbar"
          aria-label="Scroll issue table columns"
          aria-controls={tableId}
          aria-describedby={scrollHelpId}
          aria-orientation="horizontal"
          aria-valuemin={0}
          aria-valuemax={scrollMaximum}
          aria-valuenow={Math.round(scrollPosition)}
          aria-valuetext={
            scrollMaximum > 0
              ? `${Math.round((scrollPosition / scrollMaximum) * 100)}% across the table`
              : "All columns fit"
          }
          tabIndex={0}
          onKeyDown={(event) => {
            const page = Math.max(80, event.currentTarget.clientWidth * 0.8);
            const nextPosition = {
              ArrowLeft: scrollPosition - 48,
              ArrowRight: scrollPosition + 48,
              PageUp: scrollPosition - page,
              PageDown: scrollPosition + page,
              Home: 0,
              End: scrollMaximum,
            }[event.key];
            if (nextPosition !== undefined) {
              event.preventDefault();
              moveScroll(nextPosition);
            }
          }}
          onScroll={(event) => {
            setScrollPosition(event.currentTarget.scrollLeft);
            syncScroll(event.currentTarget, tableScrollRef.current);
          }}
        >
          <div className="h-1 min-w-[1180px]" aria-hidden="true" />
        </div>
      </div>
      <div
        ref={tableScrollRef}
        className="w-full max-w-full overflow-x-auto focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-umich-blue"
        role="region"
        aria-label="Scrollable accessibility issue table"
        aria-describedby={scrollHelpId}
        onScroll={(event) => {
          setScrollPosition(event.currentTarget.scrollLeft);
          syncScroll(event.currentTarget, topScrollRef.current);
        }}
      >
        <table id={tableId} className="min-w-[1180px] w-full border-collapse text-left text-sm">
          <caption className="sr-only">
            Accessibility issue groups with explanation, expected remediation, and exact location samples
          </caption>
          <thead className="bg-surface-muted text-xs font-semibold uppercase tracking-wide text-fg-muted">
            <tr>
              <th scope="col" className="w-[23%] border-b border-border px-4 py-3">Issue</th>
              <th scope="col" className="w-[23%] border-b border-border px-4 py-3">Why it is an issue</th>
              <th scope="col" className="w-[25%] border-b border-border px-4 py-3">Expected fix</th>
              <th scope="col" className="w-[29%] border-b border-border px-4 py-3">Where exactly</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((row) => <IssueTableRow key={row.issue_key} row={row} />)}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function IssueTableRow({ row }: { row: IssueRow }) {
  const lane = row.review_lane === "likely_barrier"
    ? "Automated failure"
    : row.review_lane === "expert_review"
      ? "Needs confirmation"
      : "Informational";
  const remaining = Math.max(0, row.occurrence_count - row.locations.length);

  return (
    <tr className="align-top hover:bg-surface-muted/40">
      <th scope="row" className="px-4 py-4 font-normal">
        <Link to={row.detail_url} className="font-semibold text-umich-blue underline underline-offset-2">
          {row.title}
        </Link>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <Tag>{lane}</Tag>
          <Tag>{sourceLabel(row.pipeline)}</Tag>
          {row.wcag_sc && <Tag>WCAG {row.wcag_sc} {row.conformance}</Tag>}
        </div>
        <p className="mt-2 text-xs text-fg-muted">
          {row.occurrence_count} occurrence{row.occurrence_count === 1 ? "" : "s"} on {row.page_count} page{row.page_count === 1 ? "" : "s"}
        </p>
        <p className="mt-1 text-xs text-fg-subtle">{row.evidence_summary}</p>
      </th>
      <td className="px-4 py-4 text-fg">
        <p>{row.why_matters || row.description || row.evidence_summary}</p>
        {row.abilities_affected.length > 0 && (
          <p className="mt-2 text-xs text-fg-muted">
            <strong>Affects:</strong> {row.abilities_affected.join(", ")}
          </p>
        )}
      </td>
      <td className="px-4 py-4 text-fg">
        {row.fix_steps.length > 0 ? (
          <ol className="list-decimal space-y-1 pl-5">
            {row.fix_steps.map((step, index) => (
              <li key={index} dangerouslySetInnerHTML={{ __html: step }} />
            ))}
          </ol>
        ) : (
          <p>Confirm the stored evidence in page context, then correct the component or content that produced the result.</p>
        )}
        {row.acceptance && <p className="mt-2 text-xs text-fg-muted"><strong>Done when:</strong> {row.acceptance}</p>}
      </td>
      <td className="px-4 py-4">
        {row.locations.length > 0 ? (
          <ul className="space-y-3">
            {row.locations.map((location) => (
              <Location key={`${location.page_id}:${location.target}`} location={location} />
            ))}
          </ul>
        ) : (
          <p className="text-fg-muted">No bounded location sample is available for this historical evidence.</p>
        )}
        {remaining > 0 && (
          <Link to={row.detail_url} className="mt-3 inline-block text-xs font-semibold text-umich-blue underline underline-offset-2">
            View {remaining} more occurrence{remaining === 1 ? "" : "s"}
          </Link>
        )}
      </td>
    </tr>
  );
}

function Location({ location }: { location: IssueLocation }) {
  return (
    <li className="border-l-2 border-umich-blue/30 pl-3">
      <a
        href={location.page_url}
        target="_blank"
        rel="noopener noreferrer"
        className="break-all font-medium text-umich-blue underline underline-offset-2"
      >
        {location.page_title || location.page_url}
        <ExternalLink className="ml-1 inline h-3 w-3" aria-hidden />
        <span className="sr-only"> opens the scanned page in a new tab</span>
      </a>
      {location.page_title && <p className="mt-0.5 break-all text-xs text-fg-muted">{location.page_url}</p>}
      {/* A finding that only exists after a control is used cannot be
          reproduced from the URL alone. Naming the control is the
          difference between evidence and an assertion. */}
      {location.revealed_by && (
        <p className="mt-0.5 text-xs font-medium text-fg">
          After clicking &ldquo;{location.revealed_by}&rdquo;
        </p>
      )}
      <code className="mt-1 block max-w-[28rem] overflow-x-auto rounded-xs bg-surface-muted px-2 py-1 text-xs text-fg">
        {location.target}
      </code>
      {location.context && <p className="mt-1 line-clamp-3 text-xs text-fg-muted">{location.context}</p>}
      <Link to={location.evidence_url} className="mt-1 inline-block text-xs font-semibold text-umich-blue underline underline-offset-2">
        Open stored page evidence
      </Link>
    </li>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full border border-border bg-surface-muted px-2 py-0.5 text-2xs font-semibold text-fg-muted">{children}</span>;
}

function sourceLabel(pipeline: IssueRow["pipeline"]): string {
  return {
    axe: "axe-core",
    alfa: "Siteimprove Alfa · standardized ACT rule",
    semantic: "Local AI",
    keyboard: "Keyboard probe",
    responsive: "Responsive probe",
    focus: "Focus probe",
    visual: "Visual probe",
    image: "OCR + vision",
    protected_image: "Protected image",
  }[pipeline] ?? pipeline;
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col text-xs font-semibold uppercase tracking-wide text-fg-subtle">
      {label}
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 min-h-target rounded-xs border border-border bg-surface px-2 py-2 text-sm font-normal normal-case tracking-normal text-fg focus:border-umich-blue focus:outline-none"
      >
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

function DownloadLink({
  href,
  children,
  secondary = false,
}: {
  href: string;
  children: React.ReactNode;
  secondary?: boolean;
}) {
  return (
    <a
      href={href}
      className={`inline-flex min-h-target items-center justify-center gap-2 rounded-xs px-4 py-2.5 text-sm font-semibold no-underline ${secondary ? "border border-border bg-surface text-fg hover:bg-surface-muted" : "bg-umich-blue text-fg-inverse hover:bg-umich-blue-600"}`}
    >
      {children}
    </a>
  );
}
