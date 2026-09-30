import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import { Card, LinkButton, PageHeader } from "../components/ui";
import {
  protectedQueryKey,
  useProtectedIdentityContext,
} from "../hooks/useProtectedIdentityContext";
import { TablePagination, usePagedRows } from "../components/TablePagination";
import {
  Cell,
  ColumnHeader,
  Row,
  Table,
  TableBar,
  TableHead,
  TableRegion,
} from "../components/table/Table";
import { CHECK_LABEL, REVIEW_TYPE_LABEL } from "../lib/terms";
import type { ProtectedIssueIndexGroup } from "../api/types";

const SOURCE_LABEL: Record<ProtectedIssueIndexGroup["source_layer"], string> = {
  axe: CHECK_LABEL.axe,
  alfa: CHECK_LABEL.alfa,
  keyboard: CHECK_LABEL.keyboard,
  responsive: CHECK_LABEL.responsive,
  focus: CHECK_LABEL.focus,
  protected_image: CHECK_LABEL.protected_image,
  unavailable: "Check not recorded",
};

/** What each automatic result reads as in the Result column. */
const RESULT_LABEL: Record<string, string> = {
  failed: "Failed",
  cant_tell: REVIEW_TYPE_LABEL.expert_review,
  critical: "Critical",
  serious: "Serious",
  moderate: "Moderate",
  minor: "Minor",
};

/**
 * A deliberately aggregate-only review surface for protected reports. It is
 * not a replacement for page evidence: protected URLs, selectors, snippets,
 * screenshots, and OCR/VLM output are intentionally never rendered here.
 */
export default function ProtectedIssueIndexRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const protectedIdentity = useProtectedIdentityContext();
  const index = useQuery({
    queryKey: protectedQueryKey(
      "issue-index",
      protectedIdentity.fingerprint,
      id,
    ),
    queryFn: () => api.getProtectedIssueIndex(id),
    enabled:
      Number.isSafeInteger(id) && id > 0 && protectedIdentity.isReady,
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
  });
  const groups = useMemo(() => index.data?.groups ?? [], [index.data]);
  const resetKey = useMemo(
    () => groups.map((group) => `${group.source_layer}:${group.rule_id}:${group.engine_outcome}`).join(","),
    [groups],
  );
  const paged = usePagedRows(groups, { resetKey });

  if (!Number.isSafeInteger(id) || id <= 0) {
    return <p role="alert" className="text-sm text-sev-critical">This sign-in scan number is not valid. Check the address, or open the report from Reports.</p>;
  }
  if (protectedIdentity.isChecking) {
    return (
      <p aria-live="polite" className="text-sm text-fg-muted">
        Checking that you can open this sign-in scan…
      </p>
    );
  }
  if (protectedIdentity.error || !protectedIdentity.isReady) {
    return (
      <Card
        className="border-sev-critical/40 bg-sev-critical-bg p-4 text-sm text-sev-critical"
        role="alert"
      >
        {protectedIdentity.error instanceof Error
          ? protectedIdentity.error.message
          : "Axcess could not confirm your access to sign-in scans. Try again, or ask your administrator."}
      </Card>
    );
  }

  return (
    <>
      <PageHeader
        crumbs={[
          { label: "Reports", to: "/scans" },
          { label: `Sign-in scan #${id}`, to: `/scans/${id}/protected` },
          { label: "Issues" },
        ]}
        title="Sign-in scan issues"
        subtitle="Possible problems the automatic checks found, grouped by rule. Page addresses are hidden. An expert needs to confirm each one."
        actions={<LinkButton to={`/scans/${id}/protected`} variant="secondary">Sign-in scan</LinkButton>}
      />

      {(index.isLoading || index.isFetching) && <p aria-live="polite" className="text-sm text-fg-muted">Loading sign-in scan issues…</p>}
      {index.error && (
        <Card className="border-sev-critical/40 bg-sev-critical-bg p-4 text-sm text-sev-critical" role="alert">
          {index.error instanceof Error ? index.error.message : "Axcess could not load the sign-in scan issues. Try again later."}
        </Card>
      )}
      {!index.isFetching && index.data && (
        <>
          <Card className="mb-4 border-umich-blue/30 bg-umich-blue/5 p-4 text-sm text-fg">
            <p>
              Each row is a possible problem that an automatic check found. It does not prove
              that the site passes or fails the Web Content Accessibility Guidelines (WCAG).
              Check each one yourself before you assign a fix. Use the approved account and
              only the approved pages.
            </p>
            <p className="mt-2 text-fg-muted">
              This page leaves out affected page addresses and detailed evidence on purpose.
              {index.data.evidence_available
                ? " This version does not accept or show attachments. Check each issue with the approved account and pages."
                : " The time for keeping detailed results has ended. Only these issue counts remain."}
            </p>
          </Card>
          {index.data.groups.length === 0 ? (
            <Card className="p-5 text-sm text-fg-muted">
              No issues are saved yet. This does not prove that the site is accessible.
              Complete the manual checks. Then review what was checked and what the checks cannot find.
            </Card>
          ) : (
            <Card>
              {paged.pages > 1 && (
                <TableBar pager={<TablePagination label="Sign-in scan issues" noun="issues" {...paged} />} />
              )}
              <TableRegion label="Sign-in scan issues table" paged={paged}>
                <Table caption="Sign-in scan issues, grouped by check and rule">
                  <TableHead>
                    <tr>
                      <ColumnHeader>Check</ColumnHeader>
                      <ColumnHeader>Rule</ColumnHeader>
                      <ColumnHeader>WCAG criterion</ColumnHeader>
                      <ColumnHeader>Result</ColumnHeader>
                      <ColumnHeader>Occurrences</ColumnHeader>
                      <ColumnHeader>Pages</ColumnHeader>
                    </tr>
                  </TableHead>
                  <tbody>
                    {paged.pageRows.map((group, position) => (
                      <IssueRow
                        key={`${group.source_layer}:${group.rule_id}:${group.engine_outcome ?? "lead"}`}
                        group={group}
                        index={(paged.page - 1) * paged.pageSize + position}
                      />
                    ))}
                  </tbody>
                </Table>
              </TableRegion>
            </Card>
          )}
          <p className="mt-4 text-sm text-fg-muted">
            <Link to={`/scans/${id}/protected/manual-checks`} className="text-umich-blue underline underline-offset-2">Record manual WCAG checks</Link>, including WCAG 3.3.8 Accessible Authentication (Minimum) for the sign-in steps.
          </p>
        </>
      )}
    </>
  );
}

function IssueRow({ group, index }: { group: ProtectedIssueIndexGroup; index: number }) {
  const outcome = group.engine_outcome ?? group.impact;
  const result = outcome ? RESULT_LABEL[outcome] ?? outcome.replaceAll("_", " ") : REVIEW_TYPE_LABEL.expert_review;
  return (
    <Row index={index}>
      <Cell className="text-fg">{SOURCE_LABEL[group.source_layer]}</Cell>
      <Cell className="font-mono text-xs text-fg">{group.rule_id}</Cell>
      <Cell className="text-fg">{group.wcag_sc ? `${group.wcag_sc}${group.wcag_level ? ` (Level ${group.wcag_level})` : ""}` : "Does not apply"}</Cell>
      <Cell className="text-fg">{result}</Cell>
      <Cell numeric className="text-fg">{group.occurrence_count.toLocaleString()}</Cell>
      <Cell numeric className="text-fg">{group.page_count.toLocaleString()}</Cell>
    </Row>
  );
}
