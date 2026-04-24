import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertOctagon } from "lucide-react";
import { api } from "../api/client";
import { Button, Card, PageHeader } from "../components/ui";
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
    js_eager: false,
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
          <label className="flex flex-col gap-1">
            <span className="text-sm font-semibold text-fg">Seed URL</span>
            <input
              type="url"
              required
              autoFocus
              placeholder="https://example.com/section/"
              value={form.url}
              onChange={(e) => update("url", e.target.value)}
              className="rounded-xs border border-border bg-surface px-3 py-2 text-sm text-fg focus:border-umich-blue focus:outline-none"
            />
            <span className="text-xs text-fg-muted">
              Must start with http:// or https://. By default the crawl
              stays under this URL's path — e.g.{" "}
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
            <div className="mt-1 space-y-1.5">
              <Checkbox
                checked={form.whole_host}
                onChange={(v) => update("whole_host", v)}
                label="Crawl the entire host (ignore the path scope)"
              />
              <Checkbox
                checked={form.include_subdomain}
                onChange={(v) => update("include_subdomain", v)}
                label="Follow links on subdomains"
              />
              <Checkbox
                checked={form.js_eager}
                onChange={(v) => update("js_eager", v)}
                label="Use real browser (Playwright) for every page — slower but handles SPAs / Cloudflare"
              />
              <Checkbox
                checked={form.ignore_robots}
                onChange={(v) => update("ignore_robots", v)}
                label="Ignore robots.txt (authorized testing only)"
              />
              <Checkbox
                checked={form.skip_ocr}
                onChange={(v) => update("skip_ocr", v)}
                label="Skip OCR"
              />
              <Checkbox
                checked={form.skip_vlm}
                onChange={(v) => update("skip_vlm", v)}
                label="Skip VLM classification"
              />
            </div>
          </fieldset>

          <div className="flex gap-2">
            <Button
              type="submit"
              variant="primary"
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
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="rounded-xs border border-border bg-surface px-2 py-1.5 text-sm font-normal normal-case tracking-normal text-fg focus:border-umich-blue focus:outline-none"
      />
    </label>
  );
}

function Checkbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex items-start gap-2 text-sm text-fg">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 rounded-xs border-border text-umich-blue focus:ring-umich-blue"
      />
      <span>{label}</span>
    </label>
  );
}
