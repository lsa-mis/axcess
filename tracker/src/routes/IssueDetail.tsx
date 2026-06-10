/**
 * Issue detail: the full record for one issue. Shows the owning check,
 * the page, the tier badge, evidence, and a status workflow. The
 * remediation handoff button is stubbed for a later iteration and says
 * so honestly rather than pretending.
 */

import { Link, useParams } from "react-router-dom";
import { store } from "../data/store";
import { useAppData } from "../data/useStore";
import type { IssueStatus } from "../data/types";
import {
  Button,
  Card,
  PageTitle,
  SeverityBadge,
  TierBadge,
  inputClass,
} from "../components/ui";

const STATUSES: IssueStatus[] = [
  "open",
  "in_progress",
  "remediated",
  "accepted_risk",
  "false_positive",
];

export default function IssueDetailRoute() {
  const { issueId } = useParams<{ issueId: string }>();
  const data = useAppData();
  const issue = data.issues.find((i) => i.id === issueId);

  if (!issue) {
    return (
      <Card className="p-6">
        <p className="font-semibold">This issue does not exist.</p>
        <Link to="/issues" className="mt-2 inline-block text-brand underline">
          Back to issues
        </Link>
      </Card>
    );
  }

  const check = data.checks.find((c) => c.id === issue.checkId);
  const page = data.pages.find((p) => p.id === issue.pageId);
  const run = data.testRuns.find((r) => r.id === issue.testRunId);

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-2 text-sm text-ink-muted">
        <Link to="/issues" className="text-brand underline">
          Issues
        </Link>{" "}
        / Issue {issue.id.slice(0, 14)}
      </nav>
      <PageTitle
        title={check ? check.title : "Issue"}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={issue.severity} />
            <TierBadge tier={issue.foundByTier} />
            {check ? (
              <span className="text-sm">WCAG {check.wcag}</span>
            ) : null}
          </span>
        }
      />

      <div className="grid max-w-4xl gap-4 md:grid-cols-2">
        <Card className="p-4">
          <h2 className="mb-2 text-lg font-bold">Where</h2>
          {page ? (
            <>
              <p className="font-semibold">{page.title}</p>
              <p className="break-all text-sm text-ink-muted">{page.url}</p>
              <a
                href={page.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-flex min-h-target items-center text-brand underline"
              >
                Open the page in a new tab
              </a>
            </>
          ) : (
            <p>The page record was removed.</p>
          )}
          {run ? (
            <p className="mt-3 text-sm text-ink-muted">
              Found during a Module {run.module} run started{" "}
              {new Date(run.startedAt).toLocaleString()}.
            </p>
          ) : null}
        </Card>

        <Card className="p-4">
          <h2 className="mb-2 text-lg font-bold">Status</h2>
          <label htmlFor="issue-status" className="text-sm font-semibold">
            Workflow status
          </label>
          <select
            id="issue-status"
            className={`${inputClass} mt-1 block`}
            value={issue.status}
            onChange={(e) =>
              store.setIssueStatus(issue.id, e.target.value as IssueStatus)
            }
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace("_", " ")}
              </option>
            ))}
          </select>
          <p className="mt-3 text-sm text-ink-muted">
            Created {new Date(issue.createdAt).toLocaleString()}, last update{" "}
            {new Date(issue.updatedAt).toLocaleString()}.
          </p>
          <Button
            className="mt-3"
            onClick={() => store.addRemediation(issue.id, "Unassigned")}
          >
            Start a remediation record
          </Button>
          <p className="mt-2 text-sm text-ink-muted">
            JIRA and TDX handoff arrives with the integrations iteration.
            The remediation record keeps the assignment local until then.
          </p>
        </Card>

        <Card className="p-4 md:col-span-2">
          <h2 className="mb-2 text-lg font-bold">What the tester saw</h2>
          {issue.notes ? (
            <p className="whitespace-pre-wrap">{issue.notes}</p>
          ) : (
            <p className="text-ink-muted">No notes were recorded.</p>
          )}
          {check ? (
            <>
              <h3 className="mt-4 text-sm font-bold uppercase tracking-wide text-ink-muted">
                What this check expects
              </h3>
              <p className="mt-1">{check.expectedBehavior}</p>
            </>
          ) : null}
        </Card>

        {issue.evidence.screenshot || issue.evidence.screenReaderOutput ? (
          <Card className="p-4 md:col-span-2">
            <h2 className="mb-2 text-lg font-bold">Evidence</h2>
            {issue.evidence.screenshot ? (
              <img
                src={issue.evidence.screenshot}
                alt="Screenshot evidence attached when this issue was logged"
                className="max-h-96 w-auto rounded border border-line"
              />
            ) : null}
            {issue.evidence.screenReaderOutput ? (
              <>
                <h3 className="mt-3 text-sm font-bold uppercase tracking-wide text-ink-muted">
                  Screen reader output
                </h3>
                <pre className="mt-1 whitespace-pre-wrap rounded border border-line bg-paper-muted p-3 font-mono text-sm">
                  {issue.evidence.screenReaderOutput}
                </pre>
              </>
            ) : null}
          </Card>
        ) : null}

        {data.remediations.filter((r) => r.issueId === issue.id).length > 0 ? (
          <Card className="p-4 md:col-span-2">
            <h2 className="mb-2 text-lg font-bold">Remediations</h2>
            <ul className="divide-y divide-line">
              {data.remediations
                .filter((r) => r.issueId === issue.id)
                .map((r) => (
                  <li key={r.id} className="flex items-center gap-3 py-2">
                    <span className="font-semibold">{r.assignee}</span>
                    <span className="text-sm text-ink-muted">{r.status}</span>
                    <span className="ml-auto text-sm text-ink-muted">
                      {new Date(r.createdAt).toLocaleDateString()}
                    </span>
                  </li>
                ))}
            </ul>
          </Card>
        ) : null}
      </div>
    </>
  );
}
