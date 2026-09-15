import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileCode2, Loader2 } from "lucide-react";
import { api } from "../api/client";
import ReportHeader, { ReportMeta } from "../components/ReportHeader";
import Tabs from "../components/Tabs";
import { Card, EmptyState, ExternalLinkButton, LinkButton } from "../components/ui";

type TabId = "page" | "dom";

/**
 * What the inspector points at: a CSS selector and/or the exact element markup.
 *
 * `revealedBy` is the accessible name of the control that had to be operated
 * before this element existed, and null for elements present at page load. The
 * capture this view searches is the page *as it loaded*, so a revealed element
 * is legitimately absent from it — without this field the inspector cannot tell
 * "we could not find it" from "it was never there", and reports the first for
 * both.
 */
type Target = {
  selector: string | null;
  snippet: string | null;
  revealedBy: string | null;
  /** The captured state this finding is visible in, when one was stored. */
  stateKey: string | null;
};

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
 * into the markup, computed off the main render path). The capture is given
 * the page's own URL as `<base href>` first, without which its relative
 * stylesheets and images would resolve against the review UI and the page
 * would render unstyled (see `withBaseHref`); the "Loaded DOM" tab
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
  const navigate = useNavigate();
  const scan = Number(scanId);
  const page = Number(pageId);
  const issueKey = params.get("issue");
  const directSelector = params.get("selector");
  const directSnippet = params.get("snippet");

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
      out.push({
        selector,
        snippet,
        revealedBy: f.revealed_by || null,
        stateKey: f.revealed_state_key || null,
      });
    }
    return out;
  }, [currentFindings]);
  const hasTarget = targets.length > 0;

  // The controls that were operated before these findings were first flagged,
  // in the order the probe reached them. Empty when every target was already
  // flagged at page load.
  const revealingControls = useMemo(() => {
    const out: string[] = [];
    for (const target of targets) {
      if (target.revealedBy && !out.includes(target.revealedBy)) {
        out.push(target.revealedBy);
      }
    }
    return out;
  }, [targets]);
  const allTargetsRevealed =
    hasTarget && targets.every((target) => target.revealedBy !== null);


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

  // Which state is on screen. In the URL like the view above it, so a link to
  // "the dialog on page 12" survives being sent to someone.
  //
  // The default is the finding's own state rather than the page as it loaded:
  // arriving here from a revealed finding and being shown a document that
  // cannot contain it is the whole complaint. Only when every target agrees on
  // one state, though -- an issue spanning several states has no single
  // correct answer, so it opens on the load capture and the picker offers the
  // rest.
  const findingStateKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const target of targets) if (target.stateKey) keys.add(target.stateKey);
    return keys;
  }, [targets]);
  const defaultStateKey =
    findingStateKeys.size === 1 && allTargetsRevealed
      ? [...findingStateKeys][0]
      : null;
  const requestedState = params.get("state");
  const stateKey = requestedState ?? defaultStateKey;

  const { data, isLoading, error } = useQuery({
    // The state belongs in the key: without it every finding on the page
    // would share one cached document and the picker would appear to do
    // nothing.
    queryKey: ["page-inspection", scan, page, stateKey],
    queryFn: () => api.getPageInspection(scan, page, stateKey),
    enabled: inspectEnabled,
    retry: false,
  });

  const states = data?.states ?? [];
  const activeStateKey = data?.render.state_key ?? null;
  const stateHref = (key: string | null) => {
    const next = new URLSearchParams(params);
    if (key) next.set("state", key);
    else next.set("state", "");
    const qs = next.toString();
    return `/scans/${scan}/pages/${page}/inspect${qs ? `?${qs}` : ""}`;
  };

  // Which rendering is on screen. In the URL rather than in state so the row
  // below can be links — and so "the Loaded DOM of page 12" is something you
  // can send someone. "page" is the default and stays out of the query string.
  const tab: TabId = params.get("view") === "dom" ? "dom" : "page";
  const viewHref = (view: TabId) => {
    const next = new URLSearchParams(params);
    if (view === "page") next.delete("view");
    else next.set("view", view);
    const qs = next.toString();
    return `/scans/${scan}/pages/${page}/inspect${qs ? `?${qs}` : ""}`;
  };

  /**
   * The findings that could be in the document on screen.
   *
   * One issue can span several states — the same rule failing in two different
   * dialogs — and a finding from another state is not *missing* from this one,
   * it was never going to be here. Counting it would report a miss the reviewer
   * cannot act on, and would keep the "not found" warning permanently lit no
   * matter which state they chose.
   *
   * Load-state findings stay in scope while viewing a state: a revealed state
   * is the page plus whatever the click added, so they are usually still there.
   * The load view keeps every target, because explaining why the revealed ones
   * are absent is the whole point of that screen.
   */
  const scopedTargets = useMemo(
    () =>
      activeStateKey
        ? targets.filter(
            (target) => !target.stateKey || target.stateKey === activeStateKey,
          )
        : targets,
    [targets, activeStateKey],
  );
  const offStateCount = targets.length - scopedTargets.length;
  // What the status lines below are actually talking about.
  const hasScopedTarget = scopedTargets.length > 0;

  /**
   * Why a target is missing from this capture, or null when drift is still the
   * only explanation.
   *
   * Three cases, because two explanations are in play and the page must not
   * assert one when both are open:
   *
   * - every target interaction-revealed — the capture being the load state
   *   accounts for all of it, and nothing here is evidence the site changed.
   * - a mix — the load-state findings genuinely should have been matched, so
   *   drift stays on the table alongside interaction.
   * - none — unchanged.
   *
   * The wording stops at *flagged*. `revealed_by` records that a violation was
   * first reported after a control was operated; the probe never establishes
   * that the element itself was absent before, and saying so would trade one
   * overstatement for another.
   */
  const missingReason = useMemo(() => {
    // Viewing a captured state, the document on screen is the one the finding
    // was flagged in, so "it is not here because this is the load state" is no
    // longer the explanation for anything.
    if (activeStateKey) return null;
    if (revealingControls.length === 0) return null;
    if (!allTargetsRevealed) {
      return {
        whenNoneFound:
          "Some of these were first flagged after a control was operated, so they " +
          "may not be in this capture of the page as it loaded; the rest may have " +
          "changed since the scan.",
        whenSomeFound:
          "the rest were either first flagged after a control was operated, or may " +
          "have changed since the scan.",
        certain: false,
      };
    }
    const quoted = revealingControls.map((name) => `“${name}”`);
    const list =
      quoted.length === 1
        ? quoted[0]
        : `${quoted.slice(0, -1).join(", ")} and ${quoted[quoted.length - 1]}`;
    const one = revealingControls.length === 1 && targets.length === 1;
    return {
      whenNoneFound:
        `${one ? "This element was" : "These elements were"} first flagged after ` +
        `activating ${list}. This capture is the page as it loaded, so ` +
        `${one ? "it may not appear" : "they may not appear"} here.`,
      whenSomeFound: `the rest were first flagged after activating ${list}, so they may not be in this capture.`,
      certain: true,
    };
  }, [allTargetsRevealed, revealingControls, targets.length, activeStateKey]);

  const frameRef = useRef<HTMLIFrameElement | null>(null);

  // The captured markup is shown via `srcDoc`, which gives the frame no
  // document URL of its own, so every relative stylesheet/font/image in the
  // capture would resolve against the review UI's origin and 404 (the page
  // rendered unstyled). Injecting the page's own URL as <base> makes those
  // subresources resolve against the site they came from. The DOM tab keeps
  // the untouched capture.
  const documentHtml = useMemo(
    () =>
      withBaseHref(
        data?.render.dom_html ?? null,
        data?.render.final_url || data?.page.url || null,
      ),
    [data?.render.dom_html, data?.render.final_url, data?.page.url],
  );

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
    const html = documentHtml;
    if (!showHighlights || !html || scopedTargets.length === 0) {
      setHighlight(null);
      return;
    }
    setHighlight(null); // the raw capture shows while the outline is baked
    scheduleIdle(() => {
      if (request !== highlightRequest.current) return; // superseded
      setHighlight(buildHighlightedHtml(html, scopedTargets));
    });
  }, [showHighlights, documentHtml, scopedTargets]);

  const srcDoc = showHighlights && highlight ? highlight.srcDoc : (documentHtml ?? "");
  const highlightedCount = showHighlights && highlight ? highlight.found : 0;
  const highlightPending = showHighlights && hasTarget && highlight === null;

  // Best-effort: if the sandbox permits contentDocument access, bring the
  // highlighted element into view. Never required, the outline is baked in.
  const scrollToElement = useCallback(() => {
    if (scopedTargets.length === 0) return;
    let attempt = 0;
    const tryScroll = () => {
      try {
        const doc = frameRef.current?.contentDocument;
        if (doc) {
          let el: Element | null = null;
          for (const t of scopedTargets) {
            el = findTargetElement(doc, t);
            if (el) break;
          }
          const target = el as HTMLElement | null;
          if (!target?.scrollIntoView) return;
          keepCentered(target);
          return;
        }
      } catch {
        // Opaque document, the highlight is baked in, only the auto-scroll is lost.
      }
      attempt += 1;
      if (attempt < 10) window.setTimeout(tryScroll, 60);
    };
    tryScroll();
  }, [scopedTargets]);

  // The flagged element's markup, split out of the source so the Loaded DOM tab
  // can wrap it in a <mark>. Null when there is no target or the element is not
  // present in the captured markup. Computed lazily, only when the DOM tab is
  // actually open, because it needs its own unmarked parse of the document.
  const domParts = useMemo(
    () => (tab === "dom" ? highlightInDom(data?.render.dom_html ?? null, scopedTargets) : null),
    [tab, data?.render.dom_html, scopedTargets],
  );
  const domMarkCount = domParts?.filter((s) => s.marked).length ?? 0;

  // Bring the first marked run into view. The source of a real page is far too
  // long to expect anyone to hunt through it for the flagged markup.
  const domPreRef = useRef<HTMLPreElement | null>(null);
  useEffect(() => {
    if (tab !== "dom" || domMarkCount === 0) return;
    const mark = domPreRef.current?.querySelector("mark");
    mark?.scrollIntoView({ block: "center" });
  }, [tab, domMarkCount, domParts]);

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
      <ReportHeader
        scanId={scan}
        previousScanId={scanData?.previous_scan_id ?? null}
        tabs={false}
        title={displayTitle}
        meta={
          <ReportMeta
            counts={
              render.ok
                ? `${
                    render.source === "stored"
                      ? "Stored render"
                      : render.source === "state"
                        ? "Captured state"
                        : "Live render"
                  } (${render.status_code})`
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
          {render.source === "state" ? (
            <>
              {/* A missing state is not a failed render, and must not offer
                  the live page as a substitute: loading the site now shows it
                  at page load, which is the one state the reviewer has just
                  said they do not want. */}
              <p className="text-sm font-semibold text-fg">
                This interaction state was not captured
              </p>
              <p className="mt-1 text-sm text-fg">{render.error}</p>
              <p className="mt-2 text-2xs text-fg-muted">
                To reach it by hand, open the live page and follow the steps in
                the state list above. Switch back to{" "}
                <span className="font-semibold">At page load</span> for the
                markup this report does hold.
              </p>
            </>
          ) : (
            <>
              <p className="text-sm font-semibold text-fg">This page could not be re-rendered</p>
              <p className="mt-1 text-sm text-fg">{render.error}</p>
              <p className="mt-2 text-2xs text-fg-muted">
                The stored scan evidence for this page is still available, use{" "}
                <span className="font-semibold">Open live page</span> to view it
                yourself, or return to the stored page evidence.
              </p>
            </>
          )}
        </Card>
      )}

      {/* Which state, then which view of it. Two separate choices, so they
          are two separate controls rather than one row mixing both axes. A
          select, not the segmented row below: a busy page can reach a dozen
          states and chips would wrap into a block. */}
      {states.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <label htmlFor="inspect-state" className="text-sm font-semibold text-fg">
            Page state
          </label>
          <select
            id="inspect-state"
            className="min-h-target rounded-xs border border-border bg-surface px-3 py-1.5 text-sm text-fg"
            value={activeStateKey ?? ""}
            onChange={(event) => navigate(stateHref(event.target.value || null), { replace: true })}
          >
            <option value="">At page load</option>
            {states.map((state) => (
              <option key={state.state_key} value={state.state_key}>
                {/* The whole chain, not just the last control: reaching a
                    nested state by hand means repeating every step. */}
                {`After clicking ${state.path_labels.length > 0
                  ? state.path_labels.map((label) => `“${label}”`).join(" → ")
                  : `“${state.revealed_by}”`}`}
              </option>
            ))}
          </select>
          {activeStateKey && (
            <span className="text-xs text-fg-muted">
              Captured during the scan, after the control was operated.
            </span>
          )}
        </div>
      )}

      <Tabs
        mode="nav"
        label="How this page was rendered"
        className="mb-4"
        replace
        value={tab}
        items={[
          {
            key: "page",
            label: render.ok ? "Rendered page" : "Page",
            to: viewHref("page"),
          },
          // "Loaded DOM" was accurate while the only document was the page as
          // it loaded. It can now be a state captured after a click, so the
          // name says what it shows rather than when it was taken.
          { key: "dom", label: "DOM source", to: viewHref("dom") },
        ]}
      />

      <div
        id="inspect-panel-page"
        role="region"
        aria-label="Rendered page"
        className="rounded-xs border border-border bg-surface shadow-card"
        hidden={tab !== "page"}
      >
        {render.ok && render.dom_html ? (
          <div>
            {currentFindings.length > 0 && (
              <div className="border-b border-border bg-surface-muted/40 px-3 py-2">
                <p className="text-2xs font-semibold text-fg-subtle">
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
              <span className="text-xs font-semibold text-fg-subtle">
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
                    found,{" "}
                    {missingReason?.whenSomeFound ??
                      "the rest may have changed since the scan."}
                  </span>
                )}
              {!highlightPending && showHighlights && hasScopedTarget && highlightedCount === 0 && (
                // Only drops the error styling when interaction accounts for
                // every miss. Then "not found" is the expected result and
                // flagging it warns about a fact of how the scan works; with a
                // mix, something genuinely should have been matched.
                <span className={missingReason?.certain ? undefined : "text-sev-major"}>
                  {missingReason?.whenNoneFound ??
                    "The flagged element was not found in this capture, it may have changed since the scan."}
                </span>
              )}
              {offStateCount > 0 && (
                // Without this the issue looks smaller in a state view than it
                // is: the picker is the only way to the rest of it.
                <span>
                  {offStateCount} more {offStateCount === 1 ? "occurrence" : "occurrences"} of
                  this issue {offStateCount === 1 ? "is" : "are"} in another state.
                </span>
              )}
              {!showHighlights && hasScopedTarget && (
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
            {/* Outside the live region above: this is standing context about
                the capture, not a status that changes, so it should not be
                re-announced every time the highlight count updates. */}
            <p className="border-t border-border px-3 py-2 text-2xs text-fg-muted">
              The markup is the stored capture; its stylesheets, fonts and
              images load from the live site now, so styling can differ from
              how the page looked when it was scanned. The page&rsquo;s own scripts
              never run here, so a flagged element the site would have revealed
              with JavaScript is forced visible to be highlighted.
            </p>
          </div>
        ) : (
          <div className="p-6 text-sm text-fg-muted">
            {render.error || "The page could not be rendered."}
          </div>
        )}
      </div>

      <div
        id="inspect-panel-dom"
        role="region"
        aria-label="Loaded DOM"
        className="rounded-xs border border-border bg-surface shadow-card"
        hidden={tab !== "dom"}
      >
        {render.ok && render.dom_html ? (
          <div className="p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <p className="flex items-center gap-1.5 text-2xs font-semibold text-fg-subtle">
                <FileCode2 className="h-4 w-4" aria-hidden />
                Loaded DOM, captured at render time
              </p>
              <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                {hasScopedTarget && (
                  <span className="text-2xs text-fg-muted">
                    {domMarkCount > 0
                      ? `${domMarkCount} flagged ${domMarkCount === 1 ? "element is" : "elements are"} marked in the source below.`
                      : (missingReason?.whenNoneFound ??
                        "The flagged markup was not found in this capture.")}
                  </span>
                )}
                {render.dom_truncated && (
                  <span className="text-2xs text-sev-major">
                    Truncated for length (shown at 2,000,000 characters).
                  </span>
                )}
              </span>
            </div>
            {/* Scanned page markup is untrusted and rendered as escaped text,
                never executed. Each flagged element's markup is wrapped in a
                <mark> so it is visible in the source, matching the page view. */}
            <pre
              ref={domPreRef}
              role="region"
              aria-label="Loaded DOM source"
              // Keyboard users need focus on the overflow region to scroll the
              // source. The panel wrapper is not the scroll container — this
              // is — so the tabIndex has to sit here to satisfy SC 2.1.1.
              // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
              tabIndex={0}
              // A serialized DOM is one enormous line, so an unwrapped <pre>
              // shows a mostly empty box with everything scrolled off to the
              // right. Wrapping (breaking inside long attribute values) keeps
              // the marked markup readable in place.
              className="max-h-[70vh] overflow-auto whitespace-pre-wrap break-all rounded-2xs border border-border bg-surface-muted p-3 text-2xs leading-relaxed text-fg focus-visible:shadow-focus"
            >
              <code>
                {domParts
                  ? domParts.map((segment, i) =>
                      segment.marked ? (
                        <mark
                          key={i}
                          className="rounded-[2px] bg-umich-maize/40 px-0 text-fg outline outline-1 outline-umich-maize"
                        >
                          {segment.text}
                        </mark>
                      ) : (
                        <Fragment key={i}>{segment.text}</Fragment>
                      ),
                    )
                  : render.dom_html}
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

/**
 * Give the captured markup the page's own URL as its base.
 *
 * A `srcDoc` frame has no document URL, so a capture's relative and
 * root-relative subresources (`href="/site.css"`, `src="logo.png"`) would be
 * requested from the review UI's origin and 404 — the page renders with no CSS
 * at all. A single `<base href>` restores the original resolution, so the frame
 * loads the site's real stylesheets, fonts and images.
 *
 * Left untouched when the capture already carries its own `<base href>` (the
 * first one in the document wins, and the page's own is the authoritative one)
 * or when the URL is not an http(s) address we should point a browser at.
 */
function withBaseHref(html: string | null, url: string | null): string | null {
  if (!html || !url) return html;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return html;
  } catch {
    return html;
  }
  if (/<base\b[^>]*\bhref\b/i.test(html)) return html;
  const tag = `<base href="${escapeAttribute(url)}">`;
  const head = /<head\b[^>]*>/i.exec(html);
  if (head) {
    const at = head.index + head[0].length;
    return html.slice(0, at) + tag + html.slice(at);
  }
  // No <head> in the capture (rare, but a malformed document can serialize
  // without one): put it ahead of everything so it still applies.
  const htmlTag = /<html\b[^>]*>/i.exec(html);
  if (htmlTag) {
    const at = htmlTag.index + htmlTag[0].length;
    return html.slice(0, at) + `<head>${tag}</head>` + html.slice(at);
  }
  return tag + html;
}

function escapeAttribute(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

/**
 * Center ``target`` in its frame and hold it there while the layout settles.
 *
 * A single `scrollIntoView` is not enough: the capture's stylesheets, fonts and
 * images are fetched from the live site *after* the frame fires `load`, and
 * every one of them reflows the document, so an element centered at load time
 * drifts far off-screen a moment later. This re-centers until the element's
 * position in the document stops moving (two consecutive quiet checks), with a
 * hard ceiling so a page that never stops animating cannot spin forever.
 */
function keepCentered(target: HTMLElement): void {
  let previous: number | null = null;
  let quiet = 0;
  let ticks = 0;
  const step = () => {
    try {
      const win = target.ownerDocument?.defaultView;
      if (!target.isConnected || !win) return;
      // Position in the *document*, not the viewport: the viewport-relative
      // top barely moves once we have centered it, so it cannot tell us
      // whether the page beneath is still reflowing.
      const top = target.getBoundingClientRect().top + win.scrollY;
      quiet = previous !== null && Math.abs(top - previous) < 2 ? quiet + 1 : 0;
      previous = top;
      target.scrollIntoView({ block: "center" });
      ticks += 1;
      if (quiet < 2 && ticks < 20) window.setTimeout(step, 300);
    } catch {
      // The frame navigated or unmounted mid-settle; nothing left to center.
    }
  };
  step();
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

/** A run of the captured source, either plain or inside a highlight mark. */
type DomSegment = { text: string; marked: boolean };

/**
 * Split the captured HTML into segments so every flagged occurrence can be
 * marked in the Loaded DOM (source) tab, matching what the Rendered page tab
 * outlines. Each target is located in the parsed document and its markup found
 * in the source; overlapping matches are merged so the marks can never cross.
 * Returns ``null`` when nothing could be located (the source is then shown
 * unhighlighted rather than guessed at).
 */
function highlightInDom(html: string | null, targets: Target[]): DomSegment[] | null {
  if (!html || targets.length === 0) return null;
  let doc: Document | null = null;
  try {
    doc = new DOMParser().parseFromString(html, "text/html");
  } catch {
    doc = null; // fall through to matching the stored snippets literally
  }

  const ranges: Array<[number, number]> = [];
  for (const target of targets) {
    const located = doc ? findTargetElement(doc, target) : null;
    // The element's own serialization first. It can differ from the source
    // text (the parser normalizes quoting, entities and void elements), so the
    // stored snippet is the fallback: it is frequently the literal source.
    for (const candidate of [located?.outerHTML, target.snippet]) {
      if (!candidate) continue;
      const index = html.indexOf(candidate);
      if (index >= 0) {
        ranges.push([index, index + candidate.length]);
        break;
      }
    }
  }
  if (ranges.length === 0) return null;

  // Merge overlaps so nested or repeated matches can't produce crossing marks.
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: Array<[number, number]> = [];
  for (const range of ranges) {
    const last = merged[merged.length - 1];
    if (last && range[0] <= last[1]) last[1] = Math.max(last[1], range[1]);
    else merged.push([range[0], range[1]]);
  }

  const segments: DomSegment[] = [];
  let cursor = 0;
  for (const [start, end] of merged) {
    if (start > cursor) segments.push({ text: html.slice(cursor, start), marked: false });
    segments.push({ text: html.slice(start, end), marked: true });
    cursor = end;
  }
  if (cursor < html.length) segments.push({ text: html.slice(cursor), marked: false });
  return segments;
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
  const buckets = new Map<
    string,
    { raw: string; needle: string; head: string; startTag: boolean }[]
  >();
  for (const t of targets) {
    if (!t.snippet) continue;
    const needle = normalizeWhitespace(t.snippet);
    if (!needle) continue;
    const tag = firstTagName(t.snippet) ?? "";
    const entry = {
      raw: t.snippet,
      needle,
      head: t.snippet.slice(0, SNIPPET_HEAD),
      startTag: isStartTagOnly(t.snippet),
    };
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
              (entry.startTag &&
                normalizeWhitespace(raw).startsWith(entry.needle)) ||
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
    startTagMatches(raw, needle, snippet) ||
    truncatedSnippetMatches(raw, needle)
  );
}

/**
 * True when `snippet` is a bare start tag: one tag, nothing inside it, no
 * closing tag.
 *
 * axe reports a container element as its start tag alone — `<div id="portal-1"
 * class="category-menu" role="listbox">` — rather than the element with its
 * subtree. No non-empty element's `outerHTML` can equal that, so equality is
 * simply the wrong test, and every container finding failed to highlight:
 * the page said the element "was not found in this capture" while the element
 * sat in the document being searched.
 *
 * Matching one is therefore a prefix test. A complete start tag carries the
 * element's whole attribute list, which is specific enough to identify it; two
 * elements that agree on every attribute are the identical siblings this
 * inspector already treats as one location.
 */
function isStartTagOnly(snippet: string): boolean {
  const trimmed = snippet.trim();
  return (
    trimmed.length > 2 &&
    trimmed.startsWith("<") &&
    trimmed.endsWith(">") &&
    trimmed.indexOf("<", 1) === -1
  );
}

function startTagMatches(raw: string, needle: string, snippet: string): boolean {
  return isStartTagOnly(snippet) && normalizeWhitespace(raw).startsWith(needle);
}

function truncatedSnippetMatches(raw: string, needle: string): boolean {
  if (needle.length < TRUNCATED_SNIPPET_LENGTH) return false;
  return normalizeWhitespace(raw).startsWith(needle);
}

function markElement(el: HTMLElement, outlineColor: string, bg: string): void {
  el.classList.add("axcess-inspect-highlight");
  el.style.setProperty("outline", `3px solid ${outlineColor}`, "important");
  // Inset, not outset. A flagged element that fills an `overflow: hidden`
  // ancestor (the ubiquitous image-tile pattern: `w-full h-full` inside a
  // clipped tile) has an outset ring drawn entirely outside the clip box, so
  // it is never painted. Drawing just inside the border box is always visible.
  el.style.setProperty("outline-offset", "-3px", "important");
  el.style.setProperty("background-color", bg, "important");
  el.style.setProperty("scroll-margin-top", "96px", "important");
  forceVisible(el);
  // An ancestor can hide the element no matter what we set on the element
  // itself (opacity is inherited-by-compositing, not by cascade), so the whole
  // chain has to be cleared too.
  let parent = el.parentElement;
  while (parent && parent !== el.ownerDocument.documentElement) {
    forceVisible(parent);
    parent = parent.parentElement;
  }
}

/**
 * Undo the ways a *frozen* page hides an element we need to point at.
 *
 * The frame runs the capture with scripts disabled, so any state the site's
 * own JS would have transitioned out of stays exactly as it was at scan time.
 * The common case is a lazy-loaded image still carrying `opacity-0` because
 * the load handler that swaps in `opacity-100` never runs; scroll-reveal
 * wrappers behave the same way. Those elements are genuinely invisible, and so
 * is any highlight on them.
 *
 * Transitions and animations are cleared as well so nothing re-hides what we
 * just revealed. This only ever touches the flagged element and its ancestors.
 */
function forceVisible(el: HTMLElement): void {
  el.style.setProperty("opacity", "1", "important");
  el.style.setProperty("visibility", "visible", "important");
  el.style.setProperty("animation", "none", "important");
  el.style.setProperty("transition", "none", "important");
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
