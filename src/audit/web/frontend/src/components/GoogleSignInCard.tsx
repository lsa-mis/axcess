import { useEffect, useRef } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import type { GoogleSignInState, NewScanPayload } from "../api/types";
import { Button, Card } from "./ui";
import { GOOGLE_SIGN_IN } from "./newScan/copy";
import type { SignInEnd } from "./LocalLoginScan";

const ENDED = new Set<GoogleSignInState["status"]>(["cancelled", "expired", "failed"]);

const ERROR_BOX =
  "mt-4 rounded-xs border border-sev-critical/40 bg-sev-critical-bg p-3 text-sm text-sev-critical";

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * A Google sign-in in progress, before a public scan with "Sign in to
 * Google for Google files" starts (the developer's request, 2026-11-26).
 *
 * A sibling of `LocalSignInCard`, not a mode of it. That card keeps a copy
 * of a site's sign-in, states the limits of a kept site sign-in, and lists
 * what happens to the scan's browser; this one has none of those, talks to
 * other endpoints, and starts a public scan. A `kind` prop would have
 * branched every part of it. What carries over is kept the same, so the
 * two read as one pattern (SC 3.2.4 Consistent Identification, Level AA):
 * the `Card`, the three faces (opening, window open, window closed), focus
 * moving to the heading when the face changes (SC 2.4.3 Focus Order, Level
 * A), the face's explanation in a polite live region (SC 4.1.3 Status
 * Messages, Level AA), errors as text in an alert, and one primary button
 * beside the secondary ones.
 *
 * A closed window works like a closed site sign-in window (the developer's
 * request, 2026-11-26: "There should be a button to open the window again,
 * just exactly like how sign in scan handles this situation"). It offers,
 * in the site card's order and roles: start (primary), "Reopen Google
 * window", and Cancel. The Google sign-in is kept in the browser's profile
 * on this computer, so the start checks it in a hidden browser and the
 * reopen opens a new window from it. This replaces an earlier closed face
 * with Cancel only, whose comment said the developer had asked for that;
 * they had not. Reopen exists only in this face: with the window open it
 * would be a second control for a window already in front of the person
 * (W3C COGA, "Making Content Usable": one way to do one thing,
 * https://www.w3.org/TR/coga-usable/). A closed window's sign-in is signed
 * out and deleted after the stated minutes, which the card says rather
 * than leaving it to be discovered (docs/plain-language.md: never drop a
 * limit). The window's state is said in the heading and the text, never by
 * colour alone (SC 1.4.1 Use of Color, Level A).
 */
export function GoogleSignInCard({
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
    queryKey: ["google-sign-in", signInId],
    queryFn: () => api.getGoogleSignIn(signInId),
    refetchInterval: 1000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    retry: false,
  });
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
    mutationFn: () => api.startGoogleSignInScan(signInId),
    onSuccess: ({ scan_id }) => onStarted(scan_id),
  });
  const reopen = useMutation({
    mutationFn: () => api.reopenGoogleSignIn(signInId),
    onSettled: () => void status.refetch(),
  });
  const cancel = useMutation({
    mutationFn: () => api.cancelGoogleSignIn(signInId),
    onSuccess: () => end("cancelled"),
  });
  const busy = start.isPending || reopen.isPending || cancel.isPending;

  const data = status.data;
  const face: "opening" | "open" | "closed" =
    !data || data.status === "opening_browser" ? "opening" : data.window_open ? "open" : "closed";
  const copy = GOOGLE_SIGN_IN[face];

  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, [face]);
  // A refusal ("not signed in yet", "a scan is already running", "could not
  // reopen") belongs to the face it was given in.
  const { reset: resetStart } = start;
  const { reset: resetReopen } = reopen;
  useEffect(() => {
    resetStart();
    resetReopen();
  }, [face, resetStart, resetReopen]);

  return (
    <Card className="max-w-3xl p-6 [overflow-anchor:none]">
      <p className="text-xs font-semibold text-umich-blue">{GOOGLE_SIGN_IN.eyebrow}</p>
      <h2
        ref={heading}
        tabIndex={-1}
        className="mt-1 text-xl font-semibold text-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-umich-blue"
      >
        {copy.title}
      </h2>
      {alreadyWaiting && <p className="mt-2 text-sm text-fg-muted">{GOOGLE_SIGN_IN.alreadyWaiting}</p>}
      <p role="status" className="mt-2 text-sm text-fg-muted">
        {copy.detail}
      </p>

      {status.error && !gone && (
        <p className={ERROR_BOX} role="alert">
          {errorText(status.error)}
        </p>
      )}

      {face === "closed" && (
        <p className="mt-4 rounded-xs border border-border bg-surface-subtle p-4 text-sm text-fg-muted">
          {GOOGLE_SIGN_IN.forget(data?.keep_minutes ?? 30)}
        </p>
      )}

      {face === "open" && (
        <div className="mt-4 rounded-xs border border-border bg-surface p-3">
          <h3 className="text-sm font-semibold text-fg">{GOOGLE_SIGN_IN.whatHappens}</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-fg-muted">
            {GOOGLE_SIGN_IN.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
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

      {/* Start, the likely next step, is the primary button, as on the
          sign-in card, in the open and the closed face; "Reopen Google
          window" sits between it and Cancel in the closed face, as "Reopen
          sign-in window" does on the sign-in card. "Cancel Google sign-in"
          names what it cancels, since no scan exists yet (repo rule: a verb
          and an object). Each keeps its place in each face (SC 3.2.3
          Consistent Navigation, Level AA, applied within the card). */}
      <div className="mt-5 flex flex-wrap gap-3">
        {face !== "opening" && (
          <Button variant="primary" onClick={() => start.mutate()} disabled={busy}>
            {start.isPending ? GOOGLE_SIGN_IN.starting : GOOGLE_SIGN_IN.start}
          </Button>
        )}
        {face === "closed" && (
          <Button onClick={() => reopen.mutate()} disabled={busy}>
            {reopen.isPending ? GOOGLE_SIGN_IN.reopening : GOOGLE_SIGN_IN.reopen}
          </Button>
        )}
        <Button onClick={() => cancel.mutate()} disabled={busy}>
          {cancel.isPending ? GOOGLE_SIGN_IN.cancelling : GOOGLE_SIGN_IN.cancel}
        </Button>
      </div>
    </Card>
  );
}
