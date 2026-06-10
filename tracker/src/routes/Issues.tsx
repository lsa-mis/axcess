/**
 * Issues inventory. Groups three ways (severity, WCAG criterion, page)
 * with URL-persisted filters, so a filtered view can be bookmarked and
 * shared. Every row links to the issue detail.
 */

import { Link, useSearchParams } from "react-router-dom";
import { useAppData } from "../data/useStore";
import type { Issue, Severity } from "../data/types";
import {
  Card,
  PageTitle,
  SeverityBadge,
  TierBadge,
  cn,
  inputClass,
} from "../components/ui";

const SEVERITIES: Severity[] = ["critical", "serious", "moderate", "minor"];
type GroupMode = "severity" | "wcag" | "page";

export default function IssuesRoute() {
  const data = useAppData();
  const [params, setParams] = useSearchParams();

  const groupMode = (params.get("group") ?? "severity") as GroupMode;
  const severityFilter = params.get("severity") ?? "";
  const statusFilter = params.get("status") ?? "open";

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  let issues = data.issues;
  if (severityFilter) {
    issues = issues.filter((i) => i.severity === severityFilter);
  }
  if (statusFilter === "open") {
    issues = issues.filter(
      (i) => i.status === "open" || i.status === "in_progress",
    );
  } else if (statusFilter === "closed") {
    issues = issues.filter(
      (i) =>
        i.status === "remediated" ||
        i.status === "accepted_risk" ||
        i.status === "false_positive",
    );
  }

  const groups = groupIssues(issues, groupMode, data);

  return (
    <>
      <PageTitle
        title="Issues"
        subtitle={`${issues.length} issue${issues.length === 1 ? "" : "s"} matching the current filters`}
      />

      <Card className="mb-4 p-3">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="issues-group" className="text-sm font-semibold">
              Group by
            </label>
            <select
              id="issues-group"
              className={inputClass}
              value={groupMode}
              onChange={(e) => setParam("group", e.target.value)}
            >
              <option value="severity">Severity</option>
              <option value="wcag">WCAG criterion</option>
              <option value="page">Page</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="issues-severity" className="text-sm font-semibold">
              Severity
            </label>
            <select
              id="issues-severity"
              className={inputClass}
              value={severityFilter}
              onChange={(e) => setParam("severity", e.target.value)}
            >
              <option value="">All severities</option>
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="issues-status" className="text-sm font-semibold">
              Status
            </label>
            <select
              id="issues-status"
              className={inputClass}
              value={statusFilter}
              onChange={(e) => setParam("status", e.target.value)}
            >
              <option value="open">Open and in progress</option>
              <option value="closed">Closed</option>
              <option value="all">All</option>
            </select>
          </div>
        </div>
      </Card>

      {groups.length === 0 ? (
        <Card className="p-6 text-center text-ink-muted">
          <p className="font-semibold text-ink">No issues match.</p>
          <p className="mt-1">
            Run a module in the Test Runner; failed checks land here
            automatically.
          </p>
        </Card>
      ) : (
        <div className="flex flex-col gap-4">
          {groups.map((group) => (
            <section key={group.key} aria-labelledby={`group-${group.key}`}>
              <h2
                id={`group-${group.key}`}
                className="mb-2 text-lg font-bold text-ink"
              >
                {group.label}{" "}
                <span className="font-normal text-ink-muted">
                  ({group.issues.length})
                </span>
              </h2>
              <Card>
                <ul className="divide-y divide-line">
                  {group.issues.map((issue) => (
                    <IssueRow key={issue.id} issue={issue} />
                  ))}
                </ul>
              </Card>
            </section>
          ))}
        </div>
      )}
    </>
  );
}

function IssueRow({ issue }: { issue: Issue }) {
  const data = useAppData();
  const check = data.checks.find((c) => c.id === issue.checkId);
  const page = data.pages.find((p) => p.id === issue.pageId);
  return (
    <li>
      <Link
        to={`/issues/${issue.id}`}
        className={cn(
          "flex min-h-target flex-wrap items-center gap-3 px-4 py-3 no-underline hover:bg-paper-muted",
        )}
      >
        <SeverityBadge severity={issue.severity} />
        <span className="font-semibold text-ink">
          {check ? check.title : "Unknown check"}
        </span>
        <span className="text-sm text-ink-muted">
          {page ? page.title : "Unknown page"}
        </span>
        <span className="ml-auto flex items-center gap-2">
          <TierBadge tier={issue.foundByTier} />
          <span className="text-sm text-ink-muted">{issue.status}</span>
        </span>
      </Link>
    </li>
  );
}

function groupIssues(
  issues: Issue[],
  mode: GroupMode,
  data: ReturnType<typeof useAppData>,
): Array<{ key: string; label: string; issues: Issue[] }> {
  const buckets = new Map<string, { label: string; issues: Issue[] }>();
  const push = (key: string, label: string, issue: Issue) => {
    const bucket = buckets.get(key) ?? { label, issues: [] };
    bucket.issues.push(issue);
    buckets.set(key, bucket);
  };

  for (const issue of issues) {
    if (mode === "severity") {
      push(issue.severity, `Severity: ${issue.severity}`, issue);
    } else if (mode === "wcag") {
      const check = data.checks.find((c) => c.id === issue.checkId);
      const wcag = check ? check.wcag : "unknown";
      push(wcag, `WCAG ${wcag}`, issue);
    } else {
      const page = data.pages.find((p) => p.id === issue.pageId);
      push(
        issue.pageId,
        page ? `${page.title} (${page.url})` : "Unknown page",
        issue,
      );
    }
  }

  const order =
    mode === "severity"
      ? ["critical", "serious", "moderate", "minor"]
      : [...buckets.keys()].sort();
  return order
    .filter((k) => buckets.has(k))
    .map((k) => ({ key: k, ...buckets.get(k)! }));
}
