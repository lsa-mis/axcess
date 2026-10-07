import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, Minus, RotateCcw, SlidersHorizontal } from "lucide-react";
import type { ScopePreview } from "../../api/types";
import { cn } from "../../lib/cn";
import { CHECK_LABEL } from "../../lib/terms";
import { RAIL_LABELS, SUMMARY } from "./copy";
import type { Capabilities } from "./groupProps";
import {
  checkInventory,
  isDefault,
  isFixed,
  limitText,
  switchOn,
  type ScanPolicy,
  type ScanSettings,
} from "./scanPolicy";
import type { ScopePreviewState } from "./useScopePreview";

function engineName(engine: ScanSettings["scan_engine"]): string {
  return engine === "both" ? "Rule checks (axe and Alfa)" : engine === "alfa" ? CHECK_LABEL.alfa : CHECK_LABEL.axe;
}

type Line = { label: string; on: boolean };

/**
 * Every switch the rail reports, by its short rail name, and whether it
 * will happen. A check counts as on only when it will actually run
 * (`checkInventory`), so a browser check that Fast crawl rules out lands
 * under Not included even while its switch still looks on.
 */
function lines(settings: ScanSettings, policy: ScanPolicy): { scope: Line[]; checks: Line[] } {
  const login = policy.mode === "login";
  const scope: Line[] = [
    {
      label: login ? RAIL_LABELS.whole_host_login : RAIL_LABELS.whole_host,
      on: switchOn(settings, "whole_host"),
    },
  ];
  if (!isFixed(policy, "include_subdomain")) {
    scope.push({ label: RAIL_LABELS.include_subdomain, on: switchOn(settings, "include_subdomain") });
  }
  const checks: Line[] = [
    { label: RAIL_LABELS.click_through, on: switchOn(settings, "click_through") && !settings.static_only },
    ...checkInventory(settings, policy).map((item) => ({
      label: RAIL_LABELS[item.key as keyof typeof RAIL_LABELS],
      on: item.on,
    })),
  ];
  return { scope, checks };
}

/** One labelled part of the summary, set off from the next by a rule. */
function Section({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="px-5 py-3">
      <dt className="text-xs font-semibold text-fg-muted">{term}</dt>
      {children}
    </div>
  );
}

/**
 * One item per line, with an icon that repeats what the section's name
 * already says: a tick for what runs, a dash for what does not. The icon
 * is never the only cue, so it is hidden from a screen reader.
 */
function ItemList({ items, on }: { items: string[]; on: boolean }) {
  const Icon = on ? Check : Minus;
  return (
    <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
      {items.map((item) => (
        <li key={item} className={cn("flex items-start gap-2", on ? "text-fg" : "text-fg-muted")}>
          <Icon
            aria-hidden
            className={cn("mt-1 h-4 w-4 shrink-0", on ? "text-umich-blue" : "text-fg-subtle")}
          />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * The right-hand rail: what the scan will do, as it stands right now, with
 * the buttons that start it underneath.
 *
 * It is built to be read in one pass. Each part has a short name and its
 * own lines, one fact per line, with a rule between parts; what runs is a
 * ticked list and what does not is a dashed, quieter list, each item named
 * in a few plain words. The summary is its own complementary landmark; the
 * actions passed as `children` sit in the same card but outside it,
 * because they belong to the form, pinned to the card's foot on a wide
 * screen.
 *
 * The visible card is not a live region — it changes on every keystroke.
 * A separate status line, outside the summary and empty until something
 * changes, speaks a short digest 600 ms after the last change, so typing
 * "2500" in Max pages is announced once and reading the rail never hears
 * it twice.
 */
export default function ScanSummaryCard({
  settings,
  policy,
  preview,
  capabilities,
  onReset,
  children,
  className,
}: {
  settings: ScanSettings;
  policy: ScanPolicy;
  preview: { state: ScopePreviewState; data: ScopePreview | null };
  capabilities: Capabilities;
  /** Put every setting back. Offered at the top right once something changed. */
  onReset?: () => void;
  children?: ReactNode;
  className?: string;
}) {
  const titleRef = useRef<HTMLHeadingElement>(null);
  // Scrolls when it is taller than its cap (a wide screen, a long summary).
  // A scrolling region with nothing focusable in it cannot be scrolled from
  // the keyboard, so then, and only then, the summary itself takes focus.
  const scrollRef = useRef<HTMLElement>(null);
  const [scrolls, setScrolls] = useState(false);
  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const measure = () => setScrolls(element.scrollHeight > element.clientHeight + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    for (const child of Array.from(element.children)) observer.observe(child);
    return () => observer.disconnect();
  }, []);
  const login = policy.mode === "login";
  const unchanged = isDefault(settings, policy);
  const { scope, checks } = lines(settings, policy);
  const engine = engineName(settings.scan_engine);
  const alfaUnavailable = capabilities.alfa?.available === false && settings.scan_engine !== "axe";
  const usesLocalModels = checkInventory(settings, policy).some(
    (item) => item.on && item.group === "localAi" && item.key !== "ocr",
  );

  const siteFallback =
    preview.state === "checking"
      ? "Checking the address…"
      : preview.state === "error"
        ? "Axcess could not work out what to scan from that address."
        : SUMMARY.siteEmpty;

  // No page limit reads as what the scan will do, not as a number.
  const pagesLine =
    settings.all_pages && !isFixed(policy, "all_pages")
      ? `Every page it finds, ${limitText(settings.max_depth)} clicks deep`
      : `Up to ${limitText(settings.max_pages)} pages, ${limitText(settings.max_depth)} clicks deep`;
  const coverage = [
    pagesLine,
    login ? "Stays on this website" : settings.ignore_robots ? "Ignores robots.txt" : "Follows robots.txt",
    !login && switchOn(settings, "include_subdomain") ? "Includes subdomains" : null,
    settings.static_only ? SUMMARY.htmlOnly : null,
    settings.search ? "Uses a search box to find more pages" : null,
  ].filter((part): part is string => Boolean(part));

  const running = checks.filter((line) => line.on).map((line) => line.label);
  const skipsStorage = settings.skip_rendered_storage && !settings.static_only;
  const notIncluded = [
    login ? SUMMARY.noOtherSites : SUMMARY.noSignIn,
    ...scope.filter((line) => !line.on).map((line) => line.label),
    ...checks.filter((line) => !line.on).map((line) => line.label),
    ...(skipsStorage ? [SUMMARY.noRenderedCopies] : []),
    ...(skipsStorage && login ? [SUMMARY.noScreenshots] : []),
  ];

  const digest =
    `${pagesLine}. ` +
    `${engine} against WCAG ${settings.wcag_version} Level ${settings.axe_level}. ` +
    `${running.length} ${running.length === 1 ? "check runs" : "checks run"}.`;
  const [spoken, setSpoken] = useState("");
  const lastDigest = useRef(digest);
  useEffect(() => {
    if (digest === lastDigest.current) return;
    const timer = window.setTimeout(() => {
      lastDigest.current = digest;
      setSpoken(`Summary updated. ${digest}`);
    }, 600);
    return () => window.clearTimeout(timer);
  }, [digest]);

  return (
    <div className={cn("rounded-xs border border-border bg-surface shadow-card", className)}>
      <aside
        ref={scrollRef}
        aria-labelledby="scan-summary-title"
        // A scrolling region must be reachable by keyboard (as TableRegion).
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={scrolls ? 0 : undefined}
        className="rounded-[7px] focus:outline-none focus-visible:shadow-focus lg:max-h-[calc(100vh-14rem)] lg:overflow-y-auto"
      >
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-5 pt-5">
          <h2
            id="scan-summary-title"
            ref={titleRef}
            tabIndex={-1}
            className="text-base font-semibold text-fg focus:outline-none"
          >
            {SUMMARY.title}
          </h2>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span
              className={cn(
                "inline-flex min-h-6 items-center gap-1.5 rounded-full border px-2.5 text-xs font-semibold",
                unchanged
                  ? "border-border bg-surface-muted text-fg-muted"
                  : "border-umich-blue/30 bg-umich-blue/[0.06] text-fg",
              )}
            >
              {unchanged ? (
                <Check aria-hidden className="h-3.5 w-3.5" />
              ) : (
                <SlidersHorizontal aria-hidden className="h-3.5 w-3.5" />
              )}
              {unchanged ? SUMMARY.defaultState : SUMMARY.customized}
            </span>
            {/* Top right, beside the word that says something changed, and
                only then: at the foot of the rail it sat under Start and
                Cancel, where it was the last thing found. It goes away once
                pressed, so focus moves to the summary's heading rather than
                being left on nothing. */}
            {!unchanged && onReset && (
              // eslint-disable-next-line react/forbid-elements -- Convert: a text-link styled button; needs a link variant on Button
              <button
                type="button"
                onClick={() => {
                  onReset();
                  titleRef.current?.focus();
                }}
                className="inline-flex min-h-target items-center gap-1 rounded-xs px-1 text-xs font-semibold text-umich-blue underline underline-offset-2 hover:bg-surface-muted focus-visible:outline-none focus-visible:shadow-focus"
              >
                <RotateCcw aria-hidden className="h-3.5 w-3.5" />
                {SUMMARY.reset}
              </button>
            )}
          </div>
        </div>

        <dl className="mt-3 divide-y divide-border border-t border-border text-sm leading-6">
          <Section term={SUMMARY.site}>
            {preview.state === "ok" && preview.data ? (
              <>
                <dd className="mt-1 break-all font-semibold text-fg">
                  {preview.data.whole_host
                    ? `Every page on ${preview.data.host}`
                    : `${preview.data.host}${preview.data.path_prefix}`}
                </dd>
                <dd className="text-fg-muted">
                  {preview.data.whole_host ? "Whole website" : "This section only"}
                  {login ? ", after you sign in" : ", public pages"}
                </dd>
              </>
            ) : (
              <dd className="mt-1 text-fg-muted">{siteFallback}</dd>
            )}
          </Section>

          <Section term={SUMMARY.coverage}>
            {coverage.map((line) => (
              <dd key={line} className="text-fg first-of-type:mt-1">
                {line}
              </dd>
            ))}
          </Section>

          <Section term={SUMMARY.standard}>
            <dd className="mt-1 text-fg">
              WCAG {settings.wcag_version} Level {settings.axe_level}, checked with {engine}
            </dd>
            {alfaUnavailable && (
              <dd className="mt-1.5 text-xs text-sev-major">
                {CHECK_LABEL.alfa} is not available, so this scan uses {CHECK_LABEL.axe}. Reason:{" "}
                {capabilities.alfa?.reason ?? "not installed"}.
              </dd>
            )}
          </Section>

          <Section term={SUMMARY.checks}>
            <dd className="mt-1">
              {running.length ? <ItemList items={running} on /> : <span className="text-fg-muted">None</span>}
            </dd>
            {usesLocalModels && <dd className="mt-2 text-xs text-fg-muted">{SUMMARY.localModels}</dd>}
          </Section>

          <Section term={SUMMARY.notIncluded}>
            <dd className="mt-1">
              {notIncluded.length ? (
                <ItemList items={notIncluded} on={false} />
              ) : (
                <span className="text-fg-muted">{SUMMARY.nothingLeftOut}</span>
              )}
            </dd>
            {login && <dd className="mt-2 text-xs text-fg-muted">{SUMMARY.loginPrivacy}</dd>}
          </Section>
        </dl>
      </aside>

      <p className="border-t border-border px-5 py-3 text-xs text-fg-muted">{SUMMARY.footnote}</p>

      {/* When the rail is capped and scrolls, the actions stay pinned to its
          foot and only the summary moves under them, so Start is always in
          view beside the cards; the soft shadow above them says there is
          more underneath. They cover nothing a keyboard can reach: the
          summary above holds no controls. */}
      {children && (
        <div className="rounded-b-md border-t border-border bg-surface px-5 pb-5 pt-4 lg:sticky lg:bottom-0 lg:shadow-[0_-10px_16px_-12px_rgba(0,39,76,0.28)]">
          {children}
        </div>
      )}
      <p role="status" aria-atomic="true" className="sr-only">
        {spoken}
      </p>
    </div>
  );
}
