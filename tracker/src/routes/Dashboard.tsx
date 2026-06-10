/**
 * Dashboard rollup: open issues by severity, tier coverage of the
 * check catalog, and the needs-a-human count. The portfolio score and
 * trend line arrive with the dedicated dashboard iteration after
 * Module A ships; this version only reports numbers that exist.
 */

import { Link } from "react-router-dom";
import { checksForModule } from "../data/checks";
import { useAppData } from "../data/useStore";
import { MODULE_TITLE, TIER_LABEL } from "../data/types";
import type { ModuleId, Severity, Tier } from "../data/types";
import { Card, PageTitle, TierBadge } from "../components/ui";

const SEVERITIES: Severity[] = ["critical", "serious", "moderate", "minor"];
const TIERS: Tier[] = [
  "automated",
  "ai_assisted",
  "agentic",
  "manual",
  "local_vlm",
];
const MODULES: ModuleId[] = ["A", "B", "C", "D", "E", "F"];

export default function DashboardRoute() {
  const data = useAppData();
  const openIssues = data.issues.filter(
    (i) => i.status === "open" || i.status === "in_progress",
  );

  const bySeverity = SEVERITIES.map((s) => ({
    severity: s,
    count: openIssues.filter((i) => i.severity === s).length,
  }));

  const byTier = TIERS.map((t) => ({
    tier: t,
    count: data.checks.filter((c) => c.tier === t).length,
  }));
  const needsHuman = data.checks.filter((c) => c.tier === "manual").length;

  return (
    <>
      <PageTitle
        title="Dashboard"
        subtitle="Where the portfolio stands and how much of the catalog needs a human."
      />

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="p-4">
          <h2 className="mb-3 text-lg font-bold">Open issues by severity</h2>
          {openIssues.length === 0 ? (
            <p className="text-ink-muted">
              No open issues yet. Run a module in the{" "}
              <Link to="/runner" className="text-brand underline">
                Test Runner
              </Link>{" "}
              to start.
            </p>
          ) : (
            <dl className="flex flex-col gap-2">
              {bySeverity.map(({ severity, count }) => (
                <div key={severity} className="flex items-center gap-3">
                  <dt className="w-28 font-semibold capitalize">{severity}</dt>
                  <dd className="text-xl font-bold tabular-nums">{count}</dd>
                </div>
              ))}
            </dl>
          )}
        </Card>

        <Card className="p-4">
          <h2 className="mb-3 text-lg font-bold">Tier coverage of the catalog</h2>
          <p className="mb-2 text-sm text-ink-muted">
            Every check routes to the cheapest tier that can clear it.
          </p>
          <dl className="flex flex-col gap-2">
            {byTier.map(({ tier, count }) => (
              <div key={tier} className="flex items-center gap-3">
                <dt className="w-44">
                  <TierBadge tier={tier} />
                </dt>
                <dd className="text-xl font-bold tabular-nums">{count}</dd>
                <dd className="sr-only">{TIER_LABEL[tier]}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 border-t border-line pt-3 font-semibold">
            Needs a human: {needsHuman} of {data.checks.length} checks
          </p>
        </Card>

        <Card className="p-4 md:col-span-2">
          <h2 className="mb-3 text-lg font-bold">Module progress</h2>
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {MODULES.map((m) => {
              const count = checksForModule(m).length;
              const ready = m === "A";
              return (
                <li
                  key={m}
                  className="flex items-center gap-2 rounded border border-line px-3 py-2"
                >
                  <span className="font-semibold">
                    Module {m}: {MODULE_TITLE[m]}
                  </span>
                  <span className="ml-auto text-sm text-ink-muted">
                    {count} checks, {ready ? "runnable now" : "coming next"}
                  </span>
                </li>
              );
            })}
          </ul>
        </Card>
      </div>
    </>
  );
}
