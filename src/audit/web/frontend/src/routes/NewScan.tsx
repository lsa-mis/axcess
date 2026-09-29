import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Checkbox, PageHeader } from "../components/ui";
import LocalLoginScan from "../components/LocalLoginScan";
import { AUTHORIZATION, IMAGE_ACK, RECOVERY } from "../components/newScan/copy";
import ScanForm, { SCAN_FORM_ID } from "../components/newScan/ScanForm";
import SubmitBar from "../components/newScan/SubmitBar";
import ScanTypeTabs from "../components/newScan/ScanTypeTabs";
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

/**
 * Start a scan: two tabs, one form.
 *
 * The route owns what a form needs from the outside world — the settings,
 * the capability queries, the scope preview and the two mutations — and
 * hands them to `ScanForm` under the policy for the selected tab. The tab is
 * `?mode=`, so it is bookmarkable and the topbar trail is the way back; a
 * change re-keys the form so it drops in fresh with that mode's defaults.
 * Once a login scan has been created, `?scan=` hands over to the sign-in
 * flow, which is its own screen.
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

  const selectMode = (next: ScanMode) => {
    const params = new URLSearchParams(searchParams);
    params.delete("scan");
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
    if (!snapshot || appliedFrom.current === snapshot.scan_id) return;
    if (snapshot.mode !== mode) {
      // A link that named the wrong tab: move to the scan's own tab first.
      setSearchParams((previous) => {
        const params = new URLSearchParams(previous);
        params.delete("scan");
        if (snapshot.mode === "login") params.set("mode", "login");
        else params.delete("mode");
        return params;
      });
      return;
    }
    appliedFrom.current = snapshot.scan_id;
    setSettings(settingsFromSnapshot(snapshot, policyFor(mode)));
    setErrors([]);
  }, [snapshot, mode, setSearchParams]);

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
  const createLogin = useMutation({
    mutationFn: (payload: ScanSettings) =>
      api.createLocalLoginScan(toLocalLoginPayload(payload, { imageAck })),
    onSuccess: ({ scan_id }) => {
      void queryClient.invalidateQueries({ queryKey: ["scans"] });
      navigate(`/scans/new?mode=login&scan=${scan_id}`, { replace: true });
    },
    onError: (reason: unknown) =>
      setErrors([{ field: "form", message: reason instanceof Error ? reason.message : String(reason) }]),
  });
  const pending = createPublic.isPending || createLogin.isPending;

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending) return;
    const found = validateScan(settings, policy, { authorized, imageAck });
    setErrors(found);
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

      {fromScanId !== null && !inHandoff && (
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

      {inHandoff ? (
        <LocalLoginScan showSteps={false} />
      ) : (
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
