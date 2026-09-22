import { useEffect, useState } from "react";
import type { ScopePreview } from "../../api/types";
import { cn } from "../../lib/cn";
import { SUMMARY } from "./copy";
import { engineName } from "./DefaultSettingsCard";
import type { Capabilities } from "./groupProps";
import { isDefault, isFixed, switchOn, type ScanPolicy, type ScanSettings } from "./scanPolicy";
import type { ScopePreviewState } from "./useScopePreview";

type Chip = { label: string; on: boolean };

function chip(label: string, on: boolean): Chip {
  return { label: on ? label : `${label} off`, on };
}

/**
 * The right-hand rail: what the scan will do, as it stands right now.
 *
 * Everything here is derived from the settings; it holds no state of its own
 * beyond the spoken digest. The visible card is not a live region — it
 * changes on every keystroke — so a screen reader hears one short digest
 * instead, debounced so typing "2500" in Max pages is announced once.
 */
export default function ScanSummaryCard({
  settings,
  policy,
  preview,
  capabilities,
  className,
}: {
  settings: ScanSettings;
  policy: ScanPolicy;
  preview: { state: ScopePreviewState; data: ScopePreview | null };
  capabilities: Capabilities;
  className?: string;
}) {
  const login = policy.mode === "login";
  const checks: Chip[] = [
    chip("Keyboard traps", switchOn(settings, "keyboard") && !settings.static_only),
    ...(isFixed(policy, "skip_focus") ? [] : [chip("Focus visibility", switchOn(settings, "focus") && !settings.static_only)]),
    chip("Responsive & zoom", switchOn(settings, "responsive") && !settings.static_only),
    chip("Click-through", switchOn(settings, "click_through") && !settings.static_only),
    chip("Rendered pages kept", !switchOn(settings, "skip_rendered_storage") && !settings.static_only),
  ];
  const ai: Chip[] = [
    chip("Image text (OCR)", switchOn(settings, "ocr")),
    chip("Vision model", switchOn(settings, "vision")),
    ...(isFixed(policy, "skip_semantic") ? [] : [chip("Wording review", switchOn(settings, "semantic"))]),
    ...(isFixed(policy, "skip_visual") ? [] : [chip("Motion & animation", switchOn(settings, "motion"))]),
  ];
  const countable = [...checks.slice(0, checks.length - 1), ...ai];
  const onCount = countable.filter((item) => item.on).length;
  const total = countable.length;
  const circumference = 138.2;
  const engine = engineName(settings.scan_engine);
  const alfaUnavailable = capabilities.alfa?.available === false && settings.scan_engine !== "axe";

  const site = (() => {
    if (preview.state === "idle") return null;
    if (preview.state === "error" || !preview.data) return null;
    return preview.data.whole_host
      ? { line: `Every page on ${preview.data.host}`, host: preview.data.host }
      : { line: `${preview.data.host}${preview.data.path_prefix}`, host: preview.data.host };
  })();

  const coverageLine =
    `Up to ${settings.max_pages.toLocaleString()} pages, ${settings.max_depth} clicks deep. ` +
    (login ? "Stays on this website. " : settings.ignore_robots ? "Ignores robots.txt. " : "Respects robots.txt. ") +
    (settings.static_only
      ? "HTML only, no browser."
      : switchOn(settings, "click_through")
        ? "Clicks through menus and dialogs."
        : "Load state only.");

  const notIncluded = login
    ? "Pages on any other website. Nothing is uploaded; the session cookie is discarded when the scan ends."
    : [
        "Pages behind a login",
        settings.include_subdomain ? null : "other subdomains",
        settings.whole_host ? null : "other sections of the site",
      ]
        .filter(Boolean)
        .join(" · ") + ".";

  // The spoken digest: recomputed on every change, written 600 ms after the
  // last one, and only when it differs from what was last spoken.
  const digest = `Up to ${settings.max_pages.toLocaleString()} pages. WCAG 2.2 ${settings.axe_level} with ${engine}. ${onCount} of ${total} checks on.`;
  const [spoken, setSpoken] = useState(digest);
  useEffect(() => {
    if (digest === spoken) return;
    const timer = window.setTimeout(() => setSpoken(digest), 600);
    return () => window.clearTimeout(timer);
  }, [digest, spoken]);

  return (
    <aside
      aria-labelledby="scan-summary-title"
      className={cn("rounded-md border border-border bg-surface p-5 shadow-card", className)}
    >
      <div className="flex items-center gap-3.5">
        <svg width="56" height="56" viewBox="0 0 56 56" aria-hidden className="shrink-0">
          <circle cx="28" cy="28" r="22" fill="none" stroke="#DCE3EC" strokeWidth="6" />
          <circle
            cx="28"
            cy="28"
            r="22"
            fill="none"
            stroke="#00274C"
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={(circumference * (1 - onCount / total)).toFixed(1)}
            transform="rotate(-90 28 28)"
            className="transition-[stroke-dashoffset] duration-300 motion-reduce:transition-none"
          />
          <text x="28" y="33" textAnchor="middle" fontSize="15" fontWeight="700" fill="#111827">
            {onCount}
          </text>
        </svg>
        <div className="min-w-0">
          <h2 id="scan-summary-title" className="text-base font-semibold text-fg">
            {SUMMARY.title}
          </h2>
          <p className="text-xs text-fg-muted">
            {onCount} of {total} checks on · {isDefault(settings, policy) ? "Default settings" : "Customized"}
          </p>
        </div>
      </div>
      <p role="status" aria-atomic="true" className="sr-only">
        {spoken}
      </p>

      <dl className="mt-4 flex flex-col gap-4 text-sm">
        <div>
          <dt className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">{SUMMARY.site}</dt>
          {site ? (
            <>
              <dd className="mt-1 break-all font-semibold text-fg">{site.line}</dd>
              <dd className="text-fg-muted">
                {preview.data?.whole_host ? "Whole host" : "This section only"}
                {login ? " · after you sign in" : " · public pages"}
              </dd>
            </>
          ) : (
            <dd className="mt-1 text-fg-muted">{SUMMARY.siteEmpty}</dd>
          )}
        </div>
        <div>
          <dt className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">{SUMMARY.coverage}</dt>
          <dd className="mt-1 text-fg">{coverageLine}</dd>
        </div>
        <div>
          <dt className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">{SUMMARY.checks}</dt>
          <dd className="mt-1.5 flex flex-wrap gap-1.5">
            <ChipView label={`WCAG 2.2 ${settings.axe_level}`} on />
            <ChipView label={engine} on />
            {checks.map((item) => (
              <ChipView key={item.label} label={item.label} on={item.on} />
            ))}
          </dd>
          {alfaUnavailable && (
            <dd className="mt-2 text-xs text-sev-major">
              Siteimprove Alfa is unavailable, so this scan runs with axe-core:{" "}
              {capabilities.alfa?.reason ?? "not installed"}.
            </dd>
          )}
        </div>
        <div>
          <dt className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">{SUMMARY.localAi}</dt>
          <dd className="mt-1.5 flex flex-wrap gap-1.5">
            {ai.map((item) => (
              <ChipView key={item.label} label={item.label} on={item.on} />
            ))}
          </dd>
          {ai.some((item) => item.on && item.label !== "Image text (OCR)") && (
            <dd className="mt-2 text-xs text-fg-muted">
              Uses only models already installed in local Ollama; nothing is downloaded and no image leaves
              this computer. Ollama may load several GB into memory while analysis runs.
            </dd>
          )}
        </div>
        <div>
          <dt className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">{SUMMARY.storage}</dt>
          <dd className="mt-1 text-fg">
            {settings.static_only
              ? "No rendered pages: this is an HTML-only crawl."
              : settings.skip_rendered_storage
                ? "Rendered pages are not stored; the Page inspector re-renders each page on demand. Findings and screenshots are kept as always."
                : "Keeps a copy of each rendered page, so the Page inspector opens instantly. Findings and screenshots are kept as always."}
          </dd>
        </div>
        <div className="border-t border-border pt-4">
          <dt className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">{SUMMARY.notIncluded}</dt>
          <dd className="mt-1 text-fg-muted">{notIncluded}</dd>
        </div>
      </dl>
      <p className="mt-4 rounded-xs bg-surface-muted px-3 py-2.5 text-xs leading-relaxed text-fg-muted">
        {SUMMARY.footnote}
      </p>
    </aside>
  );
}

function ChipView({ label, on }: { label: string; on: boolean }) {
  return (
    <span
      className={
        on
          ? "animate-pop-in inline-flex min-h-7 items-center rounded-full border border-border bg-surface-muted px-2.5 text-xs font-semibold text-fg"
          : "inline-flex min-h-7 items-center rounded-full border border-dashed border-border-strong bg-surface px-2.5 text-xs font-semibold text-fg-subtle"
      }
    >
      {label}
    </span>
  );
}
