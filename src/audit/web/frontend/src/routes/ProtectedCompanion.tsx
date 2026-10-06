/**
 * The protected report's own workspace: pair a companion agent, start and
 * stop the run, and read progress.
 *
 * This is the most secret-handling screen in the app, and most of what looks
 * like ceremony here is that. Three rules explain nearly all of it.
 *
 * 1. Nothing sensitive renders unless the identity it was created under is
 *    still the current one. A pairing code and a certificate fingerprint are
 *    each stored beside the identity fingerprint that produced them, and the
 *    `visible*` values below resolve to nothing when those disagree. A shared
 *    tab whose identity-aware proxy session changes users therefore shows the
 *    new user nothing belonging to the previous one, without waiting for a
 *    refetch to notice.
 *
 * 2. A pairing code is one-time and short-lived. It is cleared when it
 *    expires, and eagerly when the tab is hidden or the page is about to
 *    enter the back/forward cache, using flushSync so the DOM no longer holds
 *    it before the snapshot is taken.
 *
 * 3. Mutation callbacks re-check the identity fingerprint before committing
 *    anything to state. A request begun under one identity must not deliver
 *    its result into a view that now belongs to another; the ref holds the
 *    current value because the callback closes over a stale render.
 *
 * Queries here deliberately opt out of caching (`gcTime: 0`, and refetch on
 * mount) so protected report data is not retained in the client cache after
 * the view is closed.
 */
import { useEffect, useRef, useState } from "react";
import { parseServerTime, serverDate } from "../lib/serverTime";
import { flushSync } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertOctagon,
  CheckCircle2,
  Clock3,
  Download,
  KeyRound,
  LaptopMinimal,
  LockKeyhole,
  Play,
  ShieldCheck,
} from "lucide-react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import {
  Button,
  Card,
  LinkButton,
  PageHeader,
} from "../components/ui";
import ProtectedScanSteps, {
  type ProtectedScanStage,
} from "../components/ProtectedScanSteps";
import {
  protectedMutationKey,
  protectedQueryKey,
  useProtectedIdentityContext,
} from "../hooks/useProtectedIdentityContext";
import { CHECK_LABEL, REVIEW_TYPE_LABEL } from "../lib/terms";
import type {
  ProtectedAgentEnrollmentResponse,
  ProtectedScanStatus,
} from "../api/types";

const STATUS_COPY: Record<
  ProtectedScanStatus,
  { label: string; detail: string; className: string }
> = {
  awaiting_authentication: {
    label: "Waiting for sign-in",
    detail: "To start, create a one-time pairing code and pair the helper app. Then sign in yourself in the browser window it opens.",
    className: "border-umich-blue/40 bg-umich-blue/10 text-umich-blue",
  },
  authentication_required: {
    label: "Sign-in needed",
    detail: "Your last sign-in ended, or the site needs another step from you. Axcess did not try to sign in again for you.",
    className: "border-sev-major/50 bg-sev-major-bg text-sev-major",
  },
  running: {
    label: "Sign-in scan running",
    detail: "The helper app is scanning only the approved pages. Your browser sign-in data (session) stays on that computer.",
    className: "border-umich-blue/40 bg-umich-blue/10 text-umich-blue",
  },
  completed: {
    label: "Sign-in scan complete",
    detail: "Review the report here, behind its access controls, before you share any part of it.",
    className: "border-border bg-surface-muted text-fg-muted",
  },
  failed: {
    label: "Sign-in scan failed",
    detail: "Axcess did not retry or sign in again by itself. Read the failure details in the report. If needed, start a new sign-in that you are allowed to make.",
    className: "border-sev-critical/40 bg-sev-critical-bg text-sev-critical",
  },
  interrupted: {
    label: "Sign-in scan stopped",
    detail: "The sign-in scan stopped before it finished. The helper app did not keep a browser sign-in that could be used again.",
    className: "border-sev-major/50 bg-sev-major-bg text-sev-major",
  },
};

function displayTime(value: string | null): string {
  if (!value) return "Not recorded";
  const date = serverDate(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function ProgressMetric({
  label,
  value,
}: {
  label: string;
  value: number | string;
}) {
  return (
    <div className="rounded-xs border border-border bg-surface-muted p-3">
      <dt className="text-xs font-medium text-fg-muted">{label}</dt>
      <dd className="mt-1 text-xl font-semibold tabular-nums text-fg">
        {typeof value === "number" ? value.toLocaleString() : value}
      </dd>
    </div>
  );
}

/**
 * Report-scoped companion handoff. A pairing code is returned only by the
 * enrollment POST and remains visible solely in this in-memory view until
 * the auditor hides it; the app does not copy it to the clipboard or store
 * it in a URL, export, or report record.
 */
export default function ProtectedCompanionRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const queryClient = useQueryClient();
  const protectedIdentity = useProtectedIdentityContext();
  const identityFingerprint = protectedIdentity.fingerprint;
  const latestIdentityFingerprint = useRef<string | null>(identityFingerprint);
  latestIdentityFingerprint.current = identityFingerprint;
  const alertRef = useRef<HTMLDivElement>(null);
  const [pairing, setPairing] =
    useState<ProtectedAgentEnrollmentResponse | null>(null);
  const [pairingIdentityFingerprint, setPairingIdentityFingerprint] = useState<
    string | null
  >(null);
  const [certificateFingerprint, setCertificateFingerprint] = useState("");
  const [certificateIdentityFingerprint, setCertificateIdentityFingerprint] =
    useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const visiblePairing =
    protectedIdentity.isReady &&
    pairingIdentityFingerprint === identityFingerprint
      ? pairing
      : null;
  const visibleCertificateFingerprint =
    protectedIdentity.isReady &&
    certificateIdentityFingerprint === identityFingerprint
      ? certificateFingerprint
      : "";

  const protectedScan = useQuery({
    queryKey: protectedQueryKey("scan", identityFingerprint, id),
    queryFn: () => api.getProtectedScan(id),
    enabled:
      Number.isSafeInteger(id) && id > 0 && protectedIdentity.isReady,
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
    refetchInterval: (query) => {
      const status = query.state.data?.protection_status;
      return status === "awaiting_authentication" ||
        status === "authentication_required" ||
        status === "running"
        ? 2000
        : false;
    },
  });
  const pairedCompanion = useQuery({
    queryKey: protectedQueryKey("companion", identityFingerprint, id),
    queryFn: () => api.getProtectedCompanion(id),
    enabled:
      Number.isSafeInteger(id) && id > 0 && protectedIdentity.isReady,
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
    // Pairing happens in a separate local terminal. Poll only while this
    // report can still be handed off, so the browser notices when the
    // one-time code has been claimed and clears it from the DOM.
    refetchInterval: () => {
      const status = protectedScan.data?.protection_status;
      return status === "awaiting_authentication" ||
        status === "authentication_required" ||
        status === "interrupted"
        ? 2000
        : false;
    },
  });

  useEffect(() => {
    if (actionError) alertRef.current?.focus();
  }, [actionError]);

  const enroll = useMutation({
    mutationKey: protectedMutationKey("agent-enrollment", identityFingerprint, id),
    mutationFn: () =>
      api.createProtectedAgentEnrollment(id, visibleCertificateFingerprint.trim()),
    // The pairing code must never live in the TanStack mutation cache. Keep
    // it only in the dedicated in-memory state below, long enough to render
    // the one-time handoff card.
    gcTime: 0,
    onSuccess: (result) => {
      if (
        !identityFingerprint ||
        latestIdentityFingerprint.current !== identityFingerprint
      ) {
        return;
      }
      setActionError(null);
      setMessage("Pairing code created. It appears below, only in this browser tab.");
      setPairing(result);
      setPairingIdentityFingerprint(identityFingerprint);
    },
    onError: (error: unknown) =>
      setActionError(error instanceof Error ? error.message : String(error)),
  });

  useEffect(() => {
    if (pairedCompanion.data?.companion && visiblePairing) {
      // Once local mTLS enrollment succeeds, the one-time code has no
      // further use. Remove it from React state and the DOM immediately.
      setPairing(null);
      setPairingIdentityFingerprint(null);
      setCertificateFingerprint("");
      setCertificateIdentityFingerprint(null);
      enroll.reset();
      setMessage(
        "Helper app paired. Whenever you need to sign in again, run the command below again. This command is not secret.",
      );
    }
  }, [
    enroll,
    pairedCompanion.data?.companion,
    visiblePairing,
  ]);

  useEffect(() => {
    if (
      !protectedIdentity.isReady ||
      (pairing !== null && pairingIdentityFingerprint !== identityFingerprint) ||
      (certificateIdentityFingerprint !== null &&
        certificateIdentityFingerprint !== identityFingerprint)
    ) {
      setPairing(null);
      setPairingIdentityFingerprint(null);
      setCertificateFingerprint("");
      setCertificateIdentityFingerprint(null);
      enroll.reset();
    }
  }, [
    enroll,
    certificateIdentityFingerprint,
    identityFingerprint,
    pairing,
    pairingIdentityFingerprint,
    protectedIdentity.isReady,
  ]);

  // `useMutation` returns a fresh result object on every render, so depending
  // on `enroll` re-runs these effects continuously: this screen re-renders on
  // two 2-second polls. `reset` is bound once on the mutation observer and is
  // stable, so depend on the method rather than the object. Without this the
  // expiry timer below was cleared and rebuilt, and the three global
  // listeners further down were removed and re-added, on every render.
  const resetEnroll = enroll.reset;

  useEffect(() => {
    if (visiblePairing) resetEnroll();
  }, [resetEnroll, visiblePairing]);

  useEffect(() => {
    if (!visiblePairing) return undefined;
    const expiresAt = parseServerTime(visiblePairing.expires_at);
    const delay = Number.isFinite(expiresAt) ? Math.max(0, expiresAt - Date.now()) : 0;
    const timeout = window.setTimeout(() => {
      setPairing(null);
      setPairingIdentityFingerprint(null);
      setCertificateFingerprint("");
      setCertificateIdentityFingerprint(null);
      resetEnroll();
      setMessage("The one-time pairing code expired. Axcess removed it from this browser tab.");
    }, delay);
    return () => window.clearTimeout(timeout);
  }, [resetEnroll, visiblePairing]);

  const startCompanion = useMutation({
    mutationKey: protectedMutationKey("companion-start", identityFingerprint, id),
    mutationFn: () => api.startProtectedCompanion(id),
    gcTime: 0,
    onSuccess: (result) => {
      if (latestIdentityFingerprint.current !== identityFingerprint) return;
      setActionError(null);
      setMessage(
        result.protection_status === "running"
          ? "The helper app is already running."
          : "Ready for you to sign in. Run the helper app command on your computer. Axcess never opens the browser from the server.",
      );
      void queryClient.invalidateQueries({
        queryKey: protectedQueryKey("scan", identityFingerprint, id),
      });
      void queryClient.invalidateQueries({
        queryKey: ["scan", id, "identity", identityFingerprint],
      });
    },
    onError: (error: unknown) =>
      setActionError(error instanceof Error ? error.message : String(error)),
  });

  const downloadRedactedExport = useMutation({
    mutationKey: protectedMutationKey("redacted-export", identityFingerprint, id),
    mutationFn: () => api.downloadProtectedRedactedExport(id),
    gcTime: 0,
    onSuccess: () => {
      if (latestIdentityFingerprint.current !== identityFingerprint) return;
      setActionError(null);
      setMessage(
        "Redacted summary downloaded. Axcess did not keep a copy on the server. Handle the file according to its data classification.",
      );
    },
    onError: (error: unknown) =>
      setActionError(error instanceof Error ? error.message : String(error)),
  });
  const stopProtectedScan = useMutation({
    mutationKey: protectedMutationKey("scan-stop", identityFingerprint, id),
    mutationFn: () => api.stopProtectedScan(id),
    gcTime: 0,
    onSuccess: (result) => {
      if (latestIdentityFingerprint.current !== identityFingerprint) return;
      setActionError(null);
      setMessage("Sign-in scan stopped. The helper app can no longer get pages to check or send results.");
      void queryClient.invalidateQueries({
        queryKey: protectedQueryKey("scan", identityFingerprint, id),
      });
      void queryClient.invalidateQueries({
        queryKey: protectedQueryKey("companion", identityFingerprint, id),
      });
      void queryClient.invalidateQueries({
        queryKey: protectedQueryKey("reports", identityFingerprint),
      });
      void queryClient.invalidateQueries({
        queryKey: ["scan", id, "identity", identityFingerprint],
      });
      void result;
    },
    onError: (error: unknown) =>
      setActionError(error instanceof Error ? error.message : String(error)),
  });

  useEffect(() => {
    const clearSensitivePairingState = () => {
      // A pairing code is a one-time secret. Clear it before a page enters
      // BFCache or another person can switch to this tab, even though React
      // state is otherwise only in memory.
      // React batches native browser-event updates. Flush this rare security
      // transition so the secret is removed from the DOM before a pagehide
      // snapshot can be retained in the back/forward cache.
      flushSync(() => {
        setPairing(null);
        setPairingIdentityFingerprint(null);
        setCertificateFingerprint("");
        setCertificateIdentityFingerprint(null);
      });
      resetEnroll();
    };
    const refreshProtectedIdentity = () => {
      void queryClient.invalidateQueries({
        queryKey: protectedQueryKey("identity-context"),
      });
    };
    const onPageHide = () => clearSensitivePairingState();
    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        clearSensitivePairingState();
      } else if (document.visibilityState === "visible") {
        // A visible tab could have returned under a different proxy session.
        // The identity hook gates report content until this revalidation ends.
        refreshProtectedIdentity();
      }
    };
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) {
        clearSensitivePairingState();
        refreshProtectedIdentity();
      }
    };

    window.addEventListener("pagehide", onPageHide);
    window.addEventListener("pageshow", onPageShow);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      window.removeEventListener("pagehide", onPageHide);
      window.removeEventListener("pageshow", onPageShow);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [resetEnroll, queryClient]);

  if (!Number.isSafeInteger(id) || id <= 0) {
    return (
      <>
        <ProtectedCompanionHeader />
        <Card className="border-sev-critical/40 bg-sev-critical-bg p-4 text-sm text-sev-critical" role="alert">
          This sign-in scan number is not valid. Check the address, or open the report from Reports.
        </Card>
      </>
    );
  }
  if (protectedIdentity.isChecking) {
    return (
      <>
        <ProtectedCompanionHeader scanId={id} />
        <p className="text-sm text-fg-muted" aria-live="polite">
          Checking that you can open this sign-in scan…
        </p>
      </>
    );
  }
  if (protectedIdentity.error || !protectedIdentity.isReady) {
    return (
      <>
        <ProtectedCompanionHeader scanId={id} />
        <Card
          className="border-sev-critical/40 bg-sev-critical-bg p-4 text-sm text-sev-critical"
          role="alert"
        >
          {protectedIdentity.error instanceof Error
            ? protectedIdentity.error.message
            : "Axcess could not confirm your access to sign-in scans. Try again, or ask your administrator."}
        </Card>
      </>
    );
  }
  if (protectedScan.isLoading) {
    return (
      <>
        <ProtectedCompanionHeader scanId={id} />
        <p className="text-sm text-fg-muted" aria-live="polite">Loading sign-in scan…</p>
      </>
    );
  }
  if (protectedScan.error || !protectedScan.data) {
    return (
      <>
        <ProtectedCompanionHeader scanId={id} />
        <Card className="border-sev-critical/40 bg-sev-critical-bg p-4 text-sm text-sev-critical" role="alert">
          {protectedScan.error instanceof Error
            ? protectedScan.error.message
            : "Axcess could not load this sign-in scan. Check that you opened it through the protected sign-in scan address."}
        </Card>
      </>
    );
  }

  const scan = protectedScan.data;
  const status = STATUS_COPY[scan.protection_status];
  const mayStart =
    scan.protection_status === "awaiting_authentication" ||
    scan.protection_status === "authentication_required" ||
    scan.protection_status === "interrupted";
  const mayExport =
    scan.protection_status === "completed" && scan.is_evidence_available;
  const mayReviewIndex = scan.protection_status === "completed" || scan.protection_status === "running";
  const claimedCompanion = pairedCompanion.data?.companion ?? null;
  const journeyStage: ProtectedScanStage =
    scan.protection_status === "completed"
      ? "report"
      : scan.protection_status === "running"
        ? "scan"
        : claimedCompanion
          ? "sign_in"
          : "pair";

  return (
    <>
      <ProtectedCompanionHeader scanId={id} />
      <ProtectedScanSteps current={journeyStage} className="mb-5" />

      <Card className="mb-4 border-umich-blue/30 bg-umich-blue/5 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
            <div>
              <h2 className="text-sm font-semibold text-fg">{status.label}</h2>
              <p className="mt-1 max-w-3xl text-sm text-fg-muted">{status.detail}</p>
            </div>
          </div>
          <span
            className={`inline-flex rounded-xs border px-2 py-1 text-2xs font-semibold ${status.className}`}
            aria-label={`Sign-in scan status: ${status.label}`}
          >
            {status.label}
          </span>
        </div>
        {(scan.protection_status === "awaiting_authentication" ||
          scan.protection_status === "authentication_required" ||
          scan.protection_status === "running") && (
          <div className="mt-4 border-t border-border pt-4">
            <Button
              type="button"
              variant="secondary"
              disabled={stopProtectedScan.isPending}
              onClick={() => {
                if (window.confirm("Stop this sign-in scan? The helper app’s certificate will stop working for this report.")) {
                  setActionError(null);
                  setMessage(null);
                  stopProtectedScan.mutate();
                }
              }}
            >
              {stopProtectedScan.isPending ? "Stopping sign-in scan…" : "Stop sign-in scan"}
            </Button>
            <p className="mt-2 text-xs text-fg-muted">Stopping ends the helper app’s access to this scan (its lease). Axcess does not look into or keep the browser sign-in.</p>
          </div>
        )}
      </Card>

      <Card
        className="mb-4 p-4"
        aria-labelledby="protected-scan-progress-title"
        aria-live={scan.protection_status === "running" ? "polite" : undefined}
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 id="protected-scan-progress-title" className="text-sm font-semibold text-fg">
              Sign-in scan progress
            </h2>
            <p className="mt-1 text-xs text-fg-muted">
              The counts update while the helper app runs. Page addresses, element locators (CSS selectors), and page text stay on the computer that runs the helper app.
            </p>
          </div>
          {protectedScan.isFetching && (
            <span className="text-xs text-fg-muted" role="status">
              Refreshing counts…
            </span>
          )}
        </div>
        <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <ProgressMetric label="Pages checked" value={scan.progress.pages_indexed} />
          <ProgressMetric label="Issue occurrences" value={scan.progress.issue_occurrences} />
          <ProgressMetric label={CHECK_LABEL.axe} value={scan.progress.axe_occurrences} />
          <ProgressMetric
            label={`${CHECK_LABEL.alfa}: failed or ${REVIEW_TYPE_LABEL.expert_review}`}
            value={`${scan.progress.alfa_failed_occurrences} / ${scan.progress.alfa_review_occurrences}`}
          />
        </dl>
        {scan.progress.probe_occurrences > 0 && (
          <p className="mt-3 text-xs text-fg-muted">
            The keyboard, focus, and zoom and layout checks found {scan.progress.probe_occurrences.toLocaleString()} more occurrence{scan.progress.probe_occurrences === 1 ? "" : "s"}.
          </p>
        )}
      </Card>

      {(actionError || message) && (
        <Card
          className={`mb-4 p-4 text-sm ${
            actionError
              ? "border-sev-critical/40 bg-sev-critical-bg text-sev-critical"
              : "border-umich-blue/30 bg-umich-blue/5 text-fg"
          }`}
        >
          <div
            ref={actionError ? alertRef : undefined}
            tabIndex={actionError ? -1 : undefined}
            role={actionError ? "alert" : "status"}
            aria-live={actionError ? undefined : "polite"}
            className="flex items-start gap-3 focus:outline-none"
          >
            {actionError ? (
              <AlertOctagon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
            ) : (
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
            )}
            <p>{actionError ?? message}</p>
          </div>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(19rem,0.65fr)]">
        <div className="space-y-4">
          <Card className="p-5">
            <div className="flex items-start gap-3">
              <LaptopMinimal className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
              <div>
                <p className="text-xs font-semibold text-umich-blue">Step 2</p>
                <h2 className="mt-1 text-lg font-semibold text-fg">Connect the helper app on your computer</h2>
                <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-fg-muted">
                  <li>Enter the ID of the helper app’s certificate (SHA-256 fingerprint). This certificate was set up in advance. Then create a one-time pairing code.</li>
                  <li>On the computer that will run the scan, run the pairing command. Type the code only where the helper app asks for it.</li>
                  <li>After pairing works, run the helper app’s scan command. It opens a browser window you can see. Sign in there, directly on the site, with a password or two-step sign-in (2FA).</li>
                  <li>Axcess checks that you reached the approved page after sign-in. Then the helper app starts the scan. The scan only reads pages and does not change them.</li>
                </ol>
                <p className="mt-4 text-sm text-fg">
                  Axcess never asks for any of these:
                </p>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-fg">
                  <li>your password</li>
                  <li>a one-time code (OTP)</li>
                  <li>a phone approval (push approval)</li>
                  <li>a passkey</li>
                  <li>a recovery code</li>
                  <li>your browser profile</li>
                  <li>cookies</li>
                  <li>saved browser data (storage state)</li>
                </ul>
                <p className="mt-2 text-sm text-fg">
                  If your sign-in ends, the scan stops. It asks you to sign in again yourself.
                </p>
              </div>
            </div>

            {claimedCompanion ? (
              <PairedCompanion companion={claimedCompanion} />
            ) : !visiblePairing ? (
              <div className="mt-5 space-y-3">
                <div className="max-w-2xl">
                  <label htmlFor="companion-certificate-fingerprint" className="block text-sm font-semibold text-fg">
                    Helper app certificate ID (SHA-256 fingerprint)
                  </label>
                  <input
                    id="companion-certificate-fingerprint"
                    type="text"
                    value={visibleCertificateFingerprint}
                    onChange={(event) => {
                      setCertificateFingerprint(event.target.value);
                      setCertificateIdentityFingerprint(identityFingerprint);
                    }}
                    autoComplete="off"
                    spellCheck={false}
                    className="mt-1 w-full rounded-xs border border-border bg-surface px-3 py-2 font-mono text-sm text-fg"
                    aria-describedby="companion-certificate-fingerprint-help"
                    placeholder="AA:BB:… or 64 characters, 0–9 and A–F"
                  />
                  <p id="companion-certificate-fingerprint-help" className="mt-1 text-xs text-fg-muted">
                    This ID is public. It ties the pairing code to one managed computer. Axcess never receives the certificate’s private key.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    type="button"
                    variant="primary"
                    disabled={
                      enroll.isPending ||
                      pairedCompanion.isLoading ||
                      !mayStart ||
                      !visibleCertificateFingerprint.trim()
                    }
                    onClick={() => {
                      setActionError(null);
                      setMessage(null);
                      enroll.mutate();
                    }}
                    title={
                      mayStart
                        ? undefined
                        : "You can pair only while the report is waiting for you to sign in."
                    }
                  >
                    <KeyRound className="h-4 w-4" aria-hidden />
                    {enroll.isPending ? "Creating pairing code…" : "Create pairing code"}
                  </Button>
                  {!mayStart && (
                    <span className="text-sm text-fg-muted">
                      You do not need to pair now. Status: {status.label}.
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <PairingCode
                pairing={visiblePairing}
                onHide={() => {
                  // Clear the visible value rather than leaving it in the DOM.
                  setPairing(null);
                  setPairingIdentityFingerprint(null);
                  setCertificateFingerprint("");
                  setCertificateIdentityFingerprint(null);
                  enroll.reset();
                  setMessage("The pairing code is hidden. To pair the helper app, create a new code.");
                }}
              />
            )}
          </Card>

          {mayReviewIndex && (
            <Card className="p-5">
              <div className="flex items-start gap-3">
                <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
                <div>
                  <h2 className="text-base font-semibold text-fg">Issues found by the sign-in scan</h2>
                  <p className="mt-1 text-sm text-fg-muted">
                    See how often each check and rule found a problem. This list does not show page addresses, element locators (CSS selectors), or screenshots.
                  </p>
                </div>
              </div>
              <LinkButton to={`/scans/${id}/protected/issues`} variant="secondary" className="mt-4">
                Open sign-in scan issues
              </LinkButton>
            </Card>
          )}

          <Card className="p-5">
            <div className="flex items-start gap-3">
              <Play className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
              <div className="min-w-0">
                <p className="text-xs font-semibold text-umich-blue">Step 3</p>
                <h2 className="mt-1 text-lg font-semibold text-fg">Open the browser and sign in</h2>
                <p className="mt-1 text-sm text-fg-muted">
                  First, select Prepare sign-in. Then run the helper app command shown above. A Chromium browser window opens. Sign in there with your password, passkey, or two-step sign-in (2FA). Then go back to the terminal and press Enter. Axcess checks the page you reached before it starts scanning.
                </p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button
                type="button"
                variant="primary"
                disabled={startCompanion.isPending || !mayStart || !claimedCompanion}
                onClick={() => {
                  setActionError(null);
                  setMessage(null);
                  startCompanion.mutate();
                }}
              >
                <Play className="h-4 w-4" aria-hidden />
                {startCompanion.isPending ? "Preparing sign-in…" : "Prepare sign-in"}
              </Button>
              {mayStart && !claimedCompanion && (
                <span className="text-sm text-fg-muted">
                  Pair the helper app first. Then run its command on your computer to open the sign-in window.
                </span>
              )}
            </div>
          </Card>

          <Card className="p-5">
            <h2 className="text-base font-semibold text-fg">Approved sites (scope)</h2>
            <p className="mt-1 text-sm text-fg-muted">
              Axcess does not show or keep the exact site addresses (origins) on this page. It sends them only to the helper app, encrypted and tied to this scan. It sends them only after it checks the helper app’s certificate (mTLS).
            </p>
            <ScopeSummary
              label="Sites to scan"
              count={scan.target_origin_count}
              fingerprint={scan.target_scope_fingerprint}
            />
            <ScopeSummary
              label="Sign-in sites"
              count={scan.auth_origin_count}
              fingerprint={scan.auth_scope_fingerprint}
            />
            <ScopeSummary
              label="File and resource sites (CDN)"
              count={scan.cdn_origin_count}
              fingerprint={scan.cdn_scope_fingerprint}
            />
            <p className="mt-4 text-xs text-fg-muted">
              Site owner: <strong className="text-fg">{scan.target_owner}</strong> · Requested by (verified): <strong className="text-fg">{scan.authorized_by}</strong> · {scan.environment} · {scan.data_classification}
            </p>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="p-5">
            <div className="flex items-start gap-3">
              <Clock3 className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
              <div>
                <h2 className="text-base font-semibold text-fg">How long results are kept</h2>
                <p className="mt-1 text-sm text-fg-muted">
                  Axcess encrypts the detailed results. It deletes them automatically after a set time. A basic record of the scan stays. That record has no sensitive details.
                </p>
              </div>
            </div>
            <dl className="mt-4 space-y-3 text-sm">
              <div>
                <dt className="font-medium text-fg">Scheduled deletion</dt>
                <dd className="text-fg-muted" title={scan.cleanup_at}>{displayTime(scan.cleanup_at)}</dd>
              </div>
              <div>
                <dt className="font-medium text-fg">Detailed results and attachments</dt>
                <dd className="text-fg-muted">
                  {scan.is_evidence_available
                    ? "Not kept or shown in this version"
                    : "The time for keeping them has ended. Only the issue counts remain."}
                </dd>
              </div>
              {scan.evidence_purged_at && (
                <div>
                  <dt className="font-medium text-fg">Detailed results deleted</dt>
                  <dd className="text-fg-muted" title={scan.evidence_purged_at}>{displayTime(scan.evidence_purged_at)}</dd>
                </div>
              )}
              {scan.key_destroyed_at && (
                <div>
                  <dt className="font-medium text-fg">Encryption key deleted</dt>
                  <dd className="text-fg-muted" title={scan.key_destroyed_at}>{displayTime(scan.key_destroyed_at)}</dd>
                </div>
              )}
            </dl>
          </Card>

          <Card className="border-sev-major/40 bg-sev-major-bg/30 p-5">
            <div className="flex items-start gap-3">
              <LockKeyhole className="mt-0.5 h-5 w-5 shrink-0 text-sev-major" aria-hidden />
              <div>
                <h2 className="text-base font-semibold text-fg">Limits on sign-in scan data</h2>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-fg-muted">
                  <li>These are turned off: automatic messages to other services (webhooks), AI on other servers, report chat (MCP), and exports with all details.</li>
                  <li>AI on this computer (local AI) is {scan.allow_local_ai ? "approved only for limited image checks that stay in memory" : "turned off for this report"}.</li>
                  <li>In this version, you cannot upload files from the helper app or attach files to a review.</li>
                  <li>The helper app blocks requests that change data, downloads, pop-ups, background scripts (workers), and sites that are not approved.</li>
                </ul>
              </div>
            </div>
          </Card>

          <Card className="p-5">
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
              <div>
                <h2 className="text-base font-semibold text-fg">Check the sign-in steps yourself</h2>
                <p className="mt-1 text-sm text-fg-muted">
                  Signing in lets the helper app scan. It does not prove that the sign-in steps meet the Web Content Accessibility Guidelines (WCAG). Check them against WCAG 3.3.8 Accessible Authentication (Minimum), Level AA, from WCAG 2.2. Record a result only after you review each sign-in step in scope.
                </p>
              </div>
            </div>
            <LinkButton to={`/scans/${id}/protected/manual-checks`} variant="secondary" className="mt-4">
              Record manual check results
            </LinkButton>
          </Card>

          <Card className="p-5">
            <div className="flex items-start gap-3">
              <Download className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
              <div>
                <h2 className="text-base font-semibold text-fg">Download a redacted summary</h2>
                <p className="mt-1 text-sm text-fg-muted">
                  You can download a short Markdown summary after the report is complete. Axcess removes private details from it (redacts it). The summary leaves out site URLs, page locations, element locators (CSS selectors), and screenshots. It also leaves out text read from images (OCR) and all browser and sign-in data. This version has no attachment uploads in the app.
                </p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button
                type="button"
                variant="secondary"
                disabled={downloadRedactedExport.isPending || !mayExport}
                onClick={() => {
                  setActionError(null);
                  setMessage(null);
                  downloadRedactedExport.mutate();
                }}
                title={
                  mayExport
                    ? undefined
                    : scan.is_evidence_available
                      ? "You can download the redacted summary after the sign-in scan is complete."
                      : "Axcess deleted the detailed results, so it cannot make a new summary."
                }
              >
                <Download className="h-4 w-4" aria-hidden />
                {downloadRedactedExport.isPending
                  ? "Preparing redacted summary…"
                  : "Download redacted summary"}
              </Button>
              {!mayExport && (
                <span className="text-sm text-fg-muted">
                  {scan.is_evidence_available
                    ? "Available after the sign-in scan is complete."
                    : "No longer available. Axcess deleted the detailed results."}
                </span>
              )}
            </div>
            <p className="mt-3 text-xs text-fg-muted">
              You start this download yourself. Axcess records that you downloaded the summary. It does not save the file, or a temporary copy, on the server. The person who has a downloaded copy is responsible for it.
            </p>
          </Card>

          <p className="px-1 text-xs text-fg-muted">
            To see the whole report, go back to the <Link to={`/scans/${id}`} className="text-umich-blue underline underline-offset-2">report overview</Link>. Never put a pairing code in tickets, chat, exports, or screen recordings.
          </p>
        </div>
      </div>
    </>
  );
}

function ProtectedCompanionHeader({ scanId }: { scanId?: number }) {
  return (
    <PageHeader
      crumbs={[
        { label: "Reports", to: "/scans" },
        ...(scanId ? [{ label: `Report #${scanId}`, to: `/scans/${scanId}` }] : []),
        { label: "Sign-in scan" },
      ]}
      title="Sign-in scan"
      subtitle={
        scanId
          ? `Sign in yourself, then the helper app checks the pages for Report #${scanId}. The scan only reads pages.`
          : "Sign in yourself, then the helper app checks the pages. The scan only reads pages."
      }
      actions={
        scanId ? (
          <LinkButton to={`/scans/${scanId}`} variant="secondary">
            Report overview
          </LinkButton>
        ) : undefined
      }
    />
  );
}

function PairingCode({
  pairing,
  onHide,
}: {
  pairing: ProtectedAgentEnrollmentResponse;
  onHide: () => void;
}) {
  return (
    <section
      className="mt-5 rounded-xs border-2 border-umich-blue/40 bg-surface-muted p-4"
      aria-labelledby="pairing-code-heading"
    >
      <h3 id="pairing-code-heading" className="text-sm font-semibold text-fg">
        One-time pairing code, shown once
      </h3>
      <p className="mt-1 text-sm text-fg-muted">
        Type this code only where the helper app asks for it. Axcess does not copy it to your clipboard. After you hide this section, Axcess cannot show it again.
      </p>
      <dl className="mt-4 space-y-3">
        <div>
          <dt className="text-xs font-semibold text-fg-subtle">Pairing code</dt>
          <dd>
            <code className="mt-1 block break-all rounded-xs border border-border bg-surface px-3 py-2 text-base font-semibold text-fg">
              {pairing.pairing_code}
            </code>
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold text-fg-subtle">Expires</dt>
          <dd className="mt-1 text-sm text-fg-muted" title={pairing.expires_at}>{displayTime(pairing.expires_at)}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold text-fg-subtle">Helper app command (to pair)</dt>
          <dd>
            <code className="mt-1 block overflow-x-auto rounded-xs border border-border bg-surface px-3 py-2 text-xs text-fg">
              {pairing.companion_command}
            </code>
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold text-fg-subtle">Then run this to scan</dt>
          <dd>
            <code className="mt-1 block overflow-x-auto rounded-xs border border-border bg-surface px-3 py-2 text-xs text-fg">
              {pairing.companion_run_command}
            </code>
          </dd>
        </div>
      </dl>
      <Button type="button" className="mt-4" onClick={onHide}>
        I entered it, hide pairing code
      </Button>
    </section>
  );
}

function PairedCompanion({
  companion,
}: {
  companion: {
    enrollment_id: string;
    status: "claimed";
    companion_run_command: string;
  };
}) {
  return (
    <section
      className="mt-5 rounded-xs border border-umich-blue/40 bg-umich-blue/5 p-4"
      aria-labelledby="paired-companion-heading"
    >
      <h3 id="paired-companion-heading" className="text-sm font-semibold text-fg">
        Helper app paired
      </h3>
      <p className="mt-1 text-sm text-fg-muted">
        This report works with one helper app certificate only. If your
        sign-in ends, run the same command to sign in again. You do not need a
        new pairing code, and you cannot get one.
      </p>
      <dl className="mt-4 space-y-3">
        <div>
          <dt className="text-xs font-semibold text-fg-subtle">
            Pairing ID (enrollment ID)
          </dt>
          <dd className="mt-1">
            <code className="block break-all rounded-xs border border-border bg-surface px-3 py-2 text-xs text-fg">
              {companion.enrollment_id}
            </code>
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold text-fg-subtle">
            Run again on the paired computer
          </dt>
          <dd className="mt-1">
            <code className="block overflow-x-auto rounded-xs border border-border bg-surface px-3 py-2 text-xs text-fg">
              {companion.companion_run_command}
            </code>
          </dd>
        </div>
      </dl>
    </section>
  );
}

function ScopeSummary({
  label,
  count,
  fingerprint,
}: {
  label: string;
  count: number;
  fingerprint: string | null;
}) {
  return (
    <section className="mt-4" aria-label={label}>
      <h3 className="text-sm font-medium text-fg">{label}</h3>
      <p className="mt-1 text-sm text-fg-muted">
        {count === 0 ? "None approved" : `${count} exact site ${count === 1 ? "address" : "addresses"} approved`}
      </p>
      <p className="mt-1 text-xs text-fg-subtle">
        Scope tag: <code>{fingerprint ?? "Not shown for older scans"}</code>
      </p>
    </section>
  );
}
