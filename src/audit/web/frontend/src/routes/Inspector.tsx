import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, ExternalLink, FileCode2, Loader2 } from "lucide-react";
import { api } from "../api/client";
import ReportHeader, { ReportMeta } from "../components/ReportHeader";
import { Card, EmptyState, ExternalLinkButton, LinkButton } from "../components/ui";
import { cn } from "../lib/cn";

type TabId = "page" | "dom";

/** What the inspector points at: a CSS selector and/or the exact element markup. */
type Target = { selector: string | null; snippet: string | null };

/**
 * Page/DOM inspector for one recorded page.
 *
 * Landing here from any "pages with this issue/finding" table replaces the old
 * behavior of opening the live site in a new tab. When the scan stored the
 * rendered document (the default) it is served straight from the report
 * database; a scan run with "don't store rendered pages", a predating report,
 * or an over-bound page falls back to a one-page on-demand render in a
 * throwaway headless Chromium. The "Rendered page" tab loads that HTML into a
 * sandboxed iframe and highlights the flagged element(s) (a CSS outline baked
 * into the markup, computed off the main render path); the "Loaded DOM" tab
 * shows the same markup as escaped source with the element's markup
 * highlighted. No screenshot is captured or stored. An "Open live page"
 * action stays available in the header.
 *
 * The rendered HTML is untrusted scanned content: it is sandboxed with scripts
 * disabled, and in the DOM tab it is rendered as escaped text, never executed.
 */
export default function InspectorRoute() {
  const { scanId, pageId } = useParams<{ scanId: string; pageId: string }>();
  const [params] = useSearchParams();
  const scan = Number(scanId);
  const page = Number(pageId);
  const issueKey = params.get("issue");
  const directSelector = params.get("selector");
  const directSnippet = params.get("snippet");
  const origin = params.get("origin");
  const context = params.get("context");
  const contextTo = params.get("contextTo");
  const backTo = params.get("back");

  const { data: scanData } = useQuery({
    queryKey: ["scan", scan],
    queryFn: () => api.getScan(scan),
    enabled: Number.isFinite(scan),
  });

  // Fetch the page's full evidence so we can resolve the current issue's
  // finding(s) on this page, and only those, not every issue the page happens
  // to carry.
  const { data: pageEvidence, isError: evidenceError } = useQuery({
    queryKey: ["page-evidence", scan, page],
    queryFn: () => api.getPageEvidence(scan, page),
    enabled: Number.isFinite(scan) && Number.isFinite(page),
  });

  // The findings that belong to the issue being reviewed on this page. For the
  // ?issue= path this is every finding of the same rule/pipeline (an issue can
  // have several occurrences on one page); for a direct selector/snippet it is
  // that one finding. Only these are highlighted, not other issues on the page.
  const currentFindings = useMemo(() => {
    if (!pageEvidence) return [];
    if (issueKey) {
      const segments = issueKey.split(":");
      if (segments.length < 2) return [];
      const pipeline = segments[0];
      const rule = segments[1];
      return pageEvidence.a11y_findings.filter(
        (f) =>
          f.pipeline === pipeline &&
          f.rule_id === rule &&
          (f.target_selector || f.html_snippet),
      );
    }
    return pageEvidence.a11y_findings.filter(
      (f) =>
        (directSelector && f.target_selector === directSelector) ||
        (directSnippet && f.html_snippet === directSnippet),
    );
  }, [pageEvidence, issueKey, directSelector, directSnippet]);

  // The findings' locators, deduped (two rules can share one element, and
  // identical siblings are intentionally one location). This list drives both
  // the highlight pass and the auto-scroll, so it is computed once.
  const targets = useMemo<Target[]>(() => {
    const seen = new Set<string>();
    const out: Target[] = [];
    for (const f of currentFindings) {
      const selector = f.target_selector || null;
      const snippet = f.html_snippet || null;
      if (!selector && !snippet) continue;
      const key = snippet ? normalizeWhitespace(snippet) : (selector ?? "");
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ selector, snippet });
    }
    return out;
  }, [currentFindings]);
  const target = targets[0] ?? null;
  const hasTarget = targets.length > 0;

  // Human-readable breadcrumb label, e.g. "WCAG 1.4.3: Contrast (Minimum)"
  // instead of the cryptic `alfa:sia-r69:failed` issue key.
  const contextLabel = useMemo(
    () => currentFindings[0]?.help || context,
    [currentFindings, context],
  );

  // Toggle to show/hide the highlight, persisted so a reload keeps the view.
  const [showHighlights, setShowHighlights] = useState(() => readShowHighlights());
  const toggleHighlights = () => {
    setShowHighlights((was) => {
      const next = !was;
      try {
        localStorage.setItem("axcess.inspect.showHighlights", next ? "1" : "0");
      } catch {
        // storage unavailable, the toggle still works for the session
      }
      return next;
    });
  };

  // Don't fire the (expensive) live render until the issue key is resolved,
  // avoids a wasted capture-plus-refetch on every open. When the evidence
  // lookup fails, proceed without a marker rather than hanging.
  const inspectEnabled =
    Number.isFinite(scan) &&
    Number.isFinite(page) &&
    (!issueKey || !!pageEvidence || evidenceError);

  const { data, isLoading, error } = useQuery({
    queryKey: ["page-inspection", scan, page],
    queryFn: () => api.getPageInspection(scan, page),
    enabled: inspectEnabled,
    retry: false,
  });

  const [tab, setTab] = useState<TabId>("page");
  const tabRefs = useRef<Record<TabId, HTMLButtonElement | null>>({
    page: null,
    dom: null,
  });

  const frameRef = useRef<HTMLIFrameElement | null>(null);

  // Bake the highlight into the srcdoc rather than reaching into the frame's
  // contentDocument: the sandbox can make that document opaque, which is exactly
  // why the outline never showed. The captured HTML can be several megabytes,
  // though, so parsing + locating + re-serializing it must not stall the page:
  // the iframe paints the raw capture immediately, and the outlined version is
  // computed when the browser is idle, then swapped in (the swap re-triggers
  // onLoad, so the auto-scroll re-runs for the highlighted markup).
  const [highlight, setHighlight] = useState<HighlightResult | null>(null);
  const highlightRequest = useRef(0);

  useEffect(() => {
    highlightRequest.current += 1;
    const request = highlightRequest.current;
    const html = data?.render.dom_html ?? null;
    if (!showHighlights || !html || targets.length === 0) {
      setHighlight(null);
      return;
    }
    setHighlight(null); // the raw capture shows while the outline is baked
    scheduleIdle(() => {
      if (request !== highlightRequest.current) return; // superseded
      setHighlight(buildHighlightedHtml(html, targets));
    });
  }, [showHighlights, data?.render.dom_html, targets]);

  const srcDoc =
    showHighlights && highlight ? highlight.srcDoc : (data?.render.dom_html ?? "");
  const highlightedCount = showHighlights && highlight ? highlight.found : 0;
  const highlightPending = showHighlights && hasTarget && highlight === null;

  // Best-effort: if the sandbox permits contentDocument access, bring the
  // highlighted element into view. Never required, the outline is baked in.
  const scrollToElement = useCallback(() => {
    if (targets.length === 0) return;
    let attempt = 0;
    const tryScroll = () => {
      try {
        const doc = frameRef.current?.contentDocument;
        if (doc) {
          let el: Element | null = null;
          for (const t of targets) {
            el = findTargetElement(doc, t);
            if (el) break;
          }
          (el as HTMLElement | null)?.scrollIntoView?.({ block: "center" });
          return;
        }
      } catch {
        // Opaque document, the highlight is baked in, only the auto-scroll is lost.
      }
      attempt += 1;
      if (attempt < 10) window.setTimeout(tryScroll, 60);
    };
    tryScroll();
  }, [targets]);

  // Fresh render on mount (and when the scan/page/target changes) is the point
  // of the route, reset to the Page tab.
  useEffect(() => {
    setTab("page");
  }, [scan, page, targets]);

  // The flagged element's markup, split out of the source so the Loaded DOM tab
  // can wrap it in a <mark>. Null when there is no target or the element is not
  // present in the captured markup. Computed lazily, only when the DOM tab is
  // actually open, because it needs its own unmarked parse of the document.
  const domParts = useMemo(
    () => (tab === "dom" ? highlightInDom(data?.render.dom_html ?? null, target) : null),
    [tab, data?.render.dom_html, target],
  );

  const onTabKeyDown = (
    event: React.KeyboardEvent<HTMLButtonElement>,
    id: TabId,
  ) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const next: TabId = id === "page" ? "dom" : "page";
    setTab(next);
    tabRefs.current[next]?.focus();
  };

  if (error) {
    return (
      <EmptyState
        title="Can't inspect this page"
        message={
          error instanceof Error
            ? error.message
            : "This page could not be inspected. It may belong to a running or login-protected report, or be outside the scan's scope."
        }
        action={
          <LinkButton to={`/scans/${scan}/pages/${page}`} variant="primary">
            Back to stored page evidence
          </LinkButton>
        }
      />
    );
  }
  if (isLoading || !data) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-fg-muted" role="status">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Rendering the page for inspection…
      </div>
    );
  }

  const { page: pageInfo, render } = data;
  const displayTitle = pageInfo.title || pageInfo.url;
  const liveUrl = pageInfo.url;

  return (
    <>
      {(origin || context) && (
        <nav aria-label="Breadcrumb" className="mb-3">
          <ol className="flex flex-wrap items-center gap-1.5 text-xs font-semibold">
            {origin && backTo && (
              <>
                <li>
                  <Link
                    to={backTo}
                    className="inline-flex min-h-target items-center text-umich-blue underline underline-offset-2"
                  >
                    {origin}
                  </Link>
                </li>
                <li aria-hidden className="text-border-strong">
                  <ChevronRight className="h-3.5 w-3.5 shrink-0" />
                </li>
              </>
            )}
            {context && (
              <li>
                {contextTo ? (
                  <Link
                    to={contextTo}
                    className="inline-flex min-h-target items-center text-fg font-semibold text-umich-blue underline underline-offset-2"
                  >
                    {contextLabel}
                  </Link>
                ) : (
                  <span className="rounded-xs border border-border bg-surface-muted px-1.5 py-0.5 text-fg-muted">
                    {contextLabel}
                  </span>
                )}
              </li>
            )}
          </ol>
        </nav>
      )}

      <ReportHeader
        scanId={scan}
        previousScanId={scanData?.previous_scan_id ?? null}
        title={displayTitle}
        meta={
          <ReportMeta
            counts={
              render.ok
                ? `${render.source === "stored" ? "Stored render" : "Live render"} (${render.status_code})`
                : "Could not render live"
            }
            note={
              pageInfo.captured_at
                ? `${pageInfo.url} · captured ${new Date(pageInfo.captured_at).toLocaleString()}`
                : pageInfo.url
            }
          />
        }
        actions={
          <ExternalLinkButton
            href={liveUrl}
            variant="secondary"
            aria-label={`Open ${displayTitle} in a new tab`}
          >
            <ExternalLink className="h-4 w-4" aria-hidden />
            Open live page
          </ExternalLinkButton>
        }
      />

      {!render.ok && (
        <Card className="mb-4 border-sev-major/40 bg-sev-major-bg p-4" role="alert">
          <p className="text-sm font-semibold text-fg">This page could not be re-rendered</p>
          <p className="mt-1 text-sm text-fg">{render.error}</p>
          <p className="mt-2 text-2xs text-fg-muted">
            The stored scan evidence for this page is still available, use{" "}
            <span className="font-semibold">Open live page</span> to view it
            yourself, or return to the stored page evidence.
          </p>
        </Card>
      )}

      <div
        role="tablist"
        aria-label="How this page was rendered"
        className="mb-4 inline-flex gap-1 rounded-xs border border-border bg-surface-muted p-1"
      >
        <TabButton
          id="inspect-tab-page"
          panelId="inspect-panel-page"
          tab="page"
          label={render.ok ? "Rendered page" : "Page"}
          active={tab === "page"}
          onSelect={() => setTab("page")}
          onKeyDown={onTabKeyDown}
          ref={(el) => {
            tabRefs.current.page = el;
          }}
        />
        <TabButton
          id="inspect-tab-dom"
          panelId="inspect-panel-dom"
          tab="dom"
          label="Loaded DOM"
          active={tab === "dom"}
          onSelect={() => setTab("dom")}
          onKeyDown={onTabKeyDown}
          ref={(el) => {
            tabRefs.current.dom = el;
          }}
        />
      </div>

      <div
        id="inspect-panel-page"
        role="tabpanel"
        aria-labelledby="inspect-tab-page"
        tabIndex={0}
        className="rounded-xs border border-border bg-surface shadow-card"
        hidden={tab !== "page"}
      >
        {render.ok && render.dom_html ? (
          <div>
            {currentFindings.length > 0 && (
              <div className="border-b border-border bg-surface-muted/40 px-3 py-2">
                <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-fg-subtle">
                  Stored evidence
                </p>
                <ul className="mt-1.5 space-y-2">
                  {currentFindings.slice(0, 3).map((f) => (
                    <li key={f.id} className="text-xs">
                      <p className="font-semibold text-fg">
                        {f.help}
                        <span className="ml-1 font-normal text-fg-muted">({f.rule_id})</span>
                      </p>
                      {f.target_selector && (
                        <code className="mt-0.5 block overflow-x-auto whitespace-nowrap rounded-2xs border border-border bg-surface px-2 py-1 text-2xs text-fg">
                          {f.target_selector}
                        </code>
                      )}
                      {f.html_snippet && (
                        <pre className="mt-1 max-h-24 overflow-auto rounded-2xs border border-border bg-surface px-2 py-1 text-2xs leading-relaxed text-fg-muted">
                          {f.html_snippet}
                        </pre>
                      )}
                    </li>
                  ))}
                </ul>
                {currentFindings.length > 3 && (
                  <p className="mt-1 text-2xs text-fg-muted">
                    + {currentFindings.length - 3} more occurrence{currentFindings.length - 3 === 1 ? "" : "s"} on this page.
                  </p>
                )}
              </div>
            )}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-surface-muted/40 px-3 py-2">
              <span className="text-xs font-semibold uppercase tracking-[0.12em] text-fg-subtle">
                {highlightPending
                  ? "Highlighting…"
                  : showHighlights && highlightedCount > 0
                    ? `${highlightedCount} location${highlightedCount === 1 ? "" : "s"} highlighted`
                    : "Rendered page"}
              </span>
              {hasTarget && (
                <button
                  type="button"
                  onClick={toggleHighlights}
                  className="inline-flex min-h-target items-center gap-1 rounded-xs border border-border-strong bg-surface px-3 text-xs font-semibold text-fg hover:bg-surface-muted"
                >
                  {showHighlights ? "Hide highlights" : "Show highlights"}
                </button>
              )}
            </div>
            {/* Sandboxed with scripts disabled: the page's own JS never runs,
                but `allow-same-origin` lets us reach in to outline the flagged
                element. This is the "point at the issue" affordance, no
                screenshot is captured or stored. `onLoad` is a document-load
                lifecycle signal, not an interaction, so the a11y rule below is
                a false positive for an iframe. */}
            {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
            <iframe
              ref={frameRef}
              srcDoc={srcDoc}
              onLoad={scrollToElement}
              title={`Re-rendered ${displayTitle}`}
              sandbox="allow-same-origin"
              referrerPolicy="no-referrer"
              className="h-[75vh] w-full border-0 bg-white"
            />
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border px-3 py-2 text-xs text-fg-muted" aria-live="polite">
              {highlightPending && (
                <span>Highlighting the flagged element…</span>
              )}
              {!highlightPending && showHighlights && highlightedCount > 0 && (
                <span>
                  The red outline marks the flagged element
                  {highlightedCount > 1 ? ` (${highlightedCount} on this page)` : ""}.
                </span>
              )}
              {!highlightPending &&
                showHighlights &&
                highlight !== null &&
                highlightedCount > 0 &&
                highlightedCount < highlight.total && (
                  <span className="text-sev-major">
                    {highlightedCount} of {highlight.total} flagged elements were
                    found, the rest may have changed since the scan.
                  </span>
                )}
              {!highlightPending && showHighlights && hasTarget && highlightedCount === 0 && (
                <span className="text-sev-major">
                  The flagged element was not found in this capture, it may have
                  changed since the scan.
                </span>
              )}
              {!showHighlights && hasTarget && (
                <span>Highlights are hidden for this page.</span>
              )}
              {!hasTarget && (
                <span>
                  {render.source === "stored"
                    ? "Shown from the scan capture, no element to mark on this finding."
                    : "Rendered on demand, no element to mark on this finding."}
                </span>
              )}
              {!data.store_rendered_html && (
                <span>
                  This scan was run without storing rendered pages, the page is
                  re-rendered live on demand.
                </span>
              )}
            </div>
          </div>
        ) : (
          <div className="p-6 text-sm text-fg-muted">
            {render.error || "The page could not be rendered."}
          </div>
        )}
      </div>

      <div
        id="inspect-panel-dom"
        role="tabpanel"
        aria-labelledby="inspect-tab-dom"
        tabIndex={0}
        className="rounded-xs border border-border bg-surface shadow-card"
        hidden={tab !== "dom"}
      >
        {render.ok && render.dom_html ? (
          <div className="p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <p className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-[0.12em] text-fg-subtle">
                <FileCode2 className="h-4 w-4" aria-hidden />
                Loaded DOM, captured at render time
              </p>
              {render.dom_truncated && (
                <span className="text-2xs text-sev-major">
                  Truncated for length (shown at 2,000,000 characters).
                </span>
              )}
            </div>
            {/* Scanned page markup is untrusted and rendered as escaped text,
                never executed. The flagged element's markup is wrapped in a
                <mark> so it is visible in the source, matching the page view. */}
            <pre className="max-h-[70vh] overflow-auto rounded-2xs border border-border bg-surface-muted p-3 text-2xs leading-relaxed text-fg">
              <code>
                {domParts ? (
                  <>
                    {domParts.before}
                    <mark className="rounded-[2px] bg-umich-maize/40 px-0 text-fg">
                      {domParts.el}
                    </mark>
                    {domParts.after}
                  </>
                ) : (
                  render.dom_html
                )}
              </code>
            </pre>
          </div>
        ) : (
          <div className="p-6 text-sm text-fg-muted">
            {render.dom_html
              ? "No rendered HTML was captured."
              : render.error || "The page could not be rendered."}
          </div>
        )}
      </div>
    </>
  );
}

function TabButton({
  id,
  panelId,
  tab,
  label,
  active,
  onSelect,
  onKeyDown,
  ref,
}: {
  id: string;
  panelId: string;
  tab: TabId;
  label: string;
  active: boolean;
  onSelect: () => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLButtonElement>, id: TabId) => void;
  ref: (el: HTMLButtonElement | null) => void;
}) {
  return (
    <button
      type="button"
      id={id}
      ref={ref}
      role="tab"
      aria-selected={active}
      aria-controls={panelId}
      onClick={onSelect}
      onKeyDown={(event) => onKeyDown(event, tab)}
      className={cn(
        "min-h-target rounded-[3px] px-3.5 py-1.5 text-sm font-semibold",
        active
          ? "bg-surface text-fg shadow-card"
          : "text-fg-muted hover:bg-surface/60 hover:text-fg",
      )}
    >
      {label}
    </button>
  );
}

/** Result of baking the highlight into the srcdoc. */
type HighlightResult = { srcDoc: string; found: number; total: number };

/** Ceiling on elements examined by one snippet-match walk, bounds the worst
 *  case on pathological pages while remaining far above any real page's size. */
const WALK_CAP = 20_000;
/** Cheap exact-prefix check applied before any full/whitespace-normalized
 *  markup comparison, prunes almost every candidate element. */
const SNIPPET_HEAD = 64;
/** Snippets at/near the storage cap were truncated mid-markup and can never
 *  equal the element's full serialization; match them by normalized prefix. */
const TRUNCATED_SNIPPET_LENGTH = 3900;

/**
 * Split the captured HTML so the flagged element's serialized markup can be
 * highlighted in the Loaded DOM (source) tab. Parses the HTML with DOMParser,
 * finds the flagged element (verified CSS selector/XPath first, then a
 * bounded exact-markup walk), and locates its ``outerHTML`` in the source.
 * Returns ``null`` when it cannot be found (the source is then shown
 * unhighlighted rather than guessed at).
 */
function highlightInDom(
  html: string | null,
  target: Target | null,
): { before: string; el: string; after: string } | null {
  if (!html || !target) return null;
  try {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const el = findTargetElement(doc, target);
    if (!el) return null;
    const markup = el.outerHTML;
    if (!markup) return null;
    const index = html.indexOf(markup);
    if (index < 0) return null;
    return {
      before: html.slice(0, index),
      el: markup,
      after: html.slice(index + markup.length),
    };
  } catch {
    return null;
  }
}

/**
 * Build the ``srcDoc`` for the Rendered-page tab with the current issue's
 * finding(s) highlighted. Parses the captured HTML once, resolves every
 * target (see ``markTargets``), and re-serializes only when at least one
 * element was found. Because the outline is part of the markup, it renders
 * even when the sandbox makes the frame's ``contentDocument`` opaque (the
 * reason the earlier contentDocument-based outline never showed). Only the
 * given findings are marked, not every other issue on the page.
 */
function buildHighlightedHtml(html: string | null, targets: Target[]): HighlightResult {
  if (!html) return { srcDoc: "", found: 0, total: 0 };
  if (targets.length === 0) return { srcDoc: html, found: 0, total: 0 };
  try {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const found = markTargets(doc, targets);
    if (found === 0) return { srcDoc: html, found: 0, total: targets.length };
    return {
      srcDoc: "<!doctype html>" + doc.documentElement.outerHTML,
      found,
      total: targets.length,
    };
  } catch {
    return { srcDoc: html, found: 0, total: targets.length };
  }
}

/**
 * Resolve every target in ``doc`` and mark each located element. Two passes:
 *
 * 1. Precise, cheap locators, an Alfa JSON XPath, or a plain CSS selector
 *    whose match is *verified* against the finding's snippet so a generic
 *    selector (``h3``) that happens to hit a different element falls back to
 *    the markup walk instead of pointing at the wrong node.
 * 2. One bounded document-order walk shared by every target the precise pass
 *    missed, previously each finding walked the whole tree on its own.
 *
 * Returns the number of distinct elements located.
 */
function markTargets(doc: Document, targets: Target[]): number {
  const found = new Set<Element>();
  const unresolved: Target[] = [];
  for (const target of targets) {
    const el = findPrecise(doc, target);
    if (el) found.add(el);
    else unresolved.push(target);
  }
  locateByWalk(doc, unresolved, found);
  for (const el of found) {
    if (el instanceof HTMLElement) {
      markElement(el, "#be001e", "rgba(190,0,30,0.12)");
    }
  }
  return found.size;
}

function findPrecise(doc: Document, target: Target): Element | null {
  if (target.selector && isAlfaJsonSelector(target.selector)) {
    const el = findByXPath(doc, target.selector);
    if (el) return el;
    return null; // the walk below re-tries via the snippet if one exists
  }
  if (target.selector) {
    try {
      const el = doc.querySelector(target.selector);
      if (el && (!target.snippet || snippetMatches(el, target.snippet))) {
        return el;
      }
      // Generic selector hit the wrong element, the walk will match the
      // exact markup instead.
    } catch {
      // Invalid CSS selector, the walk is the fallback.
    }
  }
  return null;
}

/**
 * Walk ``doc`` once in document order, matching the remaining targets'
 * snippets. Each element is checked against only the snippets whose tag
 * matches its own, with a 64-char exact-prefix gate before any full
 * serialization comparison, and exact string equality before any
 * whitespace-normalized comparison (same-capture markup compares exactly).
 * Iterations are capped so an adversarial document cannot pin the tab.
 */
function locateByWalk(doc: Document, targets: Target[], found: Set<Element>): void {
  const buckets = new Map<string, { raw: string; needle: string; head: string }[]>();
  for (const t of targets) {
    if (!t.snippet) continue;
    const needle = normalizeWhitespace(t.snippet);
    if (!needle) continue;
    const tag = firstTagName(t.snippet) ?? "";
    const entry = { raw: t.snippet, needle, head: t.snippet.slice(0, SNIPPET_HEAD) };
    const bucket = buckets.get(tag);
    if (bucket) bucket.push(entry);
    else buckets.set(tag, [entry]);
  }
  if (buckets.size === 0) return;
  const walker = doc.createTreeWalker(doc.documentElement, NodeFilter.SHOW_ELEMENT);
  let node = walker.nextNode();
  let visited = 0;
  while (node && buckets.size > 0) {
    visited += 1;
    if (visited > WALK_CAP) break;
    const el = node as Element;
    const bucket = buckets.get(el.tagName.toLowerCase());
    if (bucket && bucket.length > 0) {
      const raw = el.outerHTML;
      const remaining: typeof bucket = [];
      for (const entry of bucket) {
        if (
          raw === entry.raw ||
          (raw.startsWith(entry.head) &&
            (normalizeWhitespace(raw) === entry.needle ||
              truncatedSnippetMatches(raw, entry.needle)))
        ) {
          found.add(el);
        } else {
          remaining.push(entry);
        }
      }
      if (remaining.length === 0) buckets.delete(el.tagName.toLowerCase());
      else buckets.set(el.tagName.toLowerCase(), remaining);
    }
    node = walker.nextNode();
  }
}

/** True when ``el``'s serialization is the snippet's element (any whitespace). */
function snippetMatches(el: Element, snippet: string): boolean {
  const needle = normalizeWhitespace(snippet);
  if (!needle) return false;
  const raw = el.outerHTML;
  return (
    raw === snippet ||
    normalizeWhitespace(raw) === needle ||
    truncatedSnippetMatches(raw, needle)
  );
}

function truncatedSnippetMatches(raw: string, needle: string): boolean {
  if (needle.length < TRUNCATED_SNIPPET_LENGTH) return false;
  return normalizeWhitespace(raw).startsWith(needle);
}

function markElement(el: HTMLElement, outlineColor: string, bg: string): void {
  el.classList.add("axcess-inspect-highlight");
  el.style.setProperty("outline", `3px solid ${outlineColor}`, "important");
  el.style.setProperty("outline-offset", "2px", "important");
  el.style.setProperty("background-color", bg, "important");
}

function readShowHighlights(): boolean {
  try {
    return localStorage.getItem("axcess.inspect.showHighlights") !== "0";
  } catch {
    return true;
  }
}

/**
 * Run ``task`` when the browser is idle, with a bounded timeout so a busy
 * main thread can never defer the highlight indefinitely.
 */
function scheduleIdle(task: () => void): void {
  const win = window as Window & {
    requestIdleCallback?: (cb: () => void, opts?: { timeout?: number }) => number;
  };
  if (typeof win.requestIdleCallback === "function") {
    win.requestIdleCallback(task, { timeout: 400 });
  } else {
    window.setTimeout(task, 0);
  }
}

/**
 * Locate the flagged element in ``doc``: a verified CSS selector or Alfa JSON
 * XPath when possible, else a bounded exact-markup walk (handles generic
 * selectors like ``h3`` that would otherwise hit the wrong element).
 */
function findTargetElement(doc: Document, target: Target): Element | null {
  const precise = findPrecise(doc, target);
  if (precise) return precise;
  if (!target.snippet) return null;
  const found = new Set<Element>();
  locateByWalk(doc, [target], found);
  return found.size > 0 ? [...found][0] : null;
}

function isAlfaJsonSelector(selector: string): boolean {
  const s = selector.trim();
  return s.startsWith("{") && s.includes('"path"');
}

function findByXPath(doc: Document, jsonSelector: string): Element | null {
  try {
    const parsed = JSON.parse(jsonSelector) as { path?: unknown };
    if (typeof parsed.path !== "string" || !parsed.path) return null;
    const node = doc.evaluate(
      parsed.path,
      doc,
      null,
      XPathResult.FIRST_ORDERED_NODE_TYPE,
      null,
    ).singleNodeValue;
    if (!node) return null;
    // Alfa paths often end in `/text()[1]`, a text node, not an element.
    if (node.nodeType === Node.TEXT_NODE) {
      return (node as Text).parentElement;
    }
    return node as Element;
  } catch {
    return null;
  }
}

function normalizeWhitespace(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

function firstTagName(markup: string): string | null {
  const m = /^\s*<([a-zA-Z][a-zA-Z0-9-]*)/.exec(markup);
  return m ? m[1].toLowerCase() : null;
}
