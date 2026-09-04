import { useEffect, useRef, useState } from "react";
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
import type {
  ProtectedAgentEnrollmentResponse,
  ProtectedScanStatus,
} from "../api/types";

const STATUS_COPY: Record<
  ProtectedScanStatus,
  { label: string; detail: string; className: string }
> = {
  awaiting_authentication: {
    label: "Awaiting authentication",
    detail: "Create a one-time pairing code, pair the local companion, then start the visible sign-in step.",
    className: "border-umich-blue/40 bg-umich-blue/10 text-umich-blue",
  },
  authentication_required: {
    label: "Authentication required",
    detail: "The prior session expired or needs an additional manual step. Axcess did not attempt to re-authenticate for you.",
    className: "border-sev-major/50 bg-sev-major-bg text-sev-major",
  },
  running: {
    label: "Protected crawl running",
    detail: "The paired companion is scanning only the approved scope. Browser session material remains on that computer.",
    className: "border-umich-blue/40 bg-umich-blue/10 text-umich-blue",
  },
  completed: {
    label: "Protected crawl completed",
    detail: "Review the report through the protected access controls before sharing any output.",
    className: "border-border bg-surface-muted text-fg-muted",
  },
  failed: {
    label: "Protected crawl failed",
    detail: "No automatic recovery or re-authentication occurred. Review the visible failure details in the report and begin a new authorized session if needed.",
    className: "border-sev-critical/40 bg-sev-critical-bg text-sev-critical",
  },
  interrupted: {
    label: "Protected crawl interrupted",
    detail: "The protected crawl stopped before completion. The companion did not keep a reusable browser session.",
    className: "border-sev-major/50 bg-sev-major-bg text-sev-major",
  },
};

function displayTime(value: string | null): string {
  if (!value) return "Not recorded";
  const date = new Date(value);
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
      setMessage("Pairing code generated. It is shown below only in this browser view.");
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
        "Companion paired. Re-run the non-secret local command below whenever manual re-authentication is required.",
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

  useEffect(() => {
    if (visiblePairing) enroll.reset();
  }, [enroll, visiblePairing]);

  useEffect(() => {
    if (!visiblePairing) return undefined;
    const expiresAt = Date.parse(visiblePairing.expires_at);
    const delay = Number.isFinite(expiresAt) ? Math.max(0, expiresAt - Date.now()) : 0;
    const timeout = window.setTimeout(() => {
      setPairing(null);
      setPairingIdentityFingerprint(null);
      setCertificateFingerprint("");
      setCertificateIdentityFingerprint(null);
      enroll.reset();
      setMessage("The one-time pairing code expired and was cleared from this browser view.");
    }, delay);
    return () => window.clearTimeout(timeout);
  }, [enroll, visiblePairing]);

  const startCompanion = useMutation({
    mutationKey: protectedMutationKey("companion-start", identityFingerprint, id),
    mutationFn: () => api.startProtectedCompanion(id),
    gcTime: 0,
    onSuccess: (result) => {
      if (latestIdentityFingerprint.current !== identityFingerprint) return;
      setActionError(null);
      setMessage(
        result.protection_status === "running"
          ? "The protected companion is already running."
          : "Manual companion handoff recorded. Run the local companion command; the browser is never started remotely.",
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
        "Redacted protected summary downloaded. Axcess did not keep a server-side copy; handle the downloaded file according to its classification.",
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
      setMessage("Protected run stopped. The paired companion can no longer retrieve work or submit evidence.");
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
      enroll.reset();
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
  }, [enroll, queryClient]);

  if (!Number.isSafeInteger(id) || id <= 0) {
    return (
      <>
        <ProtectedCompanionHeader />
        <Card className="border-sev-critical/40 bg-sev-critical-bg p-4 text-sm text-sev-critical" role="alert">
          This protected scan identifier is invalid.
        </Card>
      </>
    );
  }
  if (protectedIdentity.isChecking) {
    return (
      <>
        <ProtectedCompanionHeader scanId={id} />
        <p className="text-sm text-fg-muted" aria-live="polite">
          Checking protected-report access…
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
            : "Protected-report access is unavailable."}
        </Card>
      </>
    );
  }
  if (protectedScan.isLoading) {
    return (
      <>
        <ProtectedCompanionHeader scanId={id} />
        <p className="text-sm text-fg-muted" aria-live="polite">Loading protected scan…</p>
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
            : "Protected scan details are unavailable. Confirm that you are using the protected report access path."}
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
            className={`inline-flex rounded-xs border px-2 py-1 text-2xs font-semibold uppercase tracking-wide ${status.className}`}
            aria-label={`Protected scan status: ${status.label}`}
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
                if (window.confirm("Stop this protected companion run? The paired companion certificate will be revoked for this report.")) {
                  setActionError(null);
                  setMessage(null);
                  stopProtectedScan.mutate();
                }
              }}
            >
              {stopProtectedScan.isPending ? "Stopping protected run…" : "Stop protected run"}
            </Button>
            <p className="mt-2 text-xs text-fg-muted">Stopping invalidates the active companion lease; it does not remotely inspect or retain the browser session.</p>
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
              Protected scan progress
            </h2>
            <p className="mt-1 text-xs text-fg-muted">
              Counts update while the companion runs. Protected page addresses, selectors, and page text stay on the auditor’s computer.
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
          <ProgressMetric label="axe-core" value={scan.progress.axe_occurrences} />
          <ProgressMetric
            label="Alfa failures / review"
            value={`${scan.progress.alfa_failed_occurrences} / ${scan.progress.alfa_review_occurrences}`}
          />
        </dl>
        {scan.progress.probe_occurrences > 0 && (
          <p className="mt-3 text-xs text-fg-muted">
            Browser interaction probes recorded {scan.progress.probe_occurrences.toLocaleString()} additional occurrence{scan.progress.probe_occurrences === 1 ? "" : "s"}.
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
                <p className="text-xs font-semibold uppercase tracking-wide text-umich-blue">Step 2</p>
                <h2 className="mt-1 text-lg font-semibold text-fg">Connect the secure browser on this computer</h2>
                <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-fg-muted">
                  <li>Enter the SHA-256 fingerprint of the pre-provisioned companion certificate, then generate a one-time pairing code.</li>
                  <li>On the auditor’s computer, run the pairing command and enter the code only in the local companion prompt.</li>
                  <li>After pairing succeeds, run the companion crawl command. It opens a headed browser, where you complete 1FA or MFA directly with the target.</li>
                  <li>After the approved post-login page is verified, the companion can begin the read-only crawl.</li>
                </ol>
                <p className="mt-4 text-sm text-fg">
                  Axcess never requests a password, OTP, push approval, passkey, recovery code, browser profile, cookie, or storage state. If the session expires, it stops and asks for another manual sign-in.
                </p>
              </div>
            </div>

            {claimedCompanion ? (
              <PairedCompanion companion={claimedCompanion} />
            ) : !visiblePairing ? (
              <div className="mt-5 space-y-3">
                <div className="max-w-2xl">
                  <label htmlFor="companion-certificate-fingerprint" className="block text-sm font-semibold text-fg">
                    Companion certificate SHA-256 fingerprint
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
                    placeholder="AA:BB:… or 64 hexadecimal characters"
                  />
                  <p id="companion-certificate-fingerprint-help" className="mt-1 text-xs text-fg-muted">
                    This public certificate fingerprint binds the pairing code to one managed computer. Axcess never receives the certificate private key.
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
                        : "Pairing is available only while the report needs manual authentication."
                    }
                  >
                    <KeyRound className="h-4 w-4" aria-hidden />
                    {enroll.isPending ? "Generating pairing code…" : "Generate pairing code"}
                  </Button>
                  {!mayStart && (
                    <span className="text-sm text-fg-muted">
                      Pairing is not needed while this protected scan is {status.label.toLowerCase()}.
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
                  setMessage("The pairing code is hidden. Generate a new code if you still need to pair a companion.");
                }}
              />
            )}
          </Card>

          {mayReviewIndex && (
            <Card className="p-5">
              <div className="flex items-start gap-3">
                <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
                <div>
                  <h2 className="text-base font-semibold text-fg">Protected review queue</h2>
                  <p className="mt-1 text-sm text-fg-muted">
                    Review grouped source/rule counts without exposing page locations, selectors, or screenshots.
                  </p>
                </div>
              </div>
              <LinkButton to={`/scans/${id}/protected/issues`} variant="secondary" className="mt-4">
                Open protected issue index
              </LinkButton>
            </Card>
          )}

          <Card className="p-5">
            <div className="flex items-start gap-3">
              <Play className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wide text-umich-blue">Step 3</p>
                <h2 className="mt-1 text-lg font-semibold text-fg">Open the browser and sign in</h2>
                <p className="mt-1 text-sm text-fg-muted">
                  Record the handoff, then run the local companion command shown above. Chromium opens visibly; complete password, passkey, or 2FA there, return to the terminal, and press Enter. Axcess verifies the resulting application page before scanning.
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
                {startCompanion.isPending ? "Preparing sign-in…" : "Prepare visible sign-in"}
              </Button>
              {mayStart && !claimedCompanion && (
                <span className="text-sm text-fg-muted">
                  Pair the companion first. Then run its local command to begin the visible sign-in.
                </span>
              )}
            </div>
          </Card>

          <Card className="p-5">
            <h2 className="text-base font-semibold text-fg">Approved scope commitment</h2>
            <p className="mt-1 text-sm text-fg-muted">
              Exact origins are released only in the encrypted, scan-bound companion work item after mTLS verification. They are not retained or displayed in this report workspace.
            </p>
            <ScopeSummary
              label="Target origins"
              count={scan.target_origin_count}
              fingerprint={scan.target_scope_fingerprint}
            />
            <ScopeSummary
              label="Manual sign-in origins"
              count={scan.auth_origin_count}
              fingerprint={scan.auth_scope_fingerprint}
            />
            <ScopeSummary
              label="Resource / CDN origins"
              count={scan.cdn_origin_count}
              fingerprint={scan.cdn_scope_fingerprint}
            />
            <p className="mt-4 text-xs text-fg-muted">
              Owner: <strong className="text-fg">{scan.target_owner}</strong> · Verified requester: <strong className="text-fg">{scan.authorized_by}</strong> · {scan.environment} · {scan.data_classification}
            </p>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="p-5">
            <div className="flex items-start gap-3">
              <Clock3 className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
              <div>
                <h2 className="text-base font-semibold text-fg">Evidence retention</h2>
                <p className="mt-1 text-sm text-fg-muted">
                  Detailed protected evidence is encrypted and automatically removed after its retention window. The scan’s non-sensitive audit record remains.
                </p>
              </div>
            </div>
            <dl className="mt-4 space-y-3 text-sm">
              <div>
                <dt className="font-medium text-fg">Scheduled cleanup</dt>
                <dd className="text-fg-muted" title={scan.cleanup_at}>{displayTime(scan.cleanup_at)}</dd>
              </div>
              <div>
                <dt className="font-medium text-fg">Detailed evidence and attachments</dt>
                <dd className="text-fg-muted">
                  {scan.is_evidence_available
                    ? "Not retained or displayed by this v1 workflow"
                    : "Retention period ended; only the aggregate index remains"}
                </dd>
              </div>
              {scan.evidence_purged_at && (
                <div>
                  <dt className="font-medium text-fg">Evidence purged</dt>
                  <dd className="text-fg-muted" title={scan.evidence_purged_at}>{displayTime(scan.evidence_purged_at)}</dd>
                </div>
              )}
              {scan.key_destroyed_at && (
                <div>
                  <dt className="font-medium text-fg">Evidence key unavailable</dt>
                  <dd className="text-fg-muted" title={scan.key_destroyed_at}>{displayTime(scan.key_destroyed_at)}</dd>
                </div>
              )}
            </dl>
          </Card>

          <Card className="border-sev-major/40 bg-sev-major-bg/30 p-5">
            <div className="flex items-start gap-3">
              <LockKeyhole className="mt-0.5 h-5 w-5 shrink-0 text-sev-major" aria-hidden />
              <div>
                <h2 className="text-base font-semibold text-fg">Protected-data limits</h2>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-fg-muted">
                  <li>Webhooks, remote AI, MCP chat, and unrestricted exports are disabled.</li>
                  <li>Local AI is {scan.allow_local_ai ? "explicitly approved only for bounded in-memory image leads" : "disabled for this report"}.</li>
                  <li>Companion artifact and reviewer-attachment uploads are disabled in this release.</li>
                  <li>The companion blocks mutating requests, downloads, pop-ups, workers, and unapproved destinations.</li>
                </ul>
              </div>
            </div>
          </Card>

          <Card className="p-5">
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
              <div>
                <h2 className="text-base font-semibold text-fg">Manual authentication review</h2>
                <p className="mt-1 text-sm text-fg-muted">
                  A successful manual sign-in lets the companion crawl; it does not automatically prove that sign-in or MFA meets WCAG 2.2 AA 3.3.8. Record an outcome only after reviewing each in-scope authentication step.
                </p>
              </div>
            </div>
            <LinkButton to={`/scans/${id}/protected/manual-checks`} variant="secondary" className="mt-4">
              Record outcome-only review
            </LinkButton>
          </Card>

          <Card className="p-5">
            <div className="flex items-start gap-3">
              <Download className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
              <div>
                <h2 className="text-base font-semibold text-fg">Authorized redacted export</h2>
                <p className="mt-1 text-sm text-fg-muted">
                  Download a minimal Markdown handoff only after this report is complete. It omits target URLs, page locations, selectors, screenshots, OCR text, and all browser or session material. This release has no in-app attachment uploads.
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
                      ? "The protected report must be completed before its redacted summary can be exported."
                      : "Detailed protected evidence has been purged, so no new protected export can be generated."
                }
              >
                <Download className="h-4 w-4" aria-hidden />
                {downloadRedactedExport.isPending
                  ? "Preparing redacted export…"
                  : "Download redacted summary"}
              </Button>
              {!mayExport && (
                <span className="text-sm text-fg-muted">
                  {scan.is_evidence_available
                    ? "Available after the protected crawl completes."
                    : "No longer available after protected-evidence cleanup."}
                </span>
              )}
            </div>
            <p className="mt-3 text-xs text-fg-muted">
              This is an explicit protected action. Axcess records the authorized download but does not write an export or temporary file on the server. Downloaded copies are the recipient’s responsibility.
            </p>
          </Card>

          <p className="px-1 text-xs text-fg-muted">
            Need report context? Return to the <Link to={`/scans/${id}`} className="text-umich-blue underline underline-offset-2">scan overview</Link>. Do not put pairing codes in tickets, chat, exports, or screen recordings.
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
        { label: "Protected companion" },
      ]}
      title="Protected companion"
      subtitle={
        scanId
          ? `Manual sign-in and read-only crawl handoff for scan #${scanId}.`
          : "Manual sign-in and read-only crawl handoff."
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
        One-time pairing code — shown once
      </h3>
      <p className="mt-1 text-sm text-fg-muted">
        Enter this only into the local companion prompt. Axcess will not copy it to your clipboard or show it again after you hide this section.
      </p>
      <dl className="mt-4 space-y-3">
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">Pairing code</dt>
          <dd>
            <code className="mt-1 block break-all rounded-xs border border-border bg-surface px-3 py-2 text-base font-semibold tracking-[0.16em] text-fg">
              {pairing.pairing_code}
            </code>
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">Expires</dt>
          <dd className="mt-1 text-sm text-fg-muted" title={pairing.expires_at}>{displayTime(pairing.expires_at)}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">Local companion command</dt>
          <dd>
            <code className="mt-1 block overflow-x-auto rounded-xs border border-border bg-surface px-3 py-2 text-xs text-fg">
              {pairing.companion_command}
            </code>
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">After pairing</dt>
          <dd>
            <code className="mt-1 block overflow-x-auto rounded-xs border border-border bg-surface px-3 py-2 text-xs text-fg">
              {pairing.companion_run_command}
            </code>
          </dd>
        </div>
      </dl>
      <Button type="button" className="mt-4" onClick={onHide}>
        I recorded it — hide pairing code
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
        Local companion paired
      </h3>
      <p className="mt-1 text-sm text-fg-muted">
        This report is bound to one companion certificate. Use the same local
        command to begin a fresh visible sign-in after a session expires; no
        new pairing code is needed or available.
      </p>
      <dl className="mt-4 space-y-3">
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">
            Enrollment ID
          </dt>
          <dd className="mt-1">
            <code className="block break-all rounded-xs border border-border bg-surface px-3 py-2 text-xs text-fg">
              {companion.enrollment_id}
            </code>
          </dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">
            Re-run on the paired computer
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
        {count === 0 ? "None approved" : `${count} exact ${count === 1 ? "origin" : "origins"} approved`}
      </p>
      <p className="mt-1 text-xs text-fg-subtle">
        Scope tag: <code>{fingerprint ?? "Legacy scope redacted"}</code>
      </p>
    </section>
  );
}
