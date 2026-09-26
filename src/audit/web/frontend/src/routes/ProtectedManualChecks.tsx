import { useEffect, useId, useState } from "react";
import { serverDate } from "../lib/serverTime";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck, LockKeyhole, ShieldCheck } from "lucide-react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import { Button, Card, LinkButton, PageHeader, Select } from "../components/ui";
import {
  protectedMutationKey,
  protectedQueryKey,
  useProtectedIdentityContext,
} from "../hooks/useProtectedIdentityContext";
import type { ManualOutcome, ProtectedManualCheck } from "../api/types";

const OUTCOME_LABELS: Record<ManualOutcome, string> = {
  not_started: "Not started",
  pass: "Pass",
  fail: "Fail",
  not_tested: "Not tested",
  needs_follow_up: "Needs follow-up",
};

/**
 * Manual WCAG review for a protected report.
 *
 * This is intentionally not the public-report ManualChecks route. It keeps
 * only a bounded outcome in the ordinary index: no rationale, page URL,
 * selector, evidence note, or authentication/session detail can enter this
 * flow.
 */
export default function ProtectedManualChecksRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const validId = Number.isSafeInteger(id) && id > 0;
  const protectedIdentity = useProtectedIdentityContext();
  const protectedScan = useQuery({
    queryKey: protectedQueryKey("scan", protectedIdentity.fingerprint, id),
    queryFn: () => api.getProtectedScan(id),
    enabled: validId && protectedIdentity.isReady,
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
  });
  const manualChecks = useQuery({
    queryKey: protectedQueryKey(
      "manual-checks",
      protectedIdentity.fingerprint,
      id,
    ),
    queryFn: () => api.getProtectedManualChecks(id),
    enabled: validId && protectedIdentity.isReady,
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
  });

  if (!validId) {
    return (
      <Card className="border-sev-critical/40 bg-sev-critical-bg p-4 text-sm text-sev-critical" role="alert">
        This sign-in scan number is not valid. Check the address, or open the report from Reports.
      </Card>
    );
  }
  if (protectedIdentity.isChecking) {
    return (
      <p className="text-sm text-fg-muted" aria-live="polite">
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
  if (
    protectedScan.isLoading ||
    protectedScan.isFetching ||
    manualChecks.isLoading ||
    manualChecks.isFetching
  ) {
    return <p className="text-sm text-fg-muted" aria-live="polite">Loading manual checks…</p>;
  }
  if (protectedScan.error || manualChecks.error || !protectedScan.data || !manualChecks.data) {
    const error = protectedScan.error ?? manualChecks.error;
    return (
      <Card className="border-sev-critical/40 bg-sev-critical-bg p-4 text-sm text-sev-critical" role="alert">
        {error instanceof Error
          ? error.message
          : "Axcess could not load the manual checks. Check that you have access to sign-in scans."}
      </Card>
    );
  }

  // Keep Accessible Authentication first. The remaining matrix is still
  // available, but this explicit cue prevents a successful session handoff
  // from being mistaken for a result on SC 3.3.8.
  const checks = [...manualChecks.data.checks].sort((left, right) => {
    if (left.criterion.sc === "3.3.8") return -1;
    if (right.criterion.sc === "3.3.8") return 1;
    return left.criterion.sc.localeCompare(right.criterion.sc, undefined, { numeric: true });
  });

  return (
    <>
      <PageHeader
        crumbs={[
          { label: "Reports", to: "/scans" },
          { label: `Sign-in scan #${id}`, to: `/scans/${id}/protected` },
          { label: "Manual checks" },
        ]}
        title="Manual checks for the sign-in scan"
        subtitle="Record only a result, such as Pass or Fail, for each Web Content Accessibility Guidelines (WCAG) criterion."
        actions={
          <LinkButton to={`/scans/${id}/protected`} variant="secondary">
            Sign-in scan
          </LinkButton>
        }
      />

      <Card className="mb-5 border-umich-blue/30 bg-umich-blue/5 p-4">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
          <div>
            <h2 className="text-base font-semibold text-fg">Check the sign-in steps yourself</h2>
            <p className="mt-1 max-w-4xl text-sm text-fg-muted">
              The helper app can scan after you sign in, with or without two-step sign-in (2FA). That only shows that a short-lived browser sign-in worked. It does not test or pass WCAG 3.3.8 Accessible Authentication (Minimum), Level AA, in WCAG 2.2.
            </p>
          </div>
        </div>
      </Card>

      <Card className="mb-5 border-sev-major/40 bg-sev-major-bg/30 p-4">
        <div className="flex items-start gap-3">
          <LockKeyhole className="mt-0.5 h-5 w-5 shrink-0 text-sev-major" aria-hidden />
          <div>
            <h2 className="text-base font-semibold text-fg">Do not enter private details here</h2>
            <p className="mt-1 max-w-4xl text-sm text-fg-muted">
              This form saves only a result from a fixed list. Do not enter passwords, one-time codes (OTPs), passkeys, recovery codes, or cookies. Do not enter URLs, user information, screenshots, element locators (CSS selectors), or detailed notes. This version does not accept attachments. If you need to keep evidence, use the separately approved University of Michigan (U-M) evidence process.
            </p>
          </div>
        </div>
      </Card>

      <section aria-labelledby="protected-checks-heading">
        <div className="mb-3 flex items-start gap-2">
          <ClipboardCheck className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
          <div>
            <h2 id="protected-checks-heading" className="text-base font-semibold text-fg">Results for WCAG 2.2, Level A and AA</h2>
            <p className="mt-1 text-sm text-fg-muted">
              “Not tested” and “Needs follow-up” are honest results. Choose “Pass” only after you do the manual review for that criterion.
            </p>
          </div>
        </div>
        <div className="space-y-3">
          {checks.map((check) => (
            <ProtectedManualCheckCard
              key={check.criterion.sc}
              scanId={id}
              check={check}
              identityFingerprint={protectedIdentity.fingerprint ?? "unverified"}
            />
          ))}
        </div>
      </section>

      <p className="mt-5 text-xs text-fg-muted">
        To sign in again, or to see how long results are kept, go back to the <Link to={`/scans/${id}/protected`} className="text-umich-blue underline underline-offset-2">sign-in scan</Link>.
      </p>
    </>
  );
}

function ProtectedManualCheckCard({
  scanId,
  check,
  identityFingerprint,
}: {
  scanId: number;
  check: ProtectedManualCheck;
  identityFingerprint: string;
}) {
  const queryClient = useQueryClient();
  const selectId = useId();
  const statusId = useId();
  const [outcome, setOutcome] = useState<ManualOutcome>(check.outcome);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setOutcome(check.outcome);
  }, [check.outcome]);

  const save = useMutation({
    mutationKey: protectedMutationKey(
      "manual-check-update",
      identityFingerprint,
      scanId,
      check.criterion.sc,
    ),
    mutationFn: () =>
      api.updateProtectedManualCheck(scanId, check.criterion.sc, { outcome }),
    gcTime: 0,
    onSuccess: () => {
      setError(null);
      setMessage(`WCAG ${check.criterion.sc} saved as ${OUTCOME_LABELS[outcome]}.`);
      void queryClient.invalidateQueries({
        queryKey: protectedQueryKey(
          "manual-checks",
          identityFingerprint,
          scanId,
        ),
      });
    },
    onError: (saveError: unknown) => {
      setMessage(null);
      setError(saveError instanceof Error ? saveError.message : String(saveError));
    },
  });

  const isAuthenticationCheck = check.criterion.sc === "3.3.8";
  return (
    <Card
      className={isAuthenticationCheck ? "border-umich-blue/50 p-4" : "p-4"}
      aria-labelledby={`${selectId}-heading`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id={`${selectId}-heading`} className="font-semibold text-fg">
            WCAG {check.criterion.sc} {check.criterion.name}
          </h3>
          <p className="mt-1 max-w-4xl text-sm text-fg-muted">{check.criterion.manual_check}</p>
        </div>
        <span className="rounded-xs bg-surface-muted px-2 py-1 text-xs font-semibold text-fg-muted">
          {check.criterion.level} · {check.criterion.method}
        </span>
      </div>

      {isAuthenticationCheck && (
        <p className="mt-3 rounded-xs border border-umich-blue/30 bg-umich-blue/5 p-3 text-sm text-fg">
          Signing in with two-step sign-in (2FA) for the scan does not test this criterion. Before you choose a result, review each sign-in step in scope yourself. Also review its accessible alternatives.
        </p>
      )}

      <form
        className="mt-4 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          setMessage(null);
          setError(null);
          save.mutate();
        }}
      >
        <Select
          stacked
          className="min-w-52 flex-1"
          id={selectId}
          label="Result"
          value={outcome}
          onChange={(next) => setOutcome(next as ManualOutcome)}
          aria-describedby={statusId}
          options={Object.entries(OUTCOME_LABELS).map(([value, label]) => ({
            value,
            label,
          }))}
        />
        <Button type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save result"}
        </Button>
      </form>

      <div id={statusId} className="mt-3 text-sm" aria-live="polite">
        {error ? (
          <p className="text-sev-critical" role="alert">Could not save this result: {error}</p>
        ) : message ? (
          <p className="text-fg-muted">{message}</p>
        ) : (
          <p className="text-fg-muted">
            {check.tested_at ? `Last saved ${displayTime(check.tested_at)}.` : "No result saved yet."}
          </p>
        )}
      </div>
    </Card>
  );
}

function displayTime(value: string): string {
  const date = serverDate(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
