import { useEffect, useState } from "react";
import type { ScopePreview } from "../../api/types";
import { cn } from "../../lib/cn";
import { CHECK_LABEL } from "../../lib/terms";
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
    chip(CHECK_LABEL.keyboard, switchOn(settings, "keyboard") && !settings.static_only),
    ...(isFixed(policy, "skip_focus") ? [] : [chip(CHECK_LABEL.focus, switchOn(settings, "focus") && !settings.static_only)]),
    chip(CHECK_LABEL.responsive, switchOn(settings, "responsive") && !settings.static_only),
    chip("Opens menus and pop-up windows", switchOn(settings, "click_through") && !settings.static_only),
    chip("Saved copy of each page", !switchOn(settings, "skip_rendered_storage") && !settings.static_only),
  ];
  const ai: Chip[] = [
    chip(CHECK_LABEL.image, switchOn(settings, "ocr")),
    chip("Vision model review", switchOn(settings, "vision")),
    ...(isFixed(policy, "skip_semantic") ? [] : [chip(CHECK_LABEL.semantic, switchOn(settings, "semantic"))]),
    ...(isFixed(policy, "skip_visual") ? [] : [chip(CHECK_LABEL.visual, switchOn(settings, "motion"))]),
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
    (login ? "Stays on this website. " : settings.ignore_robots ? "Ignores robots.txt. " : "Follows robots.txt. ") +
    (settings.static_only
      ? "Page code (HTML) only, no browser."
      : switchOn(settings, "click_through")
        ? "Opens menus and pop-up windows."
        : "Checks each page at page load only.");

  const notIncluded = login
    ? "Pages on any other website. Axcess uploads nothing. It deletes the sign-in cookie (session cookie) when the scan ends."
    : [
        "Pages behind a sign-in",
        settings.include_subdomain ? null : "other subdomains",
        settings.whole_host ? null : "other sections of the site",
      ]
        .filter(Boolean)
        .join(" · ") + ".";

  // The spoken digest: recomputed on every change, written 600 ms after the
  // last one, and only when it differs from what was last spoken.
  const digest = `Up to ${settings.max_pages.toLocaleString()} pages. ${engine} against WCAG 2.2 Level ${settings.axe_level}. ${onCount} of ${total} checks on.`;
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
                {preview.data?.whole_host ? "Whole website" : "This section only"}
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
            <ChipView label={`WCAG 2.2 Level ${settings.axe_level}`} on />
            <ChipView label={engine} on />
            {checks.map((item) => (
              <ChipView key={item.label} label={item.label} on={item.on} />
            ))}
          </dd>
          {alfaUnavailable && (
            <dd className="mt-2 text-xs text-sev-major">
              {CHECK_LABEL.alfa} is not available, so this scan uses {CHECK_LABEL.axe}. Reason:{" "}
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
          {ai.some((item) => item.on && item.label !== CHECK_LABEL.image) && (
            <dd className="mt-2 text-xs text-fg-muted">
              Uses only AI models already installed in Ollama on this computer. Axcess downloads nothing, and
              no image leaves this computer. Ollama may use several gigabytes (GB) of memory while it runs.
            </dd>
          )}
        </div>
        <div>
          <dt className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">{SUMMARY.storage}</dt>
          <dd className="mt-1 text-fg">
            {settings.static_only
              ? "No saved copies: a fast scan reads only the page code (HTML)."
              : settings.skip_rendered_storage
                ? login
                  ? // A sign-in scan's screenshots are cut from the same signed-in
                    // pages, so the server keeps neither (server.py, the
                    // capture_screenshots / store_rendered_html pair).
                    "No saved copy of each page, and no screenshots. The Page inspector loads the live page when you open it. Occurrences are saved as usual."
                  : "No saved copy of each page. The Page inspector loads the live page when you open it. Occurrences and screenshots are saved as usual."
                : "Keeps a saved copy of each page, so the Page inspector opens right away. Occurrences and screenshots are saved as usual."}
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
