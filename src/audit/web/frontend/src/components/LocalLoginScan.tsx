import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Clock3, ExternalLink, Eye, EyeOff, Loader2, Pause, Play } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { LocalLoginScanStatus } from "../api/types";
import { Button, Card } from "./ui";
import ProtectedScanSteps from "./ProtectedScanSteps";
import { formatScanEta } from "../lib/scanProgress";

const TERMINAL = new Set<LocalLoginScanStatus>([
  "completed",
  "failed",
  "interrupted",
]);

/**
 * The sign-in handoff for a login scan that has been created.
 *
 * The form that creates one lives in the New scan route now, rendered by
 * the same `ScanForm` as a public scan; this component picks up once
 * ``?scan=`` names the scan to sign in to. Without that it renders nothing,
 * which is the route's cue to show the form.
 */
export default function LocalLoginScan({
  showSteps = true,
}: {
  showSteps?: boolean;
}) {
  const [searchParams] = useSearchParams();
  const scanIdValue = Number(searchParams.get("scan"));
  const scanId =
    Number.isInteger(scanIdValue) && scanIdValue > 0 ? scanIdValue : null;

  if (scanId === null) return null;
  return <LocalLoginHandoff scanId={scanId} showSteps={showSteps} />;
}

function LocalLoginHandoff({
  scanId,
  showSteps,
}: {
  scanId: number;
  showSteps: boolean;
}) {
  const navigate = useNavigate();
  const [liveProgress, setLiveProgress] = useState(true);
  const status = useQuery({
    queryKey: ["local-login-scan", scanId],
    queryFn: () => api.getLocalLoginScan(scanId),
    refetchInterval: (query) =>
      query.state.data && TERMINAL.has(query.state.data.status) ? false : 1000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const confirm = useMutation({
    mutationFn: () => api.confirmLocalLogin(scanId),
    onSuccess: () => void status.refetch(),
  });
  const browser = useMutation({
    mutationFn: async (visible: boolean) => {
      const outcome = await api.setLocalLoginBrowserVisible(scanId, visible);
      // The request can succeed while the window stays where it was. Hiding
      // reports its own outcome: the state below says what happened.
      if (visible && outcome.changed === false) {
        throw new Error(
          "Axcess could not bring the Chromium window back. It is still minimized: open it from your Dock or taskbar instead.",
        );
      }
      return outcome;
    },
    onSettled: () => void status.refetch(),
  });

  const state = status.data?.status ?? "opening_browser";
  const scanActivity = useQuery({
    queryKey: ["scan", scanId, "local-login-progress"],
    queryFn: () => api.getScan(scanId),
    enabled: state === "scanning",
    refetchInterval: liveProgress && state === "scanning" ? 2000 : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
  });
  const stage = useMemo(() => {
    if (state === "completed") return "report" as const;
    if (state === "scanning") return "scan" as const;
    if (
      state === "awaiting_authentication" ||
      state === "verifying_authentication"
    ) {
      return "sign_in" as const;
    }
    return "pair" as const;
  }, [state]);

  // Three different situations, and the auditor can only see one of them
  // from here: the window is away, they asked for it back, or Axcess tried to
  // put it away and this computer would not let it.
  const browserHidden = status.data?.browser_backgrounded === true;
  const browserShownOnRequest =
    !browserHidden && status.data?.browser_hiding_wanted === false;
  const browserParked = !browserHidden && status.data?.browser_parked === true;

  const copy: Record<LocalLoginScanStatus, { title: string; detail: string }> =
    {
      opening_browser: {
        title: "Opening the sign-in browser",
        detail: "A visible Chromium window should appear on this computer.",
      },
      awaiting_authentication: {
        title: "Sign in in the Chromium window",
        detail: "Complete the full login and 2FA flow, then return here.",
      },
      verifying_authentication: {
        title: "Moving the browser out of your way",
        detail:
          "Axcess is opening its scan tabs in your signed-in browser and minimizing the window. This takes a few seconds.",
      },
      scanning: browserHidden
        ? {
            title: "Scanning in the background",
            detail:
              "The Chromium window is minimized and Axcess is scanning in it. Carry on with other work. Quitting Chromium would end the scan.",
          }
        : browserShownOnRequest
          ? {
              title: "Scanning with the browser showing",
              detail:
                "The Chromium window is on your screen because you asked to see it. The scan carries on either way. Closing the window would end the scan.",
            }
          : browserParked
            ? {
                title: "Scanning, with the browser moved aside",
                detail:
                  "The Chromium window would not minimize on this computer, so Axcess moved it to the edge of the screen. A strip of it may still show. The scan is running. Closing the window would end the scan.",
              }
            : {
                title: "Scanning, but the browser is still on screen",
                detail:
                  "Axcess has not been able to minimize the Chromium window. The scan is running. Minimize the window yourself if it is in your way; closing it would end the scan.",
              },
      completed: {
        title: "Report ready",
        detail: "Opening the normal Axcess report now.",
      },
      failed: {
        title: "Login scan stopped",
        detail:
          status.data?.error ?? "The local browser scan could not continue.",
      },
      interrupted: {
        title: "Login scan interrupted",
        detail: status.data?.error ?? "The in-memory browser session ended.",
      },
    };

  return (
    <>
      {showSteps && <ProtectedScanSteps current={stage} className="mb-5" />}
      <Card className="max-w-3xl p-6 [overflow-anchor:none]">
        <p className="text-xs font-semibold text-umich-blue">
          Login scan #{scanId}
        </p>
        <h2 className="mt-1 text-xl font-semibold text-fg" aria-live="polite">
          {copy[state].title}
        </h2>
        <p className="mt-2 text-sm text-fg-muted">{copy[state].detail}</p>

        {status.error && (
          <p
            className="mt-4 rounded-md border border-sev-critical/40 bg-sev-critical-bg p-3 text-sm text-sev-critical"
            role="alert"
          >
            {status.error instanceof Error
              ? status.error.message
              : String(status.error)}
          </p>
        )}
        {confirm.error && (
          <p
            className="mt-4 rounded-md border border-sev-critical/40 bg-sev-critical-bg p-3 text-sm text-sev-critical"
            role="alert"
          >
            {confirm.error instanceof Error
              ? confirm.error.message
              : String(confirm.error)}
          </p>
        )}
        {browser.error && (
          <p
            className="mt-4 rounded-md border border-sev-critical/40 bg-sev-critical-bg p-3 text-sm text-sev-critical"
            role="alert"
          >
            {browser.error instanceof Error
              ? browser.error.message
              : String(browser.error)}
          </p>
        )}

        {state === "awaiting_authentication" && (
          <div className="mt-6 rounded-md border-2 border-umich-blue bg-umich-blue/5 p-5">
            <h3 className="font-semibold text-fg">Finished signing in?</h3>
            <p className="mt-1 text-sm text-fg-muted">
              Make sure the visible browser shows the protected application, not
              the U-M or Duo login screen.
            </p>
            <div className="mt-4 rounded-xs border border-border bg-surface p-3">
              <h4 className="text-sm font-semibold text-fg">
                What happens when you start
              </h4>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-fg-muted">
                <li>
                  Axcess minimizes that Chromium window and scans in it in the
                  background, and keeps it minimized while you work.
                </li>
                <li>
                  Chromium stays in your Dock or taskbar. Leave it running:
                  quitting it ends the scan.
                </li>
                <li>
                  Progress appears on this page. To watch the scan, use{" "}
                  <strong>Show browser window</strong> here: a window opened
                  from the Dock or taskbar is minimized again.
                </li>
              </ul>
            </div>
            <Button
              className="mt-4"
              onClick={() => confirm.mutate()}
              disabled={confirm.isPending}
            >
              {confirm.isPending
                ? "Checking sign-in…"
                : "I’m signed in, start scan"}
            </Button>
          </div>
        )}

        {state === "scanning" && (
          // Not a live region: the heading above already announces each
          // change of state, and a region holding the button would re-read
          // itself every time the button's label changed.
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xs border border-border bg-surface p-4">
            <p className="flex items-center gap-2 text-sm font-semibold text-fg">
              <Loader2
                className="h-4 w-4 shrink-0 animate-spin text-umich-blue motion-reduce:animate-none"
                aria-hidden
              />
              {browserHidden
                ? "Scan running · browser hidden"
                : "Scan running · browser on screen"}
            </p>
            <Button
              variant="secondary"
              // aria-disabled, not disabled: a disabled button drops focus to
              // the page, and the person who pressed it has to find it again.
              aria-disabled={browser.isPending}
              className={
                browser.isPending ? "cursor-not-allowed opacity-60" : undefined
              }
              onClick={() => {
                if (!browser.isPending) browser.mutate(browserHidden);
              }}
            >
              {browserHidden ? (
                <Eye className="h-4 w-4" aria-hidden />
              ) : (
                <EyeOff className="h-4 w-4" aria-hidden />
              )}
              {browser.isPending
                ? "Working…"
                : browserHidden
                  ? "Show browser window"
                  : browserShownOnRequest
                    ? "Hide browser window"
                    : "Try hiding it again"}
            </Button>
          </div>
        )}

        {state === "scanning" && (
          <section
            className="mt-5 rounded-xs border border-border bg-surface-subtle p-4"
            aria-labelledby="login-live-progress-title"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3
                  id="login-live-progress-title"
                  className="font-semibold text-fg"
                >
                  Live page activity
                </h3>
                <p className="mt-1 text-xs text-fg-muted">
                  What the scan is doing right now. Updates every two seconds
                  without reloading or scrolling the page.
                </p>
              </div>
              <Button
                variant="secondary"
                onClick={() => setLiveProgress((current) => !current)}
              >
                {liveProgress ? (
                  <Pause className="h-4 w-4" aria-hidden />
                ) : (
                  <Play className="h-4 w-4" aria-hidden />
                )}
                {liveProgress ? "Pause updates" : "Resume updates"}
              </Button>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xs border border-border bg-surface p-3">
                <p className="flex items-center gap-2 text-xs font-semibold text-fg-subtle">
                  <Clock3 className="h-4 w-4" aria-hidden /> Estimated time
                </p>
                <p className="mt-2 text-sm font-semibold text-fg">
                  {formatScanEta(scanActivity.data?.progress?.eta)}
                </p>
              </div>
              <div className="rounded-xs border border-border bg-surface p-3">
                <p className="text-xs font-semibold text-fg-subtle">
                  Progress
                </p>
                <p className="mt-2 text-sm font-semibold text-fg">
                  {scanActivity.data?.progress
                    ? `${scanActivity.data.progress.completed} completed · ${scanActivity.data.progress.pending} queued`
                    : "Loading scan activity…"}
                </p>
              </div>
            </div>

            <div
              className="mt-3 min-h-[6.5rem]"
              aria-live="polite"
              aria-atomic="true"
            >
              <h4 className="text-sm font-semibold text-fg">Scanning now</h4>
              {scanActivity.data?.progress?.in_flight_pages.length ? (
                <ul className="mt-2 max-h-40 space-y-2 overflow-y-auto overscroll-contain">
                  {scanActivity.data.progress.in_flight_pages.map((page) => (
                    <li
                      key={page.url}
                      className="flex items-start gap-2 rounded-xs bg-surface p-3"
                    >
                      <Loader2
                        className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-umich-blue"
                        aria-hidden
                      />
                      <span className="min-w-0 break-all font-mono text-xs text-fg">
                        {page.url}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-fg-muted">
                  Waiting for the next page…
                </p>
              )}
            </div>

            {!!scanActivity.data?.progress?.recent_pages.length && (
              <div className="mt-3">
                <h4 className="text-sm font-semibold text-fg">
                  Recently completed
                </h4>
                <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto overscroll-contain">
                  {scanActivity.data.progress.recent_pages.map((page) => (
                    <li
                      key={page.url_normalized}
                      className="break-all rounded-xs bg-surface px-3 py-2 font-mono text-xs text-fg-muted"
                    >
                      {page.url_normalized}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <Link
              to={`/scans/${scanId}`}
              className="mt-4 inline-flex min-h-11 items-center gap-2 font-semibold text-umich-blue underline underline-offset-2"
            >
              Open full scan progress{" "}
              <ExternalLink size={16} aria-hidden="true" />
            </Link>
          </section>
        )}
        {state === "completed" && (
          <Button className="mt-5" onClick={() => navigate(`/scans/${scanId}`)}>
            Open report
          </Button>
        )}
        {TERMINAL.has(state) && state !== "completed" && (
          <Button
            className="mt-5"
            onClick={() => navigate("/scans/new?mode=login", { replace: true })}
          >
            Start a new login scan
          </Button>
        )}
      </Card>
    </>
  );
}
