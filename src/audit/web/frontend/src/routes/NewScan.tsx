import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertOctagon,
  Check,
  Globe2,
  LockKeyhole,
  Settings2,
} from "lucide-react";
import { api } from "../api/client";
import {
  Button,
  Card,
  Checkbox,
  LinkButton,
  PageHeader,
} from "../components/ui";
import LocalLoginScan from "../components/LocalLoginScan";
import type { NewScanPayload } from "../api/types";
import EngineChoice from "./EngineChoice";

/** Start a scan: URL input + scope preview + advanced toggles. */
export default function NewScanRoute() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const loginSelected = searchParams.get("mode") === "login";
  const [form, setForm] = useState<NewScanPayload>({
    url: searchParams.get("url") ?? "",
    max_pages: 2500,
    max_depth: 10,
    rps: 2.0,
    workers: 8,
    include_subdomain: false,
    whole_host: false,
    ignore_robots: false,
    skip_ocr: false,
    // The recommended profile keeps deterministic OCR but leaves repeated
    // model calls off. They are useful expert-review leads, not prerequisites
    // for the core accessibility report, and can dominate scan time.
    skip_vlm: true,
    // Full rendering is the default — three of the four pipelines (axe,
    // keyboard, responsive) need the live DOM. `static_only` is the
    // opt-out fast path, exposed as a warning-toned checkbox below.
    static_only: false,
    show_browser: false,
    // axe runs inside the browser Axcess already opened. Alfa remains an
    // explicit corroboration option because it starts a second browser pass
    // for every page and is therefore substantially slower.
    scan_engine: "axe",
    skip_keyboard: false,
    skip_responsive: false,
    skip_semantic: true,
    skip_focus: false,
    skip_visual: true,
    axe_level: "AA",
  });
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Debounced scope preview. Driven by React Query — effectively a
  // "derived state" that rerenders when url or whole_host changes.
  const [debouncedUrl, setDebouncedUrl] = useState(form.url);
  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedUrl(form.url), 250);
    return () => window.clearTimeout(t);
  }, [form.url]);
  const preview = useQuery({
    queryKey: ["scope-preview", debouncedUrl, form.whole_host],
    queryFn: () => api.scopePreview(debouncedUrl, form.whole_host),
    enabled: Boolean(debouncedUrl.trim()),
  });
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
    if (
      localAnalysisCapability.data?.semantic.available === false &&
      !form.skip_semantic
    ) {
      setForm((previous) => ({ ...previous, skip_semantic: true }));
    }
  }, [
    form.skip_semantic,
    form.skip_vlm,
    localAnalysisCapability.data?.semantic.available,
    localAnalysisCapability.data?.vision.available,
  ]);

  const create = useMutation({
    mutationFn: () => api.createScan(form),
    onSuccess: ({ scan_id }) => navigate(`/scans/${scan_id}`),
    onError: (e) => setSubmitError(e instanceof Error ? e.message : String(e)),
  });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    create.mutate();
  };

  const update = <K extends keyof NewScanPayload>(
    key: K,
    value: NewScanPayload[K],
  ) => setForm((prev) => ({ ...prev, [key]: value }));

  return (
    <>
      <PageHeader
        crumbs={[{ label: "Scans", to: "/scans" }, { label: "New scan" }]}
        title="New scan"
        subtitle="Choose a public website or sign in yourself before Axcess scans a protected website."
      />

      <section className="mb-6 max-w-4xl" aria-labelledby="scan-type-title">
        <p
          id="scan-type-title"
          className="mb-3 text-xs font-semibold uppercase tracking-wide text-fg-subtle"
        >
          Choose how the site opens
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          <Card
            className={
              loginSelected
                ? "p-5"
                : "border-2 border-umich-blue bg-umich-blue/5 p-5"
            }
            aria-current={loginSelected ? undefined : "true"}
          >
            <div className="flex items-start gap-3">
              <Globe2
                className="mt-0.5 h-6 w-6 shrink-0 text-umich-blue"
                aria-hidden
              />
              <div>
                <h2 className="font-semibold text-fg">Public website</h2>
                <p className="mt-1 text-sm text-fg-muted">
                  Start immediately. No account, password, or 2FA is required.
                </p>
                {loginSelected ? (
                  <LinkButton
                    to="/scans/new"
                    variant="secondary"
                    className="mt-3"
                  >
                    Select public website
                  </LinkButton>
                ) : (
                  <span className="mt-3 inline-flex rounded-full bg-umich-blue px-2.5 py-1 text-xs font-semibold text-white">
                    Selected
                  </span>
                )}
              </div>
            </div>
          </Card>

          <Card
            className={
              loginSelected
                ? "border-2 border-umich-blue bg-umich-blue/5 p-5"
                : "p-5"
            }
            aria-current={loginSelected ? "true" : undefined}
          >
            <div className="flex items-start gap-3">
              <LockKeyhole
                className="mt-0.5 h-6 w-6 shrink-0 text-umich-blue"
                aria-hidden
              />
              <div className="min-w-0">
                <h2 className="font-semibold text-fg">Login or 2FA website</h2>
                <p className="mt-1 text-sm text-fg-muted">
                  Open a visible protected browser, sign in yourself, and scan
                  only after the approved application page is confirmed.
                </p>
                {loginSelected ? (
                  <span className="mt-3 inline-flex rounded-full bg-umich-blue px-2.5 py-1 text-xs font-semibold text-white">
                    Selected
                  </span>
                ) : protectedCapability.isLoading ? (
                  <p className="mt-3 text-sm text-fg-muted" role="status">
                    Checking availability…
                  </p>
                ) : protectedCapability.data?.available ||
                  protectedCapability.data?.local_available ? (
                  <LinkButton
                    to="/scans/new?mode=login"
                    variant="secondary"
                    className="mt-3"
                  >
                    Select login / 2FA website
                  </LinkButton>
                ) : (
                  <div className="mt-3 text-sm text-fg-muted" role="status">
                    <p>
                      {protectedCapability.data?.reason ??
                        "Protected sign-in scanning is unavailable on this server."}
                    </p>
                    <LinkButton
                      to="/scans/new?mode=login"
                      variant="secondary"
                      className="mt-3"
                    >
                      View setup and workflow
                    </LinkButton>
                  </div>
                )}
              </div>
            </div>
          </Card>
        </div>
      </section>

      {loginSelected ? (
        <LocalLoginScan showSteps={false} />
      ) : (
        <>
          {submitError && (
            <Card className="mb-4 flex items-start gap-3 border-sev-critical/40 bg-sev-critical-bg p-4 text-sm text-sev-critical">
              <AlertOctagon className="mt-0.5 h-5 w-5" aria-hidden />
              <div>{submitError}</div>
            </Card>
          )}

          <Card className="max-w-3xl p-5">
            <form onSubmit={onSubmit} className="flex flex-col gap-5">
              {/* The seed URL is the most important field on the most
              important form in the app — there is exactly one of it,
              and the user cannot proceed without it. Treat it as the
              page's hero input: bigger label, base font size, taller
              control. The smaller secondary controls (Max pages, etc.)
              create the visual contrast that says "this one matters
              first." */}
              <label className="flex flex-col gap-1.5">
                <span className="text-base font-semibold text-fg">
                  Seed URL
                </span>
                <input
                  type="url"
                  required
                  autoFocus
                  placeholder="https://example.com/section/"
                  value={form.url}
                  onChange={(e) => update("url", e.target.value)}
                  className="min-h-target rounded-xs border-2 border-border bg-surface px-4 py-3 text-base text-fg focus:border-umich-blue focus:outline-none"
                />
                <span className="text-xs text-fg-muted">
                  Must start with http:// or https://. By default the crawl
                  stays under this URL&rsquo;s path — e.g.{" "}
                  <code className="rounded bg-surface-muted px-1">
                    /section/
                  </code>{" "}
                  only follows that section.
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
                        <strong className="text-fg">Scope:</strong> entire host{" "}
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
                          <span>
                            (auto-added trailing slash:{" "}
                            <code className="rounded bg-surface-muted px-1">
                              {preview.data.normalized_url}
                            </code>
                            )
                          </span>
                        )}
                      </>
                    )}
                  </span>
                )}
              </label>

              <section
                aria-labelledby="standard-profile-title"
                className="rounded-xs border border-umich-blue/25 bg-umich-blue/5 p-4"
              >
                <h2
                  id="standard-profile-title"
                  className="font-semibold text-fg"
                >
                  Balanced accessibility scan
                </h2>
                <p className="mt-1 text-sm text-fg-muted">
                  WCAG 2.2 AA against the rendered site, with fast deterministic
                  checks first. Slower corroboration and local-AI review remain
                  available under Advanced settings.
                </p>
                <ul
                  className="mt-3 grid gap-2 text-sm sm:grid-cols-2"
                  aria-label="Included tests"
                >
                  {[
                    form.scan_engine === "both"
                      ? "axe-core and Siteimprove Alfa"
                      : form.scan_engine === "alfa"
                        ? "Siteimprove Alfa"
                        : "axe-core",
                    "Keyboard, focus, and responsive checks",
                    form.skip_ocr
                      ? "Image analysis skipped"
                      : form.skip_vlm
                        ? "Image text detection (OCR)"
                        : "Image text detection and local-AI review",
                    `Up to ${form.max_pages.toLocaleString()} pages`,
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
                {alfaCapability.isLoading && (
                  <p className="mt-3 text-xs text-fg-muted" role="status">
                    Checking Siteimprove Alfa availability…
                  </p>
                )}
                {alfaCapability.data?.available === false && (
                  <p className="mt-3 text-xs text-sev-major" role="status">
                    Alfa is unavailable, so this scan will continue with
                    axe-core: {alfaCapability.data.reason}
                  </p>
                )}
              </section>

              <details className="rounded-xs border border-border bg-surface">
                <summary className="flex min-h-target cursor-pointer items-center gap-2 px-4 py-3 font-semibold text-fg">
                  <Settings2 className="h-4 w-4 text-umich-blue" aria-hidden />
                  Advanced settings
                </summary>
                <div className="space-y-4 border-t border-border p-4">
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <NumberField
                      label="Max pages"
                      value={form.max_pages}
                      min={1}
                      max={10000}
                      onChange={(v) => update("max_pages", v)}
                    />
                    <NumberField
                      label="Max depth"
                      value={form.max_depth}
                      min={1}
                      max={20}
                      onChange={(v) => update("max_depth", v)}
                    />
                    <NumberField
                      label="Requests/sec"
                      value={form.rps}
                      min={0.1}
                      max={50}
                      step={0.1}
                      onChange={(v) => update("rps", v)}
                    />
                    <NumberField
                      label="Workers"
                      value={form.workers}
                      min={1}
                      max={32}
                      onChange={(v) => update("workers", v)}
                    />
                  </div>
                  <p className="text-xs text-fg-muted">
                    Workers control local crawl and analysis concurrency; an
                    M4 Pro can comfortably start at 8 and scale up to 32.
                    Requests/sec limits traffic sent to the target site, so
                    increase it only when the site owner has approved the
                    additional load.
                  </p>

                  <fieldset className="rounded-xs border border-border p-3">
                    <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
                      Options
                    </legend>

                    {/* Conformance target — the standard to check against. Drives the
                axe rule set (tags_for_level) and frames the report. AA is the
                default because it's the near-universal legal/compliance
                target (Section 508, EN 301 549, ADA all map to WCAG AA). */}
                    <div className="mb-3 mt-1">
                      <label
                        htmlFor="axe-level"
                        className="block text-sm font-medium text-fg"
                      >
                        Conformance target
                      </label>
                      <p
                        id="axe-level-hint"
                        className="mb-1.5 text-xs text-fg-muted"
                      >
                        The WCAG 2.2 level to check against. AA is the standard
                        legal/compliance target; AAA adds the strictest rules
                        (e.g. enhanced 7:1 contrast).
                      </p>
                      <select
                        id="axe-level"
                        aria-describedby="axe-level-hint"
                        value={form.axe_level}
                        onChange={(e) =>
                          update(
                            "axe_level",
                            e.target.value as NewScanPayload["axe_level"],
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
                        id="scan-engine-hint"
                        className="mb-2 text-xs text-fg-muted"
                      >
                        Choose the DOM rules engine for this report. In
                        both-engine mode, Axcess stores axe-core and Alfa
                        evidence separately; matching rule topics are never
                        silently deduplicated.
                      </p>
                      <div
                        className="space-y-2"
                        role="radiogroup"
                        aria-describedby="scan-engine-hint"
                      >
                        <EngineChoice
                          value="axe"
                          selected={form.scan_engine}
                          onChange={(engine) => {
                            update("scan_engine", engine);
                            if (form.static_only) update("static_only", false);
                          }}
                          label="axe-core"
                          hint="Fast, stable DOM and computed-style checks in Axcess’ Playwright capture."
                        />
                        <EngineChoice
                          value="both"
                          selected={form.scan_engine}
                          onChange={(engine) => {
                            update("scan_engine", engine);
                            if (form.static_only) update("static_only", false);
                          }}
                          disabled={alfaCapability.data?.available === false}
                          label="axe-core + Siteimprove Alfa"
                          hint="Run two independent engines. Slower: Alfa takes a second local browser snapshot per page."
                        />
                        <EngineChoice
                          value="alfa"
                          selected={form.scan_engine}
                          onChange={(engine) => update("scan_engine", engine)}
                          disabled={alfaCapability.data?.available === false}
                          label="Siteimprove Alfa only"
                          hint="ACT means Accessibility Conformance Testing. Each standardized rule checks one specific condition; failures become evidence and “can’t tell” outcomes need an expert decision."
                        />
                      </div>
                      {alfaCapability.data?.available === false && (
                        <p
                          className="mt-2 text-xs text-sev-major"
                          role="status"
                        >
                          Alfa is unavailable: {alfaCapability.data.reason}
                        </p>
                      )}
                    </fieldset>

                    {/* Each checkbox has a per-row 44×44 hit target via the
                shared <Checkbox> primitive. Hints explain the consequence
                of the option in plain language (UD #4 Perceptible Information,
                Nielsen #2 Match between system & real world). */}
                    <div className="mt-1 space-y-1">
                      <Checkbox
                        checked={form.whole_host}
                        onChange={(v) => update("whole_host", v)}
                        label="Crawl the entire host"
                        hint="Ignores the URL path scope — every page on the host is in scope."
                      />
                      <Checkbox
                        checked={form.include_subdomain}
                        onChange={(v) => update("include_subdomain", v)}
                        label="Follow links on subdomains"
                        hint="e.g. links from www.example.com to docs.example.com are followed."
                      />
                      {/* Full rendering is the default; static-only is the
                  warning-toned opt-out because checking it silently
                  drops three pipelines' coverage. */}
                      <Checkbox
                        tone="warning"
                        checked={form.static_only}
                        onChange={(v) => update("static_only", v)}
                        label="Fast crawl — skip browser rendering (static only)"
                        hint={
                          form.scan_engine === "alfa"
                            ? "5–10× faster for Axcess’ crawler. Alfa still opens its own local browser capture for each included page."
                            : "5–10× faster, but it cannot be combined with axe-core. Choose Alfa only or keep Axcess browser rendering enabled."
                        }
                      />
                      {form.static_only && form.scan_engine !== "alfa" && (
                        <p className="px-2 text-xs text-sev-major" role="alert">
                          Static-only mode is incompatible with axe-core. Select
                          Alfa only or turn static-only mode off.
                        </p>
                      )}
                      <Checkbox
                        checked={form.show_browser}
                        onChange={(v) => update("show_browser", v)}
                        disabled={form.static_only}
                        label="Show the scanning browser window"
                        hint={
                          form.static_only
                            ? "Unavailable in static-only mode because Axcess is not rendering pages."
                            : "Leave this off to render invisibly in the background while you use other apps. Turn it on only when you want to watch page navigation; closing it stops browser-based checks."
                        }
                      />
                      <Checkbox
                        tone="warning"
                        checked={form.ignore_robots}
                        onChange={(v) => update("ignore_robots", v)}
                        label="Ignore robots.txt"
                        hint="Authorized testing only. The scan will be flagged in its config and audit log."
                      />
                      <Checkbox
                        checked={!form.skip_ocr}
                        onChange={(enabled) => {
                          update("skip_ocr", !enabled);
                          if (!enabled) update("skip_vlm", true);
                        }}
                        disabled={localAnalysisCapability.data?.ocr.available === false}
                        label="Detect text inside images with bundled OCR"
                        hint={
                          localAnalysisCapability.data?.ocr.available === false
                            ? "Tesseract OCR is not available in this installation."
                            : `Tesseract runs locally with up to ${localAnalysisCapability.data?.ocr.max_workers ?? 2} workers. It does not need an AI model or send images off this computer.`
                        }
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
                            ? "Turn on OCR first; the vision model only reviews images where OCR found text."
                            : localAnalysisCapability.data?.vision.available
                              ? `${localAnalysisCapability.data.vision.model} is installed locally (${formatBytes(localAnalysisCapability.data.vision.installed_size_bytes)}). Runs one at a time through Ollama.`
                              : localAnalysisCapability.data?.vision.reason ??
                                "Checking whether the configured local vision model is ready…"
                        }
                      />
                      <Checkbox
                        checked={form.skip_keyboard}
                        onChange={(v) => update("skip_keyboard", v)}
                        label="Skip keyboard-exit checks"
                        hint="Saves ~1–3s per page. The check attempts both Tab and Shift+Tab repeatedly; results are review leads, not automatic WCAG 2.1.2 failures."
                      />
                      <Checkbox
                        checked={form.skip_responsive}
                        onChange={(v) => update("skip_responsive", v)}
                        label="Skip responsive & zoom checks"
                        hint="Saves ~1–2s per page; loses 320px reflow, 200% zoom, and text-spacing coverage (SC 1.4.4 / 1.4.10 / 1.4.12)."
                      />
                      <Checkbox
                        checked={form.skip_focus}
                        onChange={(v) => update("skip_focus", v)}
                        label="Skip focus visibility checks"
                        hint="Faster, but loses the browser check for keyboard focus hidden behind sticky or fixed content (SC 2.4.11)."
                      />
                      <Checkbox
                        checked={!form.skip_semantic}
                        onChange={(enabled) => update("skip_semantic", !enabled)}
                        disabled={localAnalysisCapability.data?.semantic.available === false}
                        label="Add semantic review with local AI"
                        hint={
                          localAnalysisCapability.data?.semantic.available
                            ? `Ready. Runs up to ${localAnalysisCapability.data.semantic.checks_per_page} contextual checks per page through local Ollama; results require expert confirmation.`
                            : localAnalysisCapability.data?.semantic.reason ??
                              "Checking whether the required local text models are ready…"
                        }
                      />
                      <Checkbox
                        checked={!form.skip_visual}
                        onChange={(enabled) => update("skip_visual", !enabled)}
                        label="Add visual and motion analysis"
                        hint={
                          localAnalysisCapability.data?.vision.available
                            ? "Adds deterministic motion checks and one local vision-model review per page."
                            : "Adds deterministic motion checks. Vision review will remain unavailable until the configured local vision model is installed."
                        }
                      />
                      {(!form.skip_vlm ||
                        !form.skip_semantic ||
                        (!form.skip_visual &&
                          localAnalysisCapability.data?.vision.available)) && (
                        <div
                          className="rounded-xs border border-umich-maize/70 bg-umich-maize/10 p-3 text-sm text-fg"
                          role="status"
                          aria-live="polite"
                        >
                          <p className="font-semibold">
                            Local AI—no automatic model downloads
                          </p>
                          <p className="mt-1 text-xs text-fg-muted">
                            No model download will start with this scan. Axcess
                            uses only models already installed in local Ollama;
                            unavailable model options stay disabled. Page and
                            image evidence remains on this computer, but Ollama
                            may load several GB into unified memory and make
                            other apps feel slower while analysis is running.
                          </p>
                        </div>
                      )}
                    </div>
                  </fieldset>
                </div>
              </details>

              {/* Submit + Cancel. The submit is the page's primary CTA
              (`size="lg"`); Cancel stays at the default `md` to make the
              hierarchy unambiguous — the user shouldn't have to read the
              colors to know which one commits the form. */}
              <div className="flex flex-wrap gap-3">
                <Button
                  type="submit"
                  variant="primary"
                  size="lg"
                  disabled={
                    create.isPending ||
                    !form.url.trim() ||
                    (form.static_only && form.scan_engine !== "alfa")
                  }
                >
                  {create.isPending ? "Starting scan…" : "Start scan"}
                </Button>
                <Button type="button" onClick={() => navigate("/scans")}>
                  Cancel
                </Button>
              </div>
            </form>
          </Card>
        </>
      )}
    </>
  );
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
      {label}
      {/* min-h-target keeps the input at the SC 2.5.5 floor; px-3 gives
          enough horizontal room for the spinner controls browsers add. */}
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="min-h-target rounded-xs border border-border bg-surface px-3 py-2 text-base font-normal normal-case tracking-normal text-fg focus:border-umich-blue focus:outline-none"
      />
    </label>
  );
}

function formatBytes(value: number | null): string {
  if (!value || value < 1) return "size unavailable";
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  return `${Math.round(value / 1024 ** 2)} MB`;
}

// `Checkbox` lives in components/ui.tsx — see that file for the 44×44
// hit-target rationale. Removed the local copy that shipped with a 16×16
// native input (failed SC 2.5.5 AAA + SC 2.5.8 AA).
