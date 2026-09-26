import { useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { ArrowRight, X } from "lucide-react";
import type { SiteHistoryPoint } from "../../api/types";
import { Button, LinkButton, relativeTime } from "../ui";
import { cn } from "../../lib/cn";
import { Cell, ColumnHeader, Row, RowHeader, Table, TableHead } from "../table/Table";
import { agoLong, count, plural } from "./format";

type Measure = "occurrences" | "groups";
const MEASURES: Record<Measure, string> = { occurrences: "Occurrences", groups: "Issue groups" };

const HEIGHT = 300;
const MARGIN = { top: 40, right: 36, bottom: 60, left: 52 };
/** Room between a point and the plot edge, so an end point's label is not clipped. */
const INSET = 28;
/** Narrowest gap between two x-axis labels ("Scan 10" over "34d ago"). */
const LABEL_GAP = 72;

/**
 * Every completed scan of the site as one line, oldest to newest.
 *
 * A point is a button: click it, or Tab to it and press Enter, and the panel
 * under the chart names the scan with a link to its issues and, when it is a
 * different scan from the two being compared, a link that compares it. The
 * arrow keys move between points. The same numbers are one click away as a
 * table, which is also the way to choose a scan without the chart at all.
 */
export default function TrendChart({
  points,
  total,
  currentId,
  baselineId,
}: {
  points: SiteHistoryPoint[];
  total: number;
  currentId: number;
  baselineId: number | null;
}) {
  const [measure, setMeasure] = useState<Measure>("occurrences");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);
  const pointRefs = useRef(new Map<number, SVGGElement>());
  const tableId = useId();
  const selected = points.find((point) => point.id === selectedId) ?? null;
  const value = (point: SiteHistoryPoint) => (measure === "occurrences" ? point.occurrences : point.groups);
  const first = points[0];
  const last = points[points.length - 1];

  const closePanel = () => {
    const id = selectedId;
    setSelectedId(null);
    // The close button goes away with the panel: focus returns to the point.
    if (id !== null) pointRefs.current.get(id)?.focus();
  };

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="trend-heading" className="text-base font-semibold">Trend over time</h2>
          <p className="mt-1 text-sm text-fg-muted">{trendSummary(points, measure, value)}</p>
        </div>
        <div role="group" aria-label="Chart measure" className="inline-flex rounded-xs border border-border bg-surface-subtle p-1">
          {(Object.keys(MEASURES) as Measure[]).map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={measure === key}
              onClick={() => setMeasure(key)}
              className={cn(
                "min-h-target rounded-2xs px-3 text-sm font-semibold focus-visible:outline-none focus-visible:shadow-focus",
                measure === key ? "bg-umich-blue text-fg-inverse" : "text-fg hover:bg-surface-muted",
              )}
            >
              {MEASURES[key]}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-3 text-xs font-semibold text-fg">
        {points.length < total
          ? `Showing the ${points.length} most recent of ${total} completed scans, from scan ${first.id} to the most recent, scan ${last.id}.`
          : `Showing ${count(points.length, "completed scan")}, from scan ${first.id} to the most recent, scan ${last.id}.`}
      </p>

      <Plot
        points={points}
        measure={measure}
        value={value}
        currentId={currentId}
        baselineId={baselineId}
        selectedId={selectedId}
        onSelect={(id) => setSelectedId((previous) => (previous === id ? null : id))}
        pointRefs={pointRefs.current}
      />

      {/* The panel is not itself live: this line says what was chosen, once,
          without reading out the panel's buttons as well. */}
      <p role="status" className="sr-only">
        {selected ? `Scan ${selected.id} selected: ${totalsSentence(selected)}` : ""}
      </p>
      {selected && (
        <div className="mt-3 flex flex-wrap items-center gap-3 rounded-xs border border-l-4 border-border border-l-umich-blue bg-surface-subtle px-4 py-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold">
              Scan {selected.id} · {agoLong(selected.started_at)}
              {selected.id === currentId && <span className="font-normal text-fg-muted"> · this report</span>}
              {selected.id === baselineId && <span className="font-normal text-fg-muted"> · compared with</span>}
            </h3>
            <p className="text-sm text-fg-muted">{totalsSentence(selected)}</p>
          </div>
          <CompareLink point={selected} points={points} currentId={currentId} baselineId={baselineId} />
          {selected.id !== currentId && (
            <LinkButton variant="primary" to={`/scans/${selected.id}/issues`}>
              Open scan {selected.id} issues
              <ArrowRight className="h-4 w-4" aria-hidden />
            </LinkButton>
          )}
          <Button type="button" variant="ghost" onClick={closePanel} aria-label={`Close scan ${selected.id} details`}>
            <X className="h-5 w-5" aria-hidden />
          </Button>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <ul className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-fg-muted">
          <li className="inline-flex items-center gap-1.5"><Swatch kind="current" /> This report</li>
          {baselineId !== null && <li className="inline-flex items-center gap-1.5"><Swatch kind="baseline" /> Compared with</li>}
          <li className="inline-flex items-center gap-1.5"><Swatch kind="other" /> Other scans</li>
          <li>Select a point (click, or Tab + Enter) for details.</li>
        </ul>
        <Button type="button" aria-expanded={showTable} aria-controls={tableId} onClick={() => setShowTable((open) => !open)}>
          {showTable ? "Hide data table" : "Show as data table"}
        </Button>
      </div>
      <div id={tableId} hidden={!showTable}>
        {showTable && <HistoryTable points={points} currentId={currentId} baselineId={baselineId} />}
      </div>
    </>
  );
}

function Plot({
  points,
  measure,
  value,
  currentId,
  baselineId,
  selectedId,
  onSelect,
  pointRefs,
}: {
  points: SiteHistoryPoint[];
  measure: Measure;
  value: (point: SiteHistoryPoint) => number;
  currentId: number;
  baselineId: number | null;
  selectedId: number | null;
  onSelect: (id: number) => void;
  pointRefs: Map<number, SVGGElement>;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  const gradientId = useId();
  useLayoutEffect(() => {
    const node = box.current;
    if (!node) return;
    setWidth(node.clientWidth || 800);
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width || 800));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const plotLeft = MARGIN.left + INSET;
  const plotRight = Math.max(plotLeft + 1, width - MARGIN.right - INSET);
  const base = HEIGHT - MARGIN.bottom;
  const { top, step } = niceScale(Math.max(0, ...points.map(value)));
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  const x = (i: number) =>
    points.length === 1 ? (plotLeft + plotRight) / 2 : plotLeft + (i * (plotRight - plotLeft)) / (points.length - 1);
  const y = (v: number) => base - (v / top) * (base - MARGIN.top);
  const spacing = points.length > 1 ? (plotRight - plotLeft) / (points.length - 1) : Infinity;
  const every = Math.max(1, Math.ceil(LABEL_GAP / spacing));
  const labelled = (i: number, id: number) =>
    i % every === 0 || i === points.length - 1 || id === currentId || id === baselineId || id === selectedId;
  const line = points.map((point, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(value(point))}`).join(" ");
  const area = `${line} L${x(points.length - 1)},${base} L${x(0)},${base} Z`;

  const move = (event: KeyboardEvent<SVGGElement>, i: number) => {
    const next =
      event.key === "ArrowRight" || event.key === "ArrowDown" ? i + 1
      : event.key === "ArrowLeft" || event.key === "ArrowUp" ? i - 1
      : event.key === "Home" ? 0
      : event.key === "End" ? points.length - 1
      : null;
    if (next === null) return;
    event.preventDefault();
    const target = points[Math.min(points.length - 1, Math.max(0, next))];
    pointRefs.get(target.id)?.focus();
  };

  return (
    <div ref={box} className="mt-2 w-full">
      <svg
        role="group"
        aria-label={`${MEASURES[measure]} per completed scan`}
        width={width}
        height={HEIGHT}
        viewBox={`0 0 ${width} ${HEIGHT}`}
        className="block max-w-full overflow-visible"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" style={{ stopColor: "rgb(var(--c-fg-subtle))", stopOpacity: 0.16 }} />
            <stop offset="100%" style={{ stopColor: "rgb(var(--c-fg-subtle))", stopOpacity: 0.02 }} />
          </linearGradient>
        </defs>
        <g aria-hidden>
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={MARGIN.left} x2={width - MARGIN.right} y1={y(tick)} y2={y(tick)} className={tick === 0 ? "stroke-border-strong" : "stroke-border"} />
              <text x={MARGIN.left - 10} y={y(tick)} dy="0.35em" textAnchor="end" className="fill-fg-muted font-mono text-xs">
                {tick.toLocaleString()}
              </text>
            </g>
          ))}
          <path d={area} fill={`url(#${gradientId})`} />
          <path d={line} fill="none" className="stroke-umich-blue" strokeWidth={2.5} strokeLinejoin="round" />
          {points.map((point, i) =>
            point.id === selectedId ? (
              <line key="guide" x1={x(i)} x2={x(i)} y1={y(value(point)) + 14} y2={base} className="stroke-fg-subtle" strokeDasharray="4 4" />
            ) : null,
          )}
          {points.map((point, i) => (
            <g key={point.id}>
              <text
                x={x(i)}
                y={y(value(point)) - 14}
                textAnchor="middle"
                className={cn("fill-fg font-mono text-sm", point.id === currentId && "font-bold")}
              >
                {labelled(i, point.id) || spacing >= 40 ? value(point).toLocaleString() : ""}
              </text>
              {labelled(i, point.id) && (
                <>
                  <text x={x(i)} y={base + 24} textAnchor="middle" className={cn("fill-fg text-sm", point.id === currentId ? "font-bold" : "font-semibold")}>
                    Scan {point.id}
                  </text>
                  <text x={x(i)} y={base + 43} textAnchor="middle" className="fill-fg-muted text-xs">
                    {relativeTime(point.started_at)}
                  </text>
                </>
              )}
            </g>
          ))}
        </g>
        {points.map((point, i) => {
          const cx = x(i);
          const cy = y(value(point));
          const isCurrent = point.id === currentId;
          const isBaseline = point.id === baselineId;
          const isSelected = point.id === selectedId;
          return (
            <g
              key={point.id}
              ref={(node) => {
                if (node) pointRefs.set(point.id, node);
                else pointRefs.delete(point.id);
              }}
              role="button"
              tabIndex={0}
              aria-pressed={isSelected}
              aria-label={`Scan ${point.id}, ${agoLong(point.started_at)}: ${totalsSentence(point)}${isCurrent ? " This report." : isBaseline ? " Compared with." : ""}`}
              onClick={() => onSelect(point.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(point.id);
                } else {
                  move(event, i);
                }
              }}
              className="group cursor-pointer outline-none"
            >
              {/* A 44px target around a small mark (SC 2.5.5). */}
              <circle cx={cx} cy={cy} r={22} fill="transparent" />
              <circle cx={cx} cy={cy} r={19} fill="none" strokeWidth={3} className="stroke-umich-blue opacity-0 group-focus-visible:opacity-100" />
              {isSelected && <circle cx={cx} cy={cy} r={13} fill="none" strokeWidth={2} className="stroke-umich-blue" />}
              <circle
                cx={cx}
                cy={cy}
                r={isCurrent ? 7.5 : 6}
                strokeWidth={2.5}
                className={cn(
                  isCurrent && "fill-umich-blue stroke-surface",
                  isBaseline && "fill-fg-subtle stroke-surface",
                  !isCurrent && !isBaseline && "fill-surface stroke-umich-blue group-hover:fill-surface-muted",
                )}
              />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/** Where comparing with a selected scan leads: always the later scan's page. */
function CompareLink({
  point,
  points,
  currentId,
  baselineId,
}: {
  point: SiteHistoryPoint;
  points: SiteHistoryPoint[];
  currentId: number;
  baselineId: number | null;
}) {
  if (point.id === currentId || point.id === baselineId) return null;
  return <LinkButton to={compareHref(point, currentId, points)}>Compare with this report</LinkButton>;
}

/**
 * A comparison belongs to the later report and takes the earlier one as its
 * baseline. "Later" is the trend's own order (start time, as the server
 * orders a baseline); ids only decide when this report is outside the window.
 */
function compareHref(point: SiteHistoryPoint, currentId: number, points: SiteHistoryPoint[]): string {
  const at = points.findIndex((p) => p.id === point.id);
  const current = points.findIndex((p) => p.id === currentId);
  const earlier = current >= 0 ? at < current : point.id < currentId;
  return earlier
    ? `/scans/${currentId}/compare?compare_to=${point.id}`
    : `/scans/${point.id}/compare?compare_to=${currentId}`;
}

function HistoryTable({
  points,
  currentId,
  baselineId,
}: {
  points: SiteHistoryPoint[];
  currentId: number;
  baselineId: number | null;
}) {
  return (
    <div className="mt-3 overflow-x-auto">
      <Table caption="Completed scans of this site, oldest first">
        <TableHead>
          <tr>
            <ColumnHeader>Scan</ColumnHeader>
            <ColumnHeader>Scanned</ColumnHeader>
            <ColumnHeader>Occurrences</ColumnHeader>
            <ColumnHeader>Issue groups</ColumnHeader>
            <ColumnHeader><span className="sr-only">Actions</span></ColumnHeader>
          </tr>
        </TableHead>
        <tbody>
          {points.map((point, index) => (
            <Row key={point.id} index={index}>
              <RowHeader>
                Scan {point.id}
                {point.id === currentId && <span className="font-normal text-fg-muted"> · this report</span>}
                {point.id === baselineId && <span className="font-normal text-fg-muted"> · compared with</span>}
              </RowHeader>
              <Cell>{agoLong(point.started_at)}</Cell>
              <Cell numeric>{point.occurrences.toLocaleString()}</Cell>
              <Cell numeric>{point.groups.toLocaleString()}</Cell>
              <Cell className="py-1">
                <span className="flex flex-wrap gap-x-4">
                  {point.id !== currentId && point.id !== baselineId && (
                    <LinkButtonText to={compareHref(point, currentId, points)}>
                      Compare<span className="sr-only"> scan {point.id}</span> with this report
                    </LinkButtonText>
                  )}
                  {point.id !== currentId && (
                    <LinkButtonText to={`/scans/${point.id}/issues`}>
                      Open<span className="sr-only"> scan {point.id}</span> issues
                    </LinkButtonText>
                  )}
                </span>
              </Cell>
            </Row>
          ))}
        </tbody>
      </Table>
    </div>
  );
}

function LinkButtonText({ to, children }: { to: string; children: ReactNode }) {
  return (
    <LinkButton variant="ghost" to={to} className="px-1 text-umich-blue underline underline-offset-2">
      {/* One flex item: the button's gap would otherwise open around the
          visually hidden words. */}
      <span>{children}</span>
    </LinkButton>
  );
}

function Swatch({ kind }: { kind: "current" | "baseline" | "other" }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden className="shrink-0">
      <circle
        cx="6"
        cy="6"
        r="4.5"
        strokeWidth="2"
        className={cn(
          kind === "current" && "fill-umich-blue stroke-umich-blue",
          kind === "baseline" && "fill-fg-subtle stroke-fg-subtle",
          kind === "other" && "fill-surface stroke-umich-blue",
        )}
      />
    </svg>
  );
}

function totalsSentence(point: SiteHistoryPoint): string {
  return `${count(point.occurrences, "occurrence")} in ${count(point.groups, "issue group")}.`;
}

function trendSummary(
  points: SiteHistoryPoint[],
  measure: Measure,
  value: (point: SiteHistoryPoint) => number,
): string {
  const first = points[0];
  const last = points[points.length - 1];
  const from = value(first);
  const to = value(last);
  const diff = to - from;
  // From a handful of occurrences a percentage runs to thousands and says
  // nothing the count does not, so it is given only up to a fivefold change.
  const ratio = from > 0 ? Math.abs(diff) / from : Infinity;
  const percent = ratio <= 5 ? ` (${Math.round(ratio * 100)}%)` : "";
  const direction =
    diff < 0 ? `down ${(-diff).toLocaleString()}${percent}` : diff > 0 ? `up ${diff.toLocaleString()}${percent}` : "unchanged";
  return `${MEASURES[measure]} ${direction} from scan ${first.id} to scan ${last.id} across ${points.length} completed ${plural(points.length, "scan")}.`;
}

/** Round axis steps (1, 2 or 5 times a power of ten), whole numbers only. */
function niceScale(max: number, ticks = 4): { top: number; step: number } {
  if (max <= 0) return { top: 4, step: 1 };
  const raw = max / ticks;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normal = raw / magnitude;
  const step = Math.max(1, (normal <= 1 ? 1 : normal <= 2 ? 2 : normal <= 5 ? 5 : 10) * magnitude);
  return { top: Math.ceil(max / step) * step, step };
}
