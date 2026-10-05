import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { NewScanPayload } from "../api/types";
import { Checkbox, PageHeader } from "../components/ui";
import { LocalLoginHandoff, LocalSignInCard, type SignInEnd } from "../components/LocalLoginScan";
import { AUTHORIZATION, IMAGE_ACK, RECOVERY, SIGN_IN } from "../components/newScan/copy";
import ScanForm, { SCAN_FORM_ID } from "../components/newScan/ScanForm";
import SubmitBar from "../components/newScan/SubmitBar";
import ScanTypeTabs, { SCAN_PANEL_ID, scanTabId } from "../components/newScan/ScanTypeTabs";
import {
  applyPolicy,
  policyFor,
  settingsFromSnapshot,
  toLocalLoginPayload,
  validateScan,
  type FieldError,
  type FieldKey,
  type ScanMode,
  type ScanSettings,
} from "../components/newScan/scanPolicy";
import { useScopePreview } from "../components/newScan/useScopePreview";

const FIELD_IDS = {
  url: "scan-url",
  max_pages: "scan-max-pages",
  max_depth: "scan-max-depth",
  static_only: "scan-static-only",
  authorized: "scan-authorized",
  image_ack: "scan-image-ack",
} as const;

/** Which settings, when edited, settle each error the alert can list. */
const ERROR_CLEARED_BY: Partial<Record<FieldKey, ReadonlyArray<keyof ScanSettings>>> = {
  url: ["url"],
  max_pages: ["max_pages"],
  max_depth: ["max_depth"],
  static_only: ["static_only", "scan_engine"],
};

function positiveId(raw: string | null): number | null {
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : null;
}

/** A sign-in ID as the server issues it; anything else is ignored. */
function signInIdFrom(raw: string | null): string | null {
  return raw && /^[A-Za-z0-9_-]{16,64}$/.test(raw) ? raw : null;
}

/** What the page says after a sign-in ended without a scan. */
type EndNotice = { reason: SignInEnd; minutes: number };

/**
 * Start a scan: two tabs, one form.
 *
 * The route owns what a form needs from the outside world — the settings,
 * the capability queries, the scope preview and the two mutations — and
 * hands them to `ScanForm` under the policy for the selected tab. The tab is
 * `?mode=`, so it is bookmarkable and the topbar trail is the way back; a
 * change re-keys the form so it drops in fresh with that mode's defaults.
 * `?sign_in=` shows the card for a sign-in in progress, before any scan
 * exists, and `?scan=` the card for a sign-in scan once it has started.
 *
 * New scan opened with neither a tab nor a card in its address (the
 * sidebar's New scan link, for one) asks the server whether a sign-in is
 * waiting, and if so replaces the address with that sign-in's card. The
 * card used to live only in the address, so leaving the page lost it, and
 * the sign-in window sat open with no way back to its start button. The
 * address is replaced, not pushed, so Back still leaves New scan in one
 * step. The check runs once per visit: choosing the "Public website" tab
 * from the card shows the public form and stays there, so a waiting
 * sign-in never blocks a public scan.
 *
 * `?from=<scan id>` starts again from a scan that failed or was stopped:
 * its settings are fetched from the server and laid over the tab's
 * defaults once. Only settings come back. Sign-in happens in the site's own
 * window and is never stored, and the authorization and image-storage
 * confirmations start unticked, because they are the person's to give for
 * this run. Nothing here is kept in browser storage.
 */
export default function NewScanRoute() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const mode: ScanMode = searchParams.get("mode") === "login" ? "login" : "public";
  const policy = policyFor(mode);
  const handoffScanId = Number(searchParams.get("scan"));
  const inHandoff = mode === "login" && Number.isInteger(handoffScanId) && handoffScanId > 0;
  const signInId = mode === "login" && !inHandoff ? signInIdFrom(searchParams.get("sign_in")) : null;
  const inCard = inHandoff || signInId !== null;
  const location = useLocation();
  const alreadyWaiting = Boolean((location.state as { alreadyWaiting?: boolean } | null)?.alreadyWaiting);
  const [endNotice, setEndNotice] = useState<EndNotice | null>(null);

  const selectMode = (next: ScanMode) => {
    const params = new URLSearchParams(searchParams);
    params.delete("scan");
    params.delete("sign_in");
    setEndNotice(null);
    if (next === "login") params.set("mode", "login");
    else params.delete("mode");
    setSearchParams(params);
  };

  const [settings, setSettings] = useState<ScanSettings>(() =>
    applyPolicy({ ...policy.defaults, url: searchParams.get("url") ?? "" }, policy),
  );
  // A new tab is a new kind of scan: everything but the address starts from
  // that mode's defaults, which is also what the default card claims.
  useEffect(() => {
    setSettings((previous) => applyPolicy({ ...policyFor(mode).defaults, url: previous.url }, policyFor(mode)));
    setErrors([]);
  }, [mode]);

  const [errors, setErrors] = useState<FieldError[]>([]);
  const [authorized, setAuthorized] = useState(false);
  const [imageAck, setImageAck] = useState(false);
  const urlInputRef = useRef<HTMLInputElement>(null);

  const fromScanId = positiveId(searchParams.get("from"));
  const previousSettings = useQuery({
    queryKey: ["scan-settings", fromScanId],
    queryFn: () => api.getScanSettings(fromScanId ?? 0),
    enabled: fromScanId !== null,
    retry: false,
    staleTime: Infinity,
  });
  // Applied once per scan id and only on the tab the scan belongs to, after
  // the tab-change reset above, so switching tabs by hand afterwards still
  // starts that tab from its own defaults.
  const appliedFrom = useRef<number | null>(null);
  const snapshot = previousSettings.data;
  useEffect(() => {
    // Not while a card is shown: switching tabs would leave the card.
    if (!snapshot || appliedFrom.current === snapshot.scan_id || inCard) return;
    if (snapshot.mode !== mode) {
      // A link that named the wrong tab: move to the scan's own tab first.
      setSearchParams((previous) => {
        const params = new URLSearchParams(previous);
        params.delete("scan");
        params.delete("sign_in");
        if (snapshot.mode === "login") params.set("mode", "login");
        else params.delete("mode");
        return params;
      });
      return;
    }
    appliedFrom.current = snapshot.scan_id;
    setSettings(settingsFromSnapshot(snapshot, policyFor(mode)));
    setErrors([]);
  }, [snapshot, mode, setSearchParams, inCard]);

  const update = (patch: Partial<ScanSettings>) => {
    setSettings((previous) => applyPolicy({ ...previous, ...patch }, policy));
    // A field the alert named is being edited: drop its line so the alert
    // shrinks as the reader works through it.
    if (errors.length) {
      setErrors((previous) =>
        previous.filter((error) => !(ERROR_CLEARED_BY[error.field] ?? []).some((key) => key in patch)),
      );
    }
  };
  const reset = () => {
    setSettings((previous) => applyPolicy({ ...policy.defaults, url: previous.url }, policy));
    setErrors([]);
  };

  const preview = useScopePreview(settings.url, settings.whole_host, mode);
  const alfaCapability = useQuery({
    queryKey: ["capabilities", "alfa"],
    queryFn: api.getAlfaCapability,
  });
  const localAnalysisCapability = useQuery({
    queryKey: ["capabilities", "local-analysis"],
    queryFn: api.getLocalAnalysisCapability,
    retry: false,
  });
  const protectedCapability = useQuery({
    queryKey: ["capabilities", "protected-scans"],
    queryFn: api.getProtectedScanCapability,
    retry: false,
  });
  const protectedReady = Boolean(
    protectedCapability.data?.available || protectedCapability.data?.local_available,
  );

  // Once per visit, and only when the address names no tab and no card.
  // Until the answer comes the form is held back, so it does not appear and
  // then vanish under the reader's pointer or focus. The request is local
  // and answers at once; an error (a browser that is not on this computer
  // cannot have a sign-in here) shows the form.
  const [checkSignIn, setCheckSignIn] = useState(
    () => !searchParams.get("mode") && !searchParams.get("scan") && !searchParams.get("sign_in"),
  );
  const waitingSignIn = useQuery({
    queryKey: ["local-sign-in", "current"],
    queryFn: api.getCurrentLocalSignIn,
    enabled: checkSignIn,
    retry: false,
    staleTime: 0,
    gcTime: 0,
  });
  useEffect(() => {
    if (!checkSignIn || waitingSignIn.isPending) return;
    setCheckSignIn(false);
    const found = waitingSignIn.data?.sign_in;
    if (!found || (found.status !== "opening_browser" && found.status !== "awaiting_authentication")) return;
    setSearchParams(
      (previous) => {
        const params = new URLSearchParams(previous);
        params.set("mode", "login");
        params.delete("scan");
        params.set("sign_in", found.sign_in_id);
        return params;
      },
      { replace: true },
    );
  }, [checkSignIn, waitingSignIn.isPending, waitingSignIn.data, setSearchParams]);

  // What the server cannot run, the form does not offer: fall back rather
  // than let a scan start with an engine or a model that is not there.
  useEffect(() => {
    if (alfaCapability.data?.available === false && settings.scan_engine !== "axe") {
      setSettings((previous) => ({ ...previous, scan_engine: "axe" }));
    }
  }, [alfaCapability.data?.available, settings.scan_engine]);
  useEffect(() => {
    const local = localAnalysisCapability.data;
    if (!local) return;
    if (local.vision.available === false && !settings.skip_vlm) {
      setSettings((previous) => ({ ...previous, skip_vlm: true }));
    }
    if (local.semantic.available === false && !settings.skip_semantic) {
      setSettings((previous) => ({ ...previous, skip_semantic: true }));
    }
  }, [localAnalysisCapability.data, settings.skip_semantic, settings.skip_vlm]);

  // A new scan changes the scan list, so the list is marked out of date, as
  // quick retry and delete already do. Only navigating, Reports showed its
  // cached list for its five fresh seconds, and a list with no running scan
  // does not refresh itself: before a site's first scan, "No reports yet".
  const queryClient = useQueryClient();
  const createPublic = useMutation({
    mutationFn: (payload: ScanSettings) => api.createScan(payload),
    onSuccess: ({ scan_id }) => {
      void queryClient.invalidateQueries({ queryKey: ["scans"] });
      navigate(`/scans/${scan_id}`);
    },
    onError: (reason: unknown) =>
      setErrors([{ field: "form", message: reason instanceof Error ? reason.message : String(reason) }]),
  });
  // Opening the sign-in window creates no scan, so the scan list is not
  // touched here; it is when the sign-in scan starts (`onScanStarted`).
  const createLogin = useMutation({
    mutationFn: (payload: ScanSettings) =>
      api.createLocalSignIn(toLocalLoginPayload(payload, { imageAck })),
    onSuccess: (signIn) => {
      setEndNotice(null);
      navigate(`/scans/new?mode=login&sign_in=${encodeURIComponent(signIn.sign_in_id)}`, {
        replace: true,
        state: { alreadyWaiting: signIn.already_waiting },
      });
    },
    onError: (reason: unknown) =>
      setErrors([{ field: "form", message: reason instanceof Error ? reason.message : String(reason) }]),
  });
  const pending = createPublic.isPending || createLogin.isPending;

  const onScanStarted = (scanId: number) => {
    void queryClient.invalidateQueries({ queryKey: ["scans"] });
    navigate(`/scans/new?mode=login&scan=${scanId}`, { replace: true });
  };
  // Back to the form, with the reader's entries as they left them
  // (SC 3.3.7 Redundant Entry, Level A). This route kept them while the
  // card was shown. If the route was opened afresh on the card (the New
  // scan link, after leaving the page), its form starts empty, so it is
  // refilled from the sign-in's own settings, which the server sent while
  // the sign-in waited. A refilled form leaves the confirmations unticked:
  // as for `from=`, they are the person's to give for each run, and this
  // route no longer holds the ticks they gave.
  const onSignInEnded = (reason: SignInEnd, signInSettings: NewScanPayload | null, minutes: number) => {
    if (signInSettings && !settings.url.trim()) {
      setSettings(applyPolicy({ ...policyFor("login").defaults, ...signInSettings }, policyFor("login")));
    }
    setEndNotice({ reason, minutes });
    setSearchParams(
      (previous) => {
        const params = new URLSearchParams(previous);
        params.set("mode", "login");
        params.delete("sign_in");
        params.delete("scan");
        return params;
      },
      { replace: true },
    );
  };
  // The notice takes focus when it appears: the card, and the button the
  // reader pressed, are gone, and focus would otherwise fall to the page top
  // (SC 2.4.3 Focus Order, Level A). It is also a polite live region, so an
  // expiry that happens while the reader is elsewhere is announced without
  // interrupting them (SC 4.1.3 Status Messages, Level AA).
  const endNoticeRef = useRef<HTMLParagraphElement>(null);
  // After the card has gone: the address changes a render after the
  // notice is set. Runs after the form's own autofocus on its address field,
  // so the reader hears what happened first; the next Tab reaches that field.
  useEffect(() => {
    if (endNotice && !inCard) endNoticeRef.current?.focus();
  }, [endNotice, inCard]);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending) return;
    const found = validateScan(settings, policy, { authorized, imageAck });
    setErrors(found);
    setEndNotice(null);
    if (found.length) return;
    if (mode === "login") createLogin.mutate(settings);
    else createPublic.mutate(settings);
  };

  const loginDisabledReason =
    mode === "public" && !protectedCapability.isLoading && !protectedReady
      ? (protectedCapability.data?.reason ?? "Sign-in scans are not available on this server.")
      : null;
  const loginModeHref = (() => {
    const params = new URLSearchParams(searchParams);
    params.delete("scan");
    params.delete("sign_in");
    params.set("mode", "login");
    return `/scans/new?${params.toString()}`;
  })();

  return (
    <>
      {/* No `crumbs` here: the trail lives in the topbar, same as every report
          view. Passing it again would print the breadcrumb twice on this one
          route and in a different place from the rest of the app. */}
      {/* No actions here: Start and Cancel are at the foot of the summary
          rail, after the form (see SubmitBar for why). */}
      <PageHeader title="New scan" />

      <div className="mb-5 flex flex-col gap-2">
        <ScanTypeTabs mode={mode} onChange={selectMode} disabledReason={loginDisabledReason} />
        {loginDisabledReason && (
          <Link
            to={loginModeHref}
            className="report-link inline-flex min-h-target w-fit items-center font-semibold"
          >
            See how to set up sign-in scans
          </Link>
        )}
      </div>

      {fromScanId !== null && !inCard && (
        // Mounted before the fetch settles, so the result is announced.
        <p
          role="status"
          className="mb-5 rounded-xs border border-umich-blue/30 bg-umich-blue/[0.04] px-4 py-3 text-sm text-fg"
        >
          {previousSettings.isError ? (
            RECOVERY.failed(fromScanId)
          ) : snapshot && snapshot.mode === mode ? (
            <>
              {RECOVERY.loaded(fromScanId)}
              {mode === "login" && <> {RECOVERY.loadedLogin}</>}
            </>
          ) : (
            RECOVERY.loading(fromScanId)
          )}
        </p>
      )}

      {endNotice && !inCard && (
        <p
          ref={endNoticeRef}
          tabIndex={-1}
          role="status"
          className="mb-5 rounded-xs border border-umich-blue/30 bg-umich-blue/[0.04] px-4 py-3 text-sm text-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-umich-blue"
        >
          {endNotice.reason === "expired"
            ? SIGN_IN.ended.expired(endNotice.minutes)
            : SIGN_IN.ended[endNotice.reason]}
        </p>
      )}

      {inCard ? (
        // The card is what the "Site with a sign-in" tab shows while a
        // sign-in or a sign-in scan is under way, so it is that tab's panel,
        // the element the tab's aria-controls names (WAI-ARIA Authoring
        // Practices, Tabs pattern: https://www.w3.org/WAI/ARIA/apg/patterns/tabs/).
        // Without the wrapper the tab pointed at a panel that was not there,
        // an invalid aria-controls (axe: aria-valid-attr-value).
        <div id={SCAN_PANEL_ID} role="tabpanel" aria-labelledby={scanTabId("login")}>
          {inHandoff ? (
            <LocalLoginHandoff scanId={handoffScanId} />
          ) : (
            <LocalSignInCard
              key={signInId}
              signInId={signInId ?? ""}
              alreadyWaiting={alreadyWaiting}
              onEnded={onSignInEnded}
              onStarted={onScanStarted}
            />
          )}
        </div>
      ) : checkSignIn ? null : (
        <ScanForm
          key={mode}
          policy={policy}
          settings={settings}
          update={update}
          onReset={reset}
          preview={preview}
          capabilities={{ alfa: alfaCapability.data, local: localAnalysisCapability.data }}
          errors={errors}
          fieldIds={FIELD_IDS}
          onSubmit={onSubmit}
          urlInputRef={urlInputRef}
          actions={
            <SubmitBar
              form={SCAN_FORM_ID}
              label={policy.submitLabel}
              pendingLabel={policy.submitPendingLabel}
              pending={pending}
              hasNote={Boolean(policy.submitNote)}
              onCancel={() => navigate("/scans")}
            />
          }
          beforeGroups={
            mode === "login" ? (
              <div className="rounded-xs border border-border bg-surface p-3">
                <Checkbox
                  id={FIELD_IDS.authorized}
                  checked={authorized}
                  onChange={(value) => {
                    setAuthorized(value);
                    if (value) setErrors((previous) => previous.filter((error) => error.field !== "authorized"));
                  }}
                  label={AUTHORIZATION.label}
                  hint={AUTHORIZATION.hint}
                  error={errors.find((error) => error.field === "authorized")?.message}
                />
              </div>
            ) : null
          }
          afterGroups={
            mode === "login" && !settings.skip_ocr ? (
              <div className="rounded-xs border border-sev-major/50 bg-sev-major-bg/30 p-3">
                <Checkbox
                  id={FIELD_IDS.image_ack}
                  tone="warning"
                  checked={imageAck}
                  onChange={(value) => {
                    setImageAck(value);
                    if (value) setErrors((previous) => previous.filter((error) => error.field !== "image_ack"));
                  }}
                  label={IMAGE_ACK.label}
                  hint={settings.skip_vlm ? IMAGE_ACK.hintOcr : IMAGE_ACK.hintVision}
                  error={errors.find((error) => error.field === "image_ack")?.message}
                />
              </div>
            ) : null
          }
        />
      )}
    </>
  );
}
