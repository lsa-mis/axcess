/**
 * Lighter destinations: Reports (tier comparison arrives with the
 * reports iteration), Settings (data export, import, reset), and the
 * global Search. Each is honest about what works today.
 */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { store } from "../data/store";
import { useAppData } from "../data/useStore";
import { TIER_LABEL } from "../data/types";
import type { Tier } from "../data/types";
import {
  Button,
  Card,
  Field,
  PageTitle,
  SeverityBadge,
  TierBadge,
  inputClass,
} from "../components/ui";

const TIERS: Tier[] = [
  "automated",
  "ai_assisted",
  "agentic",
  "manual",
  "local_vlm",
];

export function ReportsRoute() {
  const data = useAppData();
  return (
    <>
      <PageTitle
        title="Reports"
        subtitle="The tier comparison view: how the catalog and the found issues split across T1 to T5."
      />
      <Card className="max-w-3xl p-4">
        <table className="w-full text-left">
          <caption className="sr-only">
            Checks owned and issues found per testing tier
          </caption>
          <thead>
            <tr className="border-b border-line text-sm uppercase tracking-wide text-ink-muted">
              <th scope="col" className="py-2 pr-3">
                Tier
              </th>
              <th scope="col" className="py-2 pr-3">
                Checks owned
              </th>
              <th scope="col" className="py-2">
                Issues found
              </th>
            </tr>
          </thead>
          <tbody>
            {TIERS.map((tier) => {
              const owned = data.checks.filter((c) => c.tier === tier).length;
              const found = data.issues.filter(
                (i) => i.foundByTier === tier,
              ).length;
              return (
                <tr key={tier} className="border-b border-line">
                  <th scope="row" className="py-2 pr-3 font-normal">
                    <TierBadge tier={tier} />
                    <span className="sr-only">{TIER_LABEL[tier]}</span>
                  </th>
                  <td className="py-2 pr-3 text-lg font-bold tabular-nums">
                    {owned}
                  </td>
                  <td className="py-2 text-lg font-bold tabular-nums">
                    {found}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="mt-3 text-sm text-ink-muted">
          Per-module exports and the printable summary arrive with the
          reports iteration, after Modules B through F.
        </p>
      </Card>
    </>
  );
}

export function SettingsRoute() {
  const data = useAppData();
  const [feedback, setFeedback] = useState("");

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "a11y-tracker-export.json";
    a.click();
    URL.revokeObjectURL(url);
    setFeedback("Export downloaded.");
  };

  return (
    <>
      <PageTitle
        title="Settings"
        subtitle="Your data lives in this browser. Export it before clearing storage or switching machines."
      />
      <p role="status" aria-live="polite" className="mb-3 font-semibold">
        {feedback}
      </p>
      <Card className="max-w-xl p-4">
        <div className="flex flex-col gap-3">
          <div>
            <Button variant="primary" onClick={exportJson}>
              Export all data as JSON
            </Button>
          </div>
          <div>
            <Button
              variant="danger"
              onClick={() => {
                if (
                  window.confirm(
                    "Reset to sample data? This deletes every site, run, and issue stored in this browser.",
                  )
                ) {
                  store.reset();
                  setFeedback("Data reset to the sample seed.");
                }
              }}
            >
              Reset to sample data
            </Button>
          </div>
          <p className="text-sm text-ink-muted">
            Import, users, and role management arrive with the roles
            iteration.
          </p>
        </div>
      </Card>
    </>
  );
}

export function SearchRoute() {
  const data = useAppData();
  const [query, setQuery] = useState("");

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return null;
    const checks = data.checks.filter(
      (c) =>
        c.title.toLowerCase().includes(q) || c.wcag.toLowerCase().includes(q),
    );
    const pages = data.pages.filter(
      (p) =>
        p.title.toLowerCase().includes(q) || p.url.toLowerCase().includes(q),
    );
    const issues = data.issues.filter((i) => {
      const check = data.checks.find((c) => c.id === i.checkId);
      return (
        i.notes.toLowerCase().includes(q) ||
        (check ? check.title.toLowerCase().includes(q) : false)
      );
    });
    return { checks, pages, issues };
  }, [query, data]);

  return (
    <>
      <PageTitle
        title="Search"
        subtitle="Find checks, pages, and issues across the whole tracker."
      />
      <Card className="max-w-2xl p-4">
        <Field
          label="Search everything"
          htmlFor="global-search"
          hint="Type at least two characters. Matches check titles, WCAG numbers, page titles and URLs, and issue notes."
        >
          <input
            id="global-search"
            type="search"
            className={inputClass}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </Field>
      </Card>

      {results ? (
        <div className="mt-4 flex max-w-2xl flex-col gap-4">
          <section aria-label="Matching checks">
            <h2 className="mb-1 font-bold">Checks ({results.checks.length})</h2>
            <ul className="flex flex-col gap-1">
              {results.checks.map((c) => (
                <li key={c.id} className="flex items-center gap-2">
                  <TierBadge tier={c.tier} />
                  <span>
                    {c.title} (WCAG {c.wcag})
                  </span>
                </li>
              ))}
            </ul>
          </section>
          <section aria-label="Matching pages">
            <h2 className="mb-1 font-bold">Pages ({results.pages.length})</h2>
            <ul className="flex flex-col gap-1">
              {results.pages.map((p) => (
                <li key={p.id}>
                  {p.title}{" "}
                  <span className="text-sm text-ink-muted">{p.url}</span>
                </li>
              ))}
            </ul>
          </section>
          <section aria-label="Matching issues">
            <h2 className="mb-1 font-bold">Issues ({results.issues.length})</h2>
            <ul className="flex flex-col gap-1">
              {results.issues.map((i) => (
                <li key={i.id} className="flex items-center gap-2">
                  <SeverityBadge severity={i.severity} />
                  <Link to={`/issues/${i.id}`} className="text-brand underline">
                    Open issue
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        </div>
      ) : null}
    </>
  );
}
