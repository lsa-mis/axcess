import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, PageHeader } from "../components/ui";
import type { RoadmapItem, TrackingStatus } from "../api/types";

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
