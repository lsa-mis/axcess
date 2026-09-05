import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import { Card, LinkButton, PageHeader } from "../components/ui";
import {
  protectedQueryKey,
  useProtectedIdentityContext,
} from "../hooks/useProtectedIdentityContext";
import type { ProtectedIssueIndexGroup } from "../api/types";

const SOURCE_LABEL: Record<ProtectedIssueIndexGroup["source_layer"], string> = {
  axe: "axe-core",
  alfa: "Alfa",
  keyboard: "Keyboard probe",
  responsive: "Responsive probe",
  focus: "Focus probe",
  protected_image: "In-memory image lead",
  unavailable: "Unavailable source",
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

  if (!Number.isSafeInteger(id) || id <= 0) {
    return <p role="alert" className="text-sm text-sev-critical">This protected report identifier is invalid.</p>;
  }
  if (protectedIdentity.isChecking) {
    return (
      <p aria-live="polite" className="text-sm text-fg-muted">
        Checking protected-report access…
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
          : "Protected-report access is unavailable."}
      </Card>
    );
  }

  return (
    <>
      <PageHeader
        crumbs={[
          { label: "Reports", to: "/scans" },
          { label: `Protected report #${id}`, to: `/scans/${id}/protected` },
          { label: "Issue index" },
        ]}
        title="Protected issue index"
        subtitle="Grouped, page-anonymous automated leads for expert verification."
        actions={<LinkButton to={`/scans/${id}/protected`} variant="secondary">Protected overview</LinkButton>}
      />

      {(index.isLoading || index.isFetching) && <p aria-live="polite" className="text-sm text-fg-muted">Loading protected issue index…</p>}
      {index.error && (
        <Card className="border-sev-critical/40 bg-sev-critical-bg p-4 text-sm text-sev-critical" role="alert">
          {index.error instanceof Error ? index.error.message : "The protected issue index is unavailable."}
        </Card>
      )}
      {!index.isFetching && index.data && (
        <>
          <Card className="mb-4 border-umich-blue/30 bg-umich-blue/5 p-4 text-sm text-fg">
            <p>
              Every row is an automated lead, not a conformance verdict. Verify manually with the
              authorized account and approved scope before assigning remediation work.
            </p>
            <p className="mt-2 text-fg-muted">
              This protected view intentionally omits affected-page locations and detailed evidence.
              {index.data.evidence_available
                ? " This v1 workflow does not accept or display attachments; verify with the authorized account and approved scope."
                : " The retention period has ended, so only the aggregate issue index remains."}
            </p>
          </Card>
          {index.data.groups.length === 0 ? (
            <Card className="p-5 text-sm text-fg-muted">
              No protected issue-index rows have been retained yet. This does not prove accessibility;
              complete the manual checks and confirm coverage/limitations.
            </Card>
          ) : (
            <Card className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <caption className="sr-only">Protected grouped automated issue leads</caption>
                <thead className="bg-surface-muted text-2xs uppercase tracking-wide text-fg-subtle">
                  <tr>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">Source layer</th>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">Rule</th>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">WCAG</th>
                    <th scope="col" className="px-4 py-2 text-left font-semibold">Result</th>
                    <th scope="col" className="px-4 py-2 text-right font-semibold">Occurrences</th>
                    <th scope="col" className="px-4 py-2 text-right font-semibold">Indexed pages</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {index.data.groups.map((group) => <IssueRow key={`${group.source_layer}:${group.rule_id}:${group.engine_outcome ?? "lead"}`} group={group} />)}
                </tbody>
              </table>
            </Card>
          )}
          <p className="mt-4 text-sm text-fg-muted">
            <Link to={`/scans/${id}/protected/manual-checks`} className="text-umich-blue underline underline-offset-2">Document manual WCAG checks</Link>, including SC 3.3.8 for the authentication flow.
          </p>
        </>
      )}
    </>
  );
}

function IssueRow({ group }: { group: ProtectedIssueIndexGroup }) {
  const result = group.engine_outcome ?? group.impact ?? "Review lead";
  return (
    <tr className="transition-colors hover:bg-surface-muted/60">
      <td className="px-4 py-3 text-fg">{SOURCE_LABEL[group.source_layer]}</td>
      <td className="px-4 py-3 font-mono text-xs text-fg">{group.rule_id}</td>
      <td className="px-4 py-3 text-fg">{group.wcag_sc ? `${group.wcag_sc} ${group.wcag_level ?? ""}`.trim() : "n/a"}</td>
      <td className="px-4 py-3 text-fg">{result.replaceAll("_", " ")}</td>
      <td className="px-4 py-3 text-right tabular-nums text-fg">{group.occurrence_count.toLocaleString()}</td>
      <td className="px-4 py-3 text-right tabular-nums text-fg">{group.page_count.toLocaleString()}</td>
    </tr>
  );
}
