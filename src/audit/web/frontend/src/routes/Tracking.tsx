import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader } from "../components/ui";
import type {
  CoverageCriterion,
  CoverageData,
  CoverageMethod,
  RoadmapItem,
  TrackingStatus,
} from "../api/types";

/**
 * Coverage & feature tracker — what the tool detects today versus what's
 * planned, across every pipeline. Reads from /api/tracking, which is
 * backed by the same source of truth as docs/coverage-tracker.md
 * (coverage_status.py) so the page can't claim coverage the code lacks.
 */
export default function TrackingRoute() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["tracking"],
    queryFn: api.getTracking,
  });

  const counts = data?.counts;

  return (
    <>
      <PageHeader
        title="Coverage & feature tracker"
        subtitle="What the tool detects today versus what's planned. Status is reconciled against the actual code."
      />

      {error && (
        <Card className="mb-4 border-sev-critical-bg p-4">
          <p className="text-sm text-sev-critical" role="alert">
            {error instanceof Error ? error.message : String(error)}
          </p>
        </Card>
      )}

      {counts && (
        <div className="mb-6 flex flex-wrap gap-2">
          <StatusBadge status="shipped">{counts.shipped} shipped</StatusBadge>
          <StatusBadge status="in_progress">
            {counts.in_progress} in progress
          </StatusBadge>
          <StatusBadge status="planned">{counts.planned} planned</StatusBadge>
          <span className="self-center text-xs text-fg-subtle">
            (AI roadmap items)
          </span>
        </div>
      )}

      {data?.coverage && <CoverageSection coverage={data.coverage} />}

      <section aria-labelledby="shipped-h" className="mb-8">
        <h2 id="shipped-h" className="mb-1 text-base font-semibold text-fg">
          Shipped pipelines — what runs today
        </h2>
        <p className="mb-3 text-sm text-fg-muted">
          The three deterministic pipelines need only chromium (no Ollama);
          the two AI pipelines need a local Ollama daemon.
        </p>
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">
              Detection pipelines that run on a default crawl
            </caption>
            <thead className="bg-surface-muted text-2xs uppercase tracking-wide text-fg-subtle">
              <tr>
                <Th>Pipeline</Th>
                <Th>Engine</Th>
                <Th>WCAG coverage</Th>
                <Th>AI?</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border align-top">
              {isLoading && (
                <tr>
                  <td className="px-4 py-3 text-fg-subtle" colSpan={4}>
                    Loading…
                  </td>
                </tr>
              )}
              {data?.shipped.map((p) => (
                <tr key={p.pipeline} className="hover:bg-surface-muted/60">
                  <th scope="row" className="px-4 py-3 text-left font-medium text-fg">
                    {p.name}{" "}
                    <code className="rounded bg-surface-muted px-1 text-2xs text-fg-muted">
                      {p.pipeline}
                    </code>
                    {p.note && (
                      <span className="mt-1 block text-2xs font-normal text-fg-subtle">
                        {p.note}
                      </span>
                    )}
                  </th>
                  <td className="px-4 py-3 text-fg-muted">{p.engine}</td>
                  <td className="px-4 py-3 text-fg-muted">{p.scs}</td>
                  <td className="px-4 py-3">
                    {p.needs_ai ? (
                      <span className="rounded bg-umich-blue px-2 py-0.5 text-2xs font-bold text-fg-inverse">
                        AI
                      </span>
                    ) : (
                      <span className="rounded bg-surface-muted px-2 py-0.5 text-2xs font-semibold text-fg-muted">
                        rule
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </section>

      <section aria-labelledby="roadmap-h">
        <h2 id="roadmap-h" className="mb-1 text-base font-semibold text-fg">
          AI roadmap — semantic / VLM / cross-page analyzers
        </h2>
        <p className="mb-3 text-sm text-fg-muted">
          The queue to close the AI coverage gap. A criterion listed in the
          orchestrator&apos;s default criteria but with no analyzer class is
          skipped at runtime — those read “planned,” not “shipped.”
        </p>
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">
              Planned AI analyzers by WCAG criterion
            </caption>
            <thead className="bg-surface-muted text-2xs uppercase tracking-wide text-fg-subtle">
              <tr>
                <Th>WCAG</Th>
                <Th>Issue</Th>
                <Th>Model class</Th>
                <Th>What the AI step does</Th>
                <Th>Reuses</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border align-top">
              {data?.roadmap.map((r) => (
                <RoadmapRow key={r.wcag} item={r} />
              ))}
            </tbody>
          </table>
        </Card>
      </section>

      <p className="mt-4 text-xs text-fg-subtle">
        Long-form version with the verification map:{" "}
        <code>docs/coverage-tracker.md</code>.
      </p>
    </>
  );
}

function RoadmapRow({ item }: { item: RoadmapItem }) {
  return (
    <tr className="hover:bg-surface-muted/60">
      <th scope="row" className="whitespace-nowrap px-4 py-3 text-left font-mono text-xs text-fg">
        {item.wcag}
      </th>
      <td className="px-4 py-3 text-fg">{item.issue}</td>
      <td className="px-4 py-3 text-xs text-fg-muted">{item.model_class}</td>
      <td className="px-4 py-3 text-fg-muted">
        {item.what}
        {item.note && (
          <span className="mt-1 block text-2xs text-fg-subtle">{item.note}</span>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-fg-subtle">{item.reuse}</td>
      <td className="px-4 py-3">
        <StatusBadge status={item.status}>
          {item.status.replace("_", " ")}
        </StatusBadge>
      </td>
    </tr>
  );
}

const Th = ({ children }: { children: React.ReactNode }) => (
  <th scope="col" className="px-4 py-2 text-left font-semibold">
    {children}
  </th>
);

/**
 * Status pill. Colour is backed by a text label (never colour alone) so
 * the badge clears WCAG 1.4.1; each fill is a dark tone paired with white
 * for AAA contrast (≥7:1).
 */
function StatusBadge({
  status,
  children,
}: {
  status: TrackingStatus;
  children: React.ReactNode;
}) {
  const tone: Record<TrackingStatus, string> = {
    shipped: "bg-[#0f5132]",
    in_progress: "bg-[#6b3a00]",
    planned: "bg-[#374151]",
  };
  return (
    <span
      className={`inline-block whitespace-nowrap rounded px-2 py-0.5 text-2xs font-bold text-white ${tone[status]}`}
    >
      {children}
    </span>
  );
}

// Method fills: dark tones paired with white for AAA contrast (≥7:1).
const METHOD_TONE: Record<CoverageMethod, string> = {
  automated: "bg-[#0f5132]",
  partial: "bg-[#0b4f6c]",
  "ai-assisted": "bg-[#6b3a00]",
  manual: "bg-[#374151]",
};

function CoverageMethodBadge({
  method,
  label,
}: {
  method: CoverageMethod;
  label: string;
}) {
  return (
    <span
      className={`inline-block whitespace-nowrap rounded px-2 py-0.5 text-2xs font-bold text-white ${METHOD_TONE[method]}`}
    >
      {label}
    </span>
  );
}

/**
 * The honest WCAG 2.2 A/AA coverage breakdown — what Axcess checks
 * automatically, what it AI-assists, and (the long tail) what still needs
 * manual testing. Rendered straight from the coverage matrix so it can't
 * over-claim. The "What you must still test" column is the whole point.
 */
function CoverageSection({ coverage }: { coverage: CoverageData }) {
  const label = (m: CoverageMethod) => coverage.method_labels[m];
  return (
    <section aria-labelledby="cov-h" className="mb-8">
      <h2 id="cov-h" className="mb-1 text-base font-semibold text-fg">
        WCAG 2.2 A/AA coverage — automated vs. manual
      </h2>
      <p className="mb-3 text-sm text-fg-muted">
        Across all {coverage.total} Level A/AA success criteria, exactly what
        Axcess can determine for you — and what still needs a human.{" "}
        {coverage.covered} have automated or AI-assisted coverage;{" "}
        {coverage.manual_only} are manual-only.
      </p>

      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {coverage.methods.map((m) => (
          <Card key={m} className="p-3">
            <div className="flex items-baseline justify-between gap-2">
              <CoverageMethodBadge method={m} label={label(m)} />
              <span className="text-lg font-bold tabular-nums text-fg">
                {coverage.by_method[m] ?? 0}
              </span>
            </div>
            <p className="mt-1.5 text-2xs leading-snug text-fg-subtle">
              {coverage.method_blurb[m]}
            </p>
          </Card>
        ))}
      </div>

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">
            Every WCAG 2.2 A/AA success criterion and how Axcess covers it
          </caption>
          <thead className="bg-surface-muted text-2xs uppercase tracking-wide text-fg-subtle">
            <tr>
              <Th>SC</Th>
              <Th>Criterion</Th>
              <Th>Lvl</Th>
              <Th>Coverage</Th>
              <Th>What Axcess does</Th>
              <Th>What you must still test</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border align-top">
            {coverage.criteria.map((c: CoverageCriterion) => (
              <tr key={c.sc} className="hover:bg-surface-muted/60">
                <th
                  scope="row"
                  className="whitespace-nowrap px-4 py-3 text-left font-mono text-xs text-fg"
                >
                  {c.sc}
                </th>
                <td className="px-4 py-3 text-fg">{c.name}</td>
                <td className="px-4 py-3 text-xs text-fg-muted">{c.level}</td>
                <td className="px-4 py-3">
                  <CoverageMethodBadge method={c.method} label={label(c.method)} />
                </td>
                <td className="px-4 py-3 text-xs text-fg-muted">
                  {c.automated_check || <span className="text-fg-subtle">—</span>}
                </td>
                <td className="px-4 py-3 text-xs text-fg-muted">
                  {c.manual_check}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </section>
  );
}
