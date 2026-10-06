import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Clock3, ExternalLink, Loader2, Pause, Play } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { ApiError, api } from "../api/client";
import type {
  LocalLoginScanStatus,
  LocalSignInState,
  NewScanPayload,
} from "../api/types";
import { Button, Card } from "./ui";
import { SIGN_IN } from "./newScan/copy";
import { formatScanEta } from "../lib/scanProgress";

const TERMINAL = new Set<LocalLoginScanStatus>([
  "completed",
  "failed",
  "interrupted",
]);

/** Why a sign-in ended: the server's word for it, or "gone" when the server no longer knows it. */
export type SignInEnd = "cancelled" | "expired" | "failed" | "gone";

const ENDED = new Set<LocalSignInState["status"]>(["cancelled", "expired", "failed"]);

const ERROR_BOX =
  "mt-4 rounded-xs border border-sev-critical/40 bg-sev-critical-bg p-3 text-sm text-sev-critical";

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * A sign-in in progress, before any scan exists.
 *
 * "Open browser to sign in" no longer creates a scan. Until the person
 * presses "I'm signed in, start scan" this is a sign-in with its own ID, so
 * Reports shows nothing for it and an abandoned attempt leaves no stopped,
 * empty report behind. The card's label is "Sign-in"; "Sign-in scan #N"
 * appears only once the scan exists and has a number.
 *
 * The card has three faces, chosen by what the server reports:
 *
 * - opening: the window is on its way;
 * - window open: sign in there, then start or cancel;
 * - window closed: Axcess kept the sign-in, so the person can start from
 *   the kept copy, reopen the window, or cancel. Reopen exists only in this
 *   face: with the window open it would be a second control for a window
 *   already in front of them (W3C COGA, "Making Content Usable": one way to
 *   do one thing, https://www.w3.org/TR/coga-usable/).
 *
 * The window's state is said in the heading and the text, never by colour
 * or an icon alone (SC 1.4.1 Use of Color, Level A).
 *
 * Focus moves to the card heading when the face changes, and when the card
 * first appears. The button the person pressed (the form's submit button,
 * Reopen) is gone after the change, and focus left on a removed element
 * falls back to the page top, so the next Tab would restart the page
 * (SC 2.4.3 Focus Order, Level A). Moving to the heading puts the reader
 * where the new content starts. A polite live region carries the face's
 * one-line explanation, so a change that happens while the person is in the
 * sign-in window, such as the window closing, is still announced
 * (SC 4.1.3 Status Messages, Level AA). Rejected: an assertive alert. A
 * closed window is news, not an error, and an alert would interrupt
 * whatever the reader was doing.
 */
export function LocalSignInCard({
  signInId,
  alreadyWaiting,
  onEnded,
  onStarted,
}: {
  signInId: string;
  alreadyWaiting: boolean;
  onEnded: (reason: SignInEnd, settings: NewScanPayload | null, keepMinutes: number) => void;
  onStarted: (scanId: number) => void;
}) {
  const status = useQuery({
    queryKey: ["local-sign-in", signInId],
    queryFn: () => api.getLocalSignIn(signInId),
    refetchInterval: 1000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    retry: false,
  });
  // The settings and limit from the last answer, so the form can be refilled
  // and the message worded even after the server has forgotten the sign-in.
  const last = useRef<{ settings: NewScanPayload | null; minutes: number }>({
    settings: null,
    minutes: 30,
  });
  useEffect(() => {
    if (!status.data) return;
    last.current = {
      settings: status.data.settings ?? last.current.settings,
      minutes: status.data.keep_minutes,
    };
  }, [status.data]);

  const ended = useRef(false);
  const end = (reason: SignInEnd) => {
    if (ended.current) return;
    ended.current = true;
    onEnded(reason, last.current.settings, last.current.minutes);
  };
  const serverStatus = status.data?.status;
  const gone = status.error instanceof ApiError && status.error.status === 404;
  useEffect(() => {
    if (serverStatus && ENDED.has(serverStatus)) end(serverStatus as SignInEnd);
    else if (gone) end("gone");
    // `end` reads refs only; re-running it for a new identity changes nothing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverStatus, gone]);

  const start = useMutation({
    mutationFn: () => api.startLocalSignInScan(signInId),
    onSuccess: ({ scan_id }) => onStarted(scan_id),
  });
  const reopen = useMutation({
    mutationFn: () => api.reopenLocalSignIn(signInId),
    onSettled: () => void status.refetch(),
  });
  const cancel = useMutation({
    mutationFn: () => api.cancelLocalSignIn(signInId),
    onSuccess: () => end("cancelled"),
  });
  const busy = start.isPending || reopen.isPending || cancel.isPending;

  const data = status.data;
  const face: "opening" | "open" | "closed" =
    !data || data.status === "opening_browser"
      ? "opening"
      : data.window_open
        ? "open"
        : "closed";
  const copy = SIGN_IN[face];

  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, [face]);

  // A start refused because another scan is running leaves the sign-in
  // waiting; the message says so. Clear it once the face changes, so an old
  // refusal does not sit under a new state.
  const { reset: resetStart } = start;
  const { reset: resetReopen } = reopen;
  useEffect(() => {
    resetStart();
    resetReopen();
  }, [face, resetStart, resetReopen]);

  return (
    <Card className="max-w-3xl p-6 [overflow-anchor:none]">
      <p className="text-xs font-semibold text-umich-blue">{SIGN_IN.eyebrow}</p>
      <h2
        ref={heading}
        tabIndex={-1}
        className="mt-1 text-xl font-semibold text-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-umich-blue"
      >
        {copy.title}
      </h2>
      {data?.site && (
        <p className="mt-2 text-sm font-semibold text-fg">{SIGN_IN.site(data.site)}</p>
      )}
      {/* The site line says which sign-in this is, so a person who comes
          back through the New scan link, or who submitted the form again
          for another site, knows what they are looking at. When the form
          was submitted while this one waited, say why no second window
          opened: Axcess keeps one sign-in at a time (W3C COGA, "Making
          Content Usable": tell people what happened and why). */}
      {alreadyWaiting && <p className="mt-2 text-sm text-fg-muted">{SIGN_IN.alreadyWaiting}</p>}
      <p role="status" className="mt-2 text-sm text-fg-muted">
        {copy.detail}
      </p>

      {status.error && !gone && (
        <p className={ERROR_BOX} role="alert">
          {errorText(status.error)}
        </p>
      )}

      {face === "closed" && (
        <div className="mt-4 rounded-xs border border-border bg-surface-subtle p-4 text-sm text-fg-muted">
          {/* The limit and the expiry are stated where the choice is made,
              not left for the person to discover after reopening (rule 12
              in docs/plain-language.md: never drop a limit to save space). */}
          <p>{SIGN_IN.limit}</p>
          <p className="mt-2">{SIGN_IN.keep(data?.keep_minutes ?? 30)}</p>
        </div>
      )}

      {face === "open" && (
        <div className="mt-6 rounded-xs border-2 border-umich-blue bg-umich-blue/5 p-5">
          <h3 className="font-semibold text-fg">Finished signing in?</h3>
          <p className="mt-1 text-sm text-fg-muted">
            Check that the browser window shows the site you signed in to, not
            the U-M or Duo sign-in screen.
          </p>
          <div className="mt-4 rounded-xs border border-border bg-surface p-3">
            <h4 className="text-sm font-semibold text-fg">
              What happens when you start
            </h4>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-fg-muted">
              <li>
                If &ldquo;Show the scanning browser window&rdquo; is off,
                Axcess moves your sign-in to a hidden browser and closes the
                sign-in window.
              </li>
              <li>
                If it is on, the scan runs in this signed-in window. Leave it
                open. Closing it ends the scan.
              </li>
              <li>Keep Axcess running. Progress appears on this page.</li>
              <li>{SIGN_IN.keepOpen(data?.keep_minutes ?? 30)}</li>
            </ul>
          </div>
        </div>
      )}

      {start.error && (
        <p className={ERROR_BOX} role="alert">
          {errorText(start.error)}
        </p>
      )}
      {reopen.error && (
        <p className={ERROR_BOX} role="alert">
          {errorText(reopen.error)}
        </p>
      )}
      {cancel.error && (
        <p className={ERROR_BOX} role="alert">
          {errorText(cancel.error)}
        </p>
      )}

      {/* One primary button, the likeliest next step, as on the stopped-scan
          card (ScanDetail): start. "Cancel sign-in" sits next to it as a
          secondary button. It says "sign-in", not "scan", because no scan
          exists yet; it closes the window, erases the kept sign-in and
          returns to the form with every entry kept (SC 3.3.7 Redundant
          Entry, Level A). The buttons keep their place in each face, so a
          returning reader finds them where they were (SC 3.2.3 Consistent
          Navigation, Level AA, applied within the card). */}
      <div className="mt-5 flex flex-wrap gap-3">
        {face !== "opening" && (
          <Button variant="primary" onClick={() => start.mutate()} disabled={busy}>
            {start.isPending ? SIGN_IN.starting : SIGN_IN.start}
          </Button>
        )}
        {face === "closed" && (
          <Button onClick={() => reopen.mutate()} disabled={busy}>
            {reopen.isPending ? SIGN_IN.reopening : SIGN_IN.reopen}
          </Button>
        )}
        <Button onClick={() => cancel.mutate()} disabled={busy}>
          {cancel.isPending ? SIGN_IN.cancelling : SIGN_IN.cancel}
        </Button>
      </div>
    </Card>
  );
}

/**
 * A sign-in scan that has started: from "I'm signed in, start scan" until
 * the report is ready or the scan stops.
 *
 * The form that sets one up lives in the New scan route, rendered by the
 * same `ScanForm` as a public scan, and the sign-in before the scan starts
 * is `LocalSignInCard`. This card picks up once ``?scan=`` names the scan.
 */
export function LocalLoginHandoff({ scanId }: { scanId: number }) {
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

  const state = status.data?.status ?? "verifying_authentication";
  const scanActivity = useQuery({
    queryKey: ["scan", scanId, "local-login-progress"],
    queryFn: () => api.getScan(scanId),
    enabled: state === "scanning",
    refetchInterval: liveProgress && state === "scanning" ? 2000 : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
  });

  // Set once the login session has moved to the headless scan browser. When
  // the auditor asked to keep the browser visible, the scan stays in the
  // signed-in window instead.
  const browserHidden = status.data?.browser_backgrounded === true;

  const copy: Record<LocalLoginScanStatus, { title: string; detail: string }> =
    {
      verifying_authentication: {
        title: "Preparing the signed-in session",
        detail:
          "Axcess is setting up your signed-in session. It uses your choice to show or hide the browser.",
      },
      scanning: browserHidden
        ? {
            title: "Scanning in the background",
            detail:
              "The sign-in window has closed. Axcess moved your sign-in to a hidden browser and is scanning there. Keep Axcess running until the scan finishes.",
          }
        : {
            title: "Scanning with the browser visible",
            detail:
              "Axcess is scanning in your signed-in browser. Leave the browser window open until the scan finishes.",
          },
      completed: {
        title: "Report ready",
        detail: "Open the report to see what the scan found.",
      },
      failed: {
        title: "Sign-in scan stopped",
        detail:
          status.data?.error ?? "The browser on this computer could not continue the scan. Start a new sign-in scan to try again.",
      },
      interrupted: {
        title: "Sign-in scan interrupted",
        detail: status.data?.error ?? "The sign-in session ended. Axcess keeps it only in memory, so this scan cannot continue.",
      },
    };

  // The card arrives in place of the sign-in card, whose start button is
  // gone; focus its heading so the reader lands on the new state (SC 2.4.3
  // Focus Order, Level A). Later changes are announced by the heading's
  // polite live region, without moving focus away from a control the reader
  // may be using, such as Pause updates.
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);

  return (
    <Card className="max-w-3xl p-6 [overflow-anchor:none]">
      <p className="text-xs font-semibold text-umich-blue">
        {SIGN_IN.scanEyebrow(scanId)}
      </p>
      <h2
        ref={heading}
        tabIndex={-1}
        className="mt-1 text-xl font-semibold text-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-umich-blue"
        aria-live="polite"
      >
        {copy[state].title}
      </h2>
      <p className="mt-2 text-sm text-fg-muted">{copy[state].detail}</p>

      {status.error && (
        <p className={ERROR_BOX} role="alert">
          {errorText(status.error)}
        </p>
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
                Axcess is checking your signed-in pages. This panel updates
                every two seconds without reloading or scrolling the page.
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
                  ? `${scanActivity.data.progress.completed} pages checked · ${scanActivity.data.progress.pending} waiting`
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
                Recently checked pages
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
      {/* Back to the form with this scan's settings filled in (`from=`),
          so a failed or stopped sign-in does not cost the reader every
          choice they made. Sign-in and the confirmations are never
          saved, so those are asked for again. */}
      {TERMINAL.has(state) && state !== "completed" && (
        <Button
          className="mt-5"
          onClick={() => navigate(`/scans/new?mode=login&from=${scanId}`, { replace: true })}
        >
          Start a new sign-in scan with these settings
        </Button>
      )}
    </Card>
  );
}
