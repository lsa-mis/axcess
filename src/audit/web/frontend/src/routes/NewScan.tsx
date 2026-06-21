import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertOctagon } from "lucide-react";
import { api } from "../api/client";
import { Button, Card, Checkbox, PageHeader } from "../components/ui";
import type { NewScanPayload } from "../api/types";

/** Start a scan: URL input + scope preview + advanced toggles. */
export default function NewScanRoute() {
  const navigate = useNavigate();
  const [form, setForm] = useState<NewScanPayload>({
    url: "",
    max_pages: 100,
    max_depth: 10,
    rps: 2.0,
    workers: 4,
    include_subdomain: false,
    whole_host: false,
    ignore_robots: false,
    skip_ocr: false,
    skip_vlm: false,
    // Full rendering is the default — three of the four pipelines (axe,
    // keyboard, responsive) need the live DOM. `static_only` is the
    // opt-out fast path, exposed as a warning-toned checkbox below.
    static_only: false,
    // Axe is on by default — the WCAG 2.x AA scan is one of the main
    // reasons most users reach for this tool. The hidden cost is ~50-150 ms
    // per Playwright-rendered page; the form exposes a toggle below.
    skip_axe: false,
    skip_keyboard: false,
    skip_responsive: false,
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

  const create = useMutation({
    mutationFn: () => api.createScan(form),
    onSuccess: ({ scan_id }) => navigate(`/scans/${scan_id}`),
    onError: (e) =>
      setSubmitError(e instanceof Error ? e.message : String(e)),
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
        subtitle="Start a crawl against a public URL. Runs in the background — the scan page refreshes every 2 seconds while it's active."
      />

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
            <span className="text-base font-semibold text-fg">Seed URL</span>
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
                  <span className="text-sev-critical">{preview.data.error}</span>
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
              max={16}
              onChange={(v) => update("workers", v)}
            />
          </div>

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
              <p id="axe-level-hint" className="mb-1.5 text-xs text-fg-muted">
                The WCAG 2.2 level to check against. AA is the standard
                legal/compliance target; AAA adds the strictest rules (e.g.
                enhanced 7:1 contrast).
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
                <option value="AA">WCAG 2.2 — Level AA (recommended)</option>
                <option value="AAA">WCAG 2.2 — Level AAA (strictest)</option>
              </select>
            </div>

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
                hint="5–10× faster, but disables the axe, keyboard-trap, and responsive checks on every statically-fetched page."
              />
              <Checkbox
                tone="warning"
                checked={form.ignore_robots}
                onChange={(v) => update("ignore_robots", v)}
                label="Ignore robots.txt"
                hint="Authorized testing only. The scan will be flagged in its config and audit log."
              />
              <Checkbox
                checked={form.skip_ocr}
                onChange={(v) => update("skip_ocr", v)}
                label="Skip OCR"
                hint="Faster, but findings won't include image-text extraction."
              />
              <Checkbox
                checked={form.skip_vlm}
                onChange={(v) => update("skip_vlm", v)}
                label="Skip VLM classification"
                hint="Faster, but findings won't include the essential / decorative / logo verdict."
              />
              {/* Axe is opt-out, not opt-in — most users reaching for
                  this tool want the WCAG 2.x AA scan as the primary
                  output. We surface a "Skip" rather than an "Enable"
                  to honor that default. Same for the keyboard and
                  responsive probes below. */}
              <Checkbox
                checked={form.skip_axe}
                onChange={(v) => update("skip_axe", v)}
                label="Skip WCAG axe scan"
                hint="Faster (~50-150 ms / page saved), but findings won't include the WCAG 2.x AA DOM checks."
              />
              <Checkbox
                checked={form.skip_keyboard}
                onChange={(v) => update("skip_keyboard", v)}
                label="Skip keyboard-trap probe"
                hint="Saves ~1–3s per page; loses the only automated WCAG 2.1.2 (Level A) coverage."
              />
              <Checkbox
                checked={form.skip_responsive}
                onChange={(v) => update("skip_responsive", v)}
                label="Skip responsive & zoom checks"
                hint="Saves ~1–2s per page; loses 320px reflow, 200% zoom, and text-spacing coverage (SC 1.4.4 / 1.4.10 / 1.4.12)."
              />
            </div>
          </fieldset>

          {/* Submit + Cancel. The submit is the page's primary CTA
              (`size="lg"`); Cancel stays at the default `md` to make the
              hierarchy unambiguous — the user shouldn't have to read the
              colors to know which one commits the form. */}
          <div className="flex flex-wrap gap-3">
            <Button
              type="submit"
              variant="primary"
              size="lg"
              disabled={create.isPending || !form.url.trim()}
            >
              {create.isPending ? "Starting…" : "Start crawl"}
            </Button>
            <Button type="button" onClick={() => navigate("/scans")}>
              Cancel
            </Button>
          </div>
        </form>
      </Card>
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

// `Checkbox` lives in components/ui.tsx — see that file for the 44×44
// hit-target rationale. Removed the local copy that shipped with a 16×16
// native input (failed SC 2.5.5 AAA + SC 2.5.8 AA).
