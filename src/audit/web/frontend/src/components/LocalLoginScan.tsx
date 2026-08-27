import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertOctagon,
  Check,
  Clock3,
  ExternalLink,
  Loader2,
  Pause,
  Play,
  Settings2,
} from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { LocalLoginScanPayload, LocalLoginScanStatus } from "../api/types";
import EngineChoice from "../routes/EngineChoice";
import { Button, Card, Checkbox } from "./ui";
import ProtectedScanSteps from "./ProtectedScanSteps";
import { formatScanEta } from "../lib/scanProgress";

const TERMINAL = new Set<LocalLoginScanStatus>([
  "completed",
  "failed",
  "interrupted",
  "authentication_required",
]);

export default function LocalLoginScan({
  showSteps = true,
}: {
  showSteps?: boolean;
}) {
  const [searchParams] = useSearchParams();
  const scanIdValue = Number(searchParams.get("scan"));
  const scanId =
    Number.isInteger(scanIdValue) && scanIdValue > 0 ? scanIdValue : null;

  if (scanId !== null)
    return <LocalLoginHandoff scanId={scanId} showSteps={showSteps} />;
  return <LocalLoginForm showSteps={showSteps} />;
}

function LocalLoginForm({ showSteps }: { showSteps: boolean }) {
  const navigate = useNavigate();
  const [authorized, setAuthorized] = useState(false);
  const [form, setForm] = useState<
    Omit<
      LocalLoginScanPayload,
      "approved_auth_origins" | "authorization_acknowledged"
    >
  >({
    seed_url: "",
    max_pages: 2500,
    max_depth: 10,
    rps: 1,
    workers: 2,
    whole_host: false,
    scan_engine: "axe",
    axe_level: "AA",
    skip_keyboard: false,
    skip_responsive: false,
    skip_ocr: true,
    skip_vlm: true,
    image_analysis_acknowledged: false,
  });
  const [error, setError] = useState<string | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const [debouncedUrl, setDebouncedUrl] = useState(form.seed_url);
  const alfaCapability = useQuery({
    queryKey: ["capabilities", "alfa", "local-login"],
    queryFn: api.getAlfaCapability,
  });
  const localAnalysisCapability = useQuery({
    queryKey: ["capabilities", "local-analysis", "local-login"],
    queryFn: api.getLocalAnalysisCapability,
    retry: false,
  });

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedUrl(form.seed_url), 250);
    return () => window.clearTimeout(timer);
  }, [form.seed_url]);

  const preview = useQuery({
    queryKey: ["scope-preview", debouncedUrl, form.whole_host, "local-login"],
    queryFn: () => api.scopePreview(debouncedUrl, form.whole_host),
    enabled: Boolean(debouncedUrl.trim()),
  });

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  useEffect(() => {
    if (
      alfaCapability.data?.available === false &&
      form.scan_engine !== "axe"
    ) {
      setForm((previous) => ({ ...previous, scan_engine: "axe" }));
    }
  }, [alfaCapability.data?.available, form.scan_engine]);

  useEffect(() => {
    if (localAnalysisCapability.data?.vision.available === false && !form.skip_vlm) {
      setForm((previous) => ({ ...previous, skip_vlm: true }));
    }
  }, [form.skip_vlm, localAnalysisCapability.data?.vision.available]);

  const create = useMutation({
    mutationFn: (payload: LocalLoginScanPayload) =>
      api.createLocalLoginScan(payload),
    onSuccess: ({ scan_id }) =>
      navigate(`/scans/new?mode=login&scan=${scan_id}`, { replace: true }),
    onError: (reason: unknown) =>
      setError(reason instanceof Error ? reason.message : String(reason)),
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    let parsedSeed: URL;
    try {
      parsedSeed = new URL(form.seed_url.trim());
    } catch {
      setError("Enter the HTTPS page you want Axcess to open before sign-in.");
      return;
    }
    if (
      parsedSeed.protocol !== "https:" ||
      parsedSeed.username ||
      parsedSeed.password ||
      parsedSeed.search ||
      parsedSeed.hash
    ) {
      setError("Use an HTTPS URL without credentials, a query, or a fragment.");
      return;
    }
    if (!authorized) {
      setError(
        "Confirm that the site owner authorized this accessibility scan.",
      );
      return;
    }
    if (!form.skip_ocr && !form.image_analysis_acknowledged) {
      setError(
        "Confirm how protected images and extracted text will be stored before enabling image analysis.",
      );
      return;
    }
    create.mutate({
      ...form,
      seed_url: parsedSeed.toString(),
      approved_auth_origins: [],
      authorization_acknowledged: true,
    });
  };

  const update = <K extends keyof typeof form>(
    key: K,
    value: (typeof form)[K],
  ) => setForm((previous) => ({ ...previous, [key]: value }));

  return (
    <>
      {showSteps && <ProtectedScanSteps current="scope" className="mb-5" />}
      <Card className="max-w-3xl p-5">
        <div className="mb-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-umich-blue">
            Direct local login
          </p>
          <h2 className="mt-1 text-xl font-semibold text-fg">
            Open browser, sign in, then scan
          </h2>
          <p className="mt-2 text-sm text-fg-muted">
            Choose the scan settings first. Axcess will then open visible
            Chromium so you can complete the password, passkey, or 2FA flow
            yourself.
          </p>
        </div>

        {error && (
          <div
            ref={errorRef}
            role="alert"
            tabIndex={-1}
            className="mb-4 flex items-start gap-3 rounded-xs border border-sev-critical/40 bg-sev-critical-bg p-4 text-sm text-sev-critical"
          >
            <AlertOctagon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
            <div>{error}</div>
          </div>
        )}

        <form onSubmit={submit} className="flex flex-col gap-5">
          <label className="flex flex-col gap-1.5">
            <span className="text-base font-semibold text-fg">
              Page to scan after login
            </span>
            <input
              id="local-login-seed"
              type="url"
              inputMode="url"
              required
              autoFocus
              value={form.seed_url}
              onChange={(event) => update("seed_url", event.target.value)}
              placeholder="https://umich.instructure.com/courses/"
              className="min-h-target rounded-xs border-2 border-border bg-surface px-4 py-3 text-base text-fg focus:border-umich-blue focus:outline-none"
            />
            <span className="text-xs text-fg-muted">
              Enter the protected application page to open before sign-in. For
              U-M Canvas, use https://umich.instructure.com/courses/ or a
              permitted course URL.
            </span>
            {debouncedUrl && preview.data && (
              <span
                aria-live="polite"
                className="mt-1 flex flex-wrap items-center gap-1 text-xs text-fg-muted"
              >
                {preview.data.error ? (
                  <span className="text-sev-critical">
                    {preview.data.error}
                  </span>
                ) : preview.data.whole_host ? (
                  <>
                    <strong className="text-fg">Scope:</strong> entire approved
                    host{" "}
                    <code className="rounded bg-surface-muted px-1">
                      {preview.data.host}
                    </code>
                  </>
                ) : (
                  <>
                    <strong className="text-fg">Scope:</strong>
                    <code className="rounded bg-surface-muted px-1">
                      {preview.data.host}
                      {preview.data.path_prefix}
                    </code>
                    {preview.data.auto_slash_added && (
                      <span>(trailing slash added automatically)</span>
                    )}
                  </>
                )}
              </span>
            )}
          </label>

          <section
            aria-labelledby="login-profile-title"
            className="rounded-xs border border-umich-blue/25 bg-umich-blue/5 p-4"
          >
            <h2 id="login-profile-title" className="font-semibold text-fg">
              Balanced accessibility scan
            </h2>
            <p className="mt-1 text-sm text-fg-muted">
              WCAG 2.2 {form.axe_level} against the authenticated, rendered
              site. The temporary browser session stays in memory and is
              destroyed after the scan.
            </p>
            <ul
              className="mt-3 grid gap-2 text-sm sm:grid-cols-2"
              aria-label="Included tests"
            >
              {[
                form.scan_engine === "both"
                  ? "axe-core and Siteimprove Alfa rules"
                  : form.scan_engine === "alfa"
                    ? "Siteimprove Alfa ACT rules"
                    : "axe-core DOM rules",
                form.skip_keyboard
                  ? "Keyboard-exit checks skipped"
                  : "Keyboard-exit checks",
                form.skip_responsive
                  ? "Responsive checks skipped"
                  : "Responsive and zoom checks",
                form.skip_ocr
                  ? "Image text analysis skipped"
                  : form.skip_vlm
                    ? "Local OCR image-text analysis"
                    : "Local OCR and loopback VLM analysis",
                `Up to ${form.max_pages.toLocaleString()} pages`,
                `${form.workers} concurrent authenticated ${form.workers === 1 ? "tab" : "tabs"}`,
              ].map((label) => (
                <li key={label} className="flex items-start gap-2">
                  <Check
                    className="mt-0.5 h-4 w-4 shrink-0 text-umich-blue"
                    aria-hidden
                  />
                  <span>{label}</span>
                </li>
              ))}
            </ul>
          </section>

          <details className="rounded-xs border border-border bg-surface">
            <summary className="flex min-h-target cursor-pointer items-center gap-2 px-4 py-3 font-semibold text-fg">
              <Settings2 className="h-4 w-4 text-umich-blue" aria-hidden />
              Advanced settings
            </summary>
            <div className="space-y-4 border-t border-border p-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <LoginNumberField
                  label="Max pages"
                  value={form.max_pages}
                  min={1}
                  max={2500}
                  onChange={(value) => update("max_pages", value)}
                />
                <LoginNumberField
                  label="Max depth"
                  value={form.max_depth}
                  min={1}
                  max={20}
                  onChange={(value) => update("max_depth", value)}
                />
                <LoginNumberField
                  label="Requests/sec"
                  value={form.rps}
                  min={0.1}
                  max={5}
                  step={0.1}
                  onChange={(value) => update("rps", value)}
                />
                <LoginNumberField
                  label="Workers"
                  value={form.workers}
                  min={1}
                  max={4}
                  onChange={(value) => update("workers", value)}
                />
              </div>
              <p className="text-xs text-fg-muted">
                Workers open concurrent tabs inside the same temporary,
                authenticated browser session. Two is recommended; four is
                the safety maximum for login and 2FA scans.
              </p>

              <fieldset className="rounded-xs border border-border p-3">
                <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
                  Options
                </legend>
                <div className="mb-3 mt-1">
                  <label
                    htmlFor="local-login-axe-level"
                    className="block text-sm font-medium text-fg"
                  >
                    Conformance target
                  </label>
                  <p
                    id="local-login-axe-level-hint"
                    className="mb-1.5 text-xs text-fg-muted"
                  >
                    Choose the WCAG 2.2 level applied by the selected DOM
                    engines. AA is recommended.
                  </p>
                  <select
                    id="local-login-axe-level"
                    aria-describedby="local-login-axe-level-hint"
                    value={form.axe_level}
                    onChange={(event) =>
                      update(
                        "axe_level",
                        event.target
                          .value as LocalLoginScanPayload["axe_level"],
                      )
                    }
                    className="min-h-target w-full rounded-xs border border-border bg-surface px-3 py-2 text-sm text-fg"
                  >
                    <option value="A">WCAG 2.2 — Level A (minimum)</option>
                    <option value="AA">
                      WCAG 2.2 — Level AA (recommended)
                    </option>
                    <option value="AAA">
                      WCAG 2.2 — Level AAA (strictest)
                    </option>
                  </select>
                </div>

                <fieldset className="mb-3 rounded-xs border border-border p-3">
                  <legend className="px-1 text-sm font-medium text-fg">
                    Scan engine
                  </legend>
                  <p
                    id="local-login-engine-hint"
                    className="mb-2 text-xs text-fg-muted"
                  >
                    Choose axe-core, Siteimprove Alfa, or both. Alfa receives a
                    one-use in-memory copy of the temporary signed-in browser
                    state; it is never saved to disk.
                  </p>
                  <div
                    className="space-y-2"
                    role="radiogroup"
                    aria-describedby="local-login-engine-hint"
                  >
                    <EngineChoice
                      value="axe"
                      selected={form.scan_engine}
                      onChange={(engine) => update("scan_engine", engine)}
                      label="axe-core"
                      hint="Runs directly in the temporary authenticated Chromium session."
                    />
                    <EngineChoice
                      value="both"
                      selected={form.scan_engine}
                      onChange={(engine) => update("scan_engine", engine)}
                      disabled={alfaCapability.data?.available === false}
                      label="axe-core + Siteimprove Alfa"
                      hint="Runs two independent DOM engines against the signed-in site for broader evidence."
                    />
                    <EngineChoice
                      value="alfa"
                      selected={form.scan_engine}
                      onChange={(engine) => update("scan_engine", engine)}
                      disabled={alfaCapability.data?.available === false}
                      label="Siteimprove Alfa only"
                      hint="Runs Alfa ACT rules using the temporary authenticated session."
                    />
                  </div>
                  {alfaCapability.isLoading && (
                    <p className="mt-2 text-xs text-fg-muted">
                      Checking Alfa availability…
                    </p>
                  )}
                  {alfaCapability.data?.available === false && (
                    <p className="mt-2 text-xs text-sev-major">
                      Alfa is unavailable: {alfaCapability.data.reason}
                    </p>
                  )}
                </fieldset>

                <div className="mt-1 space-y-1">
                  <Checkbox
                    checked={form.whole_host}
                    onChange={(value) => update("whole_host", value)}
                    label="Crawl the entire approved host"
                    hint="Ignores the URL path scope, but never leaves the exact signed-in website origin."
                  />
                  <Checkbox
                    checked={false}
                    onChange={() => undefined}
                    disabled
                    label="Follow links on subdomains"
                    hint="Unavailable: authenticated scans are restricted to one exact approved origin."
                  />
                  <Checkbox
                    checked={false}
                    onChange={() => undefined}
                    disabled
                    label="Fast crawl — skip browser rendering (static only)"
                    hint="Unavailable: the temporary signed-in browser is required for every protected page."
                  />
                  <Checkbox
                    checked
                    onChange={() => undefined}
                    disabled
                    tone="warning"
                    label="Ignore robots.txt"
                    hint="Required for this explicitly authorized authenticated evaluation; normal scope and read-only request limits still apply."
                  />
                  <Checkbox
                    checked={!form.skip_ocr}
                    onChange={(enabled) => {
                      update("skip_ocr", !enabled);
                      if (!enabled) update("skip_vlm", true);
                    }}
                    disabled={localAnalysisCapability.data?.ocr.available === false}
                    label="Detect text inside images with bundled OCR"
                    hint="Tesseract runs locally with up to two workers. Protected images are retrieved through the signed-in browser; only redacted results are retained."
                  />
                  <Checkbox
                    checked={!form.skip_vlm}
                    onChange={(enabled) => update("skip_vlm", !enabled)}
                    disabled={
                      form.skip_ocr ||
                      localAnalysisCapability.data?.vision.available === false
                    }
                    label="Classify image text with a local vision model"
                    hint={
                      form.skip_ocr
                        ? "Turn on OCR first."
                        : localAnalysisCapability.data?.vision.available
                          ? `${localAnalysisCapability.data.vision.model} is installed and will run only through loopback Ollama.`
                          : localAnalysisCapability.data?.vision.reason ??
                            "Checking whether the configured local vision model is ready…"
                    }
                  />
                  {!form.skip_vlm && (
                    <div
                      className="rounded-xs border border-umich-maize/70 bg-umich-maize/10 p-3 text-sm text-fg"
                      role="status"
                      aria-live="polite"
                    >
                      <p className="font-semibold">
                        Local AI—no automatic model downloads
                      </p>
                      <p className="mt-1 text-xs text-fg-muted">
                        No model download will start with this scan. Axcess uses
                        only the vision model already installed in loopback
                        Ollama; the option stays disabled when it is missing.
                        Protected image evidence never goes to a cloud model,
                        but Ollama will use additional unified memory during
                        analysis and may temporarily slow other apps.
                      </p>
                    </div>
                  )}
                  <Checkbox
                    checked={form.skip_keyboard}
                    onChange={(value) => update("skip_keyboard", value)}
                    label="Skip keyboard-exit checks"
                    hint="Saves time, but removes automated keyboard-navigation leads from the report."
                  />
                  <Checkbox
                    checked={form.skip_responsive}
                    onChange={(value) => update("skip_responsive", value)}
                    label="Skip responsive & zoom checks"
                    hint="Saves time, but removes 320px reflow, 200% zoom, and text-spacing checks."
                  />
                </div>
              </fieldset>
            </div>
          </details>

          {!form.skip_ocr && (
            <div className="rounded-xs border border-sev-major/50 bg-sev-major-bg/30 p-3">
              <Checkbox
                checked={form.image_analysis_acknowledged}
                onChange={(value) =>
                  update("image_analysis_acknowledged", value)
                }
                tone="warning"
                label="Store protected image-analysis evidence locally"
                hint={
                  form.skip_vlm
                    ? "Protected image blobs and extracted OCR text will be stored in this computer’s local Axcess evidence directory and database."
                    : "Protected image blobs, OCR text, and VLM rationale will be stored locally. Image data is sent only to the verified loopback Ollama endpoint."
                }
              />
            </div>
          )}

          <label className="flex min-h-11 items-start gap-3 text-sm text-fg">
            <input
              type="checkbox"
              checked={authorized}
              onChange={(event) => setAuthorized(event.target.checked)}
              className="mt-1 size-5 rounded border-border text-umich-blue focus:ring-2 focus:ring-umich-blue/40"
            />
            <span>
              I have authorization from the site owner and will use a
              least-privilege test account.
            </span>
          </label>

          <div className="rounded-md border border-border bg-surface-subtle p-4 text-sm text-fg-muted">
            During sign-in, the visible browser may follow public HTTPS
            redirects to U-M Shibboleth, Duo, or another identity provider. Once
            you confirm the application page, Axcess locks the crawler to that
            website and read-only page requests. The login session stays in
            memory and is destroyed when the scan ends. Report evidence is
            stored in your local Axcess database.
          </div>

          <div className="flex flex-wrap gap-3">
            <Button
              type="submit"
              variant="primary"
              size="lg"
              disabled={
                create.isPending ||
                !form.seed_url.trim() ||
                (!form.skip_ocr && !form.image_analysis_acknowledged)
              }
            >
              {create.isPending ? "Opening browser…" : "Open sign-in browser"}
            </Button>
            {showSteps && (
              <Link
                to="/scans/new"
                className="inline-flex min-h-11 items-center px-3 text-sm font-semibold text-umich-blue underline underline-offset-2"
              >
                Use a public scan
              </Link>
            )}
          </div>
        </form>
      </Card>
    </>
  );
}

function LoginNumberField({
  label,
  value,
  onChange,
  min,
  max,
  step,
  disabled = false,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
      {label}
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
        className="min-h-target rounded-xs border border-border bg-surface px-3 py-2 text-base font-normal normal-case tracking-normal text-fg disabled:cursor-not-allowed disabled:opacity-60"
      />
    </label>
  );
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
        title: "Checking the signed-in page",
        detail:
          "Axcess is confirming that the browser returned to the approved application.",
      },
      scanning: {
        title: "Scanning in the background",
        detail: status.data?.browser_backgrounded
          ? "The signed-in Chromium window has been moved out of the way while Axcess reuses its in-memory session. You can keep working, but quitting Chromium will stop the scan."
          : "Axcess is reusing the signed-in browser session in the background. You can keep working, but closing Chromium will stop the scan.",
      },
      authentication_required: {
        title: "Sign-in could not be confirmed",
        detail:
          status.data?.error ??
          "Start again and include every exact sign-in origin.",
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
        <p className="text-xs font-semibold uppercase tracking-wide text-umich-blue">
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

        {state === "awaiting_authentication" && (
          <div className="mt-6 rounded-md border-2 border-umich-blue bg-umich-blue/5 p-5">
            <h3 className="font-semibold text-fg">Finished signing in?</h3>
            <p className="mt-1 text-sm text-fg-muted">
              Make sure the visible browser shows the protected application—not
              the U-M or Duo login screen.
            </p>
            <Button
              className="mt-4"
              onClick={() => confirm.mutate()}
              disabled={confirm.isPending}
            >
              {confirm.isPending
                ? "Checking sign-in…"
                : "I’m signed in — start scan"}
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
                  The visible signed-in browser follows the page being tested.
                  This panel updates without reloading or scrolling the page.
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
                <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
                  <Clock3 className="h-4 w-4" aria-hidden /> Estimated time
                </p>
                <p className="mt-2 text-sm font-semibold text-fg">
                  {formatScanEta(scanActivity.data?.progress?.eta)}
                </p>
              </div>
              <div className="rounded-xs border border-border bg-surface p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">
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
