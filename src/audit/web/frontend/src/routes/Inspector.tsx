import { type ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { serverDate } from "../lib/serverTime";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { keepPreviousData, useQueries, useQuery } from "@tanstack/react-query";
import { Check, ChevronDown, ChevronUp, Copy, ExternalLink, FileCode2, Layers, Loader2 } from "lucide-react";
import DomSource from "../components/DomSource";
import FlaggedStepper from "../components/FlaggedStepper";
import { api } from "../api/client";
import type { PageEvidence, PageInspection, SavedStyles } from "../api/types";
import ReportHeader, { ReportMeta } from "../components/ReportHeader";
import Tabs from "../components/Tabs";
import {
  Button,
  Card,
  Disclosure,
  EmptyState,
  ExternalLinkButton,
  LinkButton,
  pageEvidencePath,
  Select,
} from "../components/ui";
import { useScanQuery } from "../hooks/useScanQuery";
import { cn } from "../lib/cn";
import {
  boxPlace,
  type BoxNote,
  buildHighlightedHtml,
  countFound,
  describeElement,
  drawnOnCanvas,
  drawsNoBox,
  findTargetElement,
  focusInCopy,
  HIGHLIGHT_CLASS,
  markCurrent,
  noteCurrent,
  normalizeWhitespace,
  readableLocator,
  scrollPanels,
  snippetCutFor,
  spotlight,
  type ElementDescription,
  type HighlightResult,
  type Target,
  type Unreachable,
} from "../lib/highlightTargets";
import { checkFingerprint, looksDifferent } from "../lib/styleFingerprint";

type TabId = "page" | "dom";

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
 * into the markup, computed off the main render path). When the scan saved
 * the copy's CSS, the frame uses that file from this app instead of the
 * site's stylesheets (see `prepareCapture`). The capture is also given the
 * page's own URL as `<base href>`, without which its relative fonts, images
 * and (for older reports) stylesheets would resolve against the review UI
 * (see `withBaseHref`); the "Loaded DOM" tab
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
  // A zoom and layout issue opens the saved page the way the check saw it:
  // its window size, or its text spacing. "Show at full width" compares.
  const checkLayout = useMemo(() => layoutForIssue(issueKey), [issueKey]);
  const [asChecked, setAsChecked] = useState(true);
  const layout = checkLayout && asChecked ? checkLayout : null;
  const directSelector = params.get("selector");
  const directSnippet = params.get("snippet");

  const { data: scanData } = useScanQuery(scan);

  // Fetch the page's full evidence so we can resolve the current issue's
  // finding(s) on this page, and only those, not every issue the page happens
  // to carry.
  const { data: pageEvidence, isError: evidenceError } = useQuery({
    queryKey: ["page-evidence", scan, page],
    queryFn: () => api.getPageEvidence(scan, page),
    enabled: Number.isFinite(scan) && Number.isFinite(page),
  });

  // The findings that belong to the issue being reviewed on this page. For the
  // ?issue= path this is every finding of the issue (an issue can have several
  // occurrences on one page); for a direct selector/snippet it is that one
  // finding. Only these are highlighted, not other issues on the page.
  const currentFindings = useMemo(() => {
    if (!pageEvidence) return [];
    if (issueKey) {
      return pageEvidence.a11y_findings.filter(
        (f) => findingInIssue(f, issueKey) && (f.target_selector || f.html_snippet),
      );
    }
    return pageEvidence.a11y_findings.filter(
      (f) =>
        (directSelector && f.target_selector === directSelector) ||
        (directSnippet && f.html_snippet === directSnippet),
    );
  }, [pageEvidence, issueKey, directSelector, directSnippet]);

  // An Images with text issue's occurrences on this page: images, which carry
  // no selector. One row per occurrence (the evidence lists an image once per
  // analysis of it).
  const currentImages = useMemo(() => {
    if (!pageEvidence || !issueKey?.startsWith("image:")) return [];
    const seen = new Set<number>();
    return pageEvidence.image_occurrences.filter((image) => {
      if (image.issue_key !== issueKey || seen.has(image.occurrence_id)) return false;
      seen.add(image.occurrence_id);
      return true;
    });
  }, [pageEvidence, issueKey]);
  // Copies inside <noscript> or <template> (in practice the no-script fallback
  // of a lazy-loaded image, whose shown twin is outlined): not in the saved
  // copy on screen, so they are said, not counted as missing.
  const shownImages = useMemo(() => currentImages.filter((image) => !image.hidden_in_copy), [currentImages]);
  const hiddenImageCount = currentImages.length - shownImages.length;

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
      // A duplicate only when the state, the locator and the markup all
      // agree. Keyed on the markup alone, two elements with identical markup
      // (a repeated link, each with its own selector) collapsed into one, so
      // the second was never outlined; and an occurrence in a clicked state
      // was dropped when the same markup was also flagged at page load.
      const key = [
        f.revealed_state_key ?? "",
        selector ?? "",
        snippet ? normalizeWhitespace(snippet) : "",
      ].join("\u0000");
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({
        selector,
        snippet,
        revealedBy: f.revealed_by || null,
        stateKey: f.revealed_state_key || null,
        place: f.element_place,
        cutAt: snippetCutFor(f.pipeline),
      });
    }
    // Images were read at page load. Each occurrence is its own element.
    for (const image of shownImages) {
      out.push({
        selector: null,
        snippet: null,
        revealedBy: null,
        stateKey: null,
        image: { locator: image.locator, alt: image.alt_text },
      });
    }
    return out;
  }, [currentFindings, shownImages]);
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
  // The default is where the issue can be seen, not the page as it loaded:
  // arriving here from a revealed finding and being shown a document that
  // cannot contain it is the whole complaint. See ``autoState`` below.
  const findingStateKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const target of targets) if (target.stateKey) keys.add(target.stateKey);
    return keys;
  }, [targets]);
  const reviewing = Boolean(issueKey || directSelector || directSnippet);
  const evidenceReady = !!pageEvidence || evidenceError;
  /** Whether the page as it loaded holds any occurrence under review. */
  const issueAtLoad = targets.some((target) => target.stateKey === null);
  /** Every occurrence under review came after a click; page load holds none. */
  const issueOnlyAfterClicks = reviewing && !issueAtLoad && findingStateKeys.size > 0;

  /**
   * Which states' captures no longer hold their flagged elements.
   *
   * Every state holding an occurrence of the issue under review is checked,
   * not only the one on screen: the picker labels each of them, and the
   * inspector opens on one that can actually be highlighted. Each capture is
   * fetched (a stored document, never a live render) and run through the
   * same matcher the highlight uses, so a label, the opening choice, and the
   * highlight can never disagree. The queries share the on-screen query's
   * key, so switching to a checked state is served from cache.
   */
  const checkedStates = useMemo(
    () => (reviewing ? [...findingStateKeys] : []),
    [findingStateKeys, reviewing],
  );
  const stateCaptures = useQueries({
    queries: checkedStates.map((key) => ({
      queryKey: ["page-inspection", scan, page, key],
      queryFn: () => api.getPageInspection(scan, page, key),
      enabled: inspectEnabled,
      retry: false,
    })),
  });
  const captureVersions = stateCaptures.map((query) => query.dataUpdatedAt).join(",");
  // Stamped with the capture versions it was computed from, so "every check
  // has finished" means for these captures, not for an earlier set.
  const [checked, setChecked] = useState<{
    versions: string;
    missing: ReadonlyMap<string, MissingCount>;
  }>(() => ({ versions: "", missing: new Map() }));
  const missingByState = checked.missing;
  useEffect(() => {
    let cancelled = false;
    const versions = captureVersions;
    const captures = checkedStates.map((key, index) => [key, stateCaptures[index]?.data] as const);
    scheduleIdle(() => {
      if (cancelled) return;
      const next = new Map<string, MissingCount>();
      for (const [key, inspection] of captures) {
        const stateTargets = targets.filter((target) => target.stateKey === key);
        // A state that was never captured has its own message; there is no
        // document to be missing anything from.
        if (!inspection?.render.ok || !inspection.render.dom_html || !stateTargets.length) continue;
        const html = prepareCapture(
          inspection.render.dom_html,
          inspection.render.final_url || inspection.page.url || null,
          savedStylesFor(inspection)?.url ?? null,
        );
        const found = countFound(html, stateTargets);
        next.set(key, { missing: stateTargets.length - found, total: stateTargets.length });
      }
      setChecked({ versions, missing: next });
    });
    return () => {
      cancelled = true;
    };
    // captureVersions stands in for stateCaptures, a new array every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [captureVersions, checkedStates, targets]);
  // Where to open when the URL does not say. An issue present at page load
  // opens there. One found only after clicks opens on the first state (in
  // the order the probe reached them) whose capture actually holds its
  // element, so the reviewer lands on the defect highlighted rather than on
  // a document that cannot contain it; if none does, on the first state
  // that holds the issue at all. Undefined while that is still being worked
  // out, and decided once per page and issue so the view never jumps.
  const settled =
    stateCaptures.every((query) => query.isSuccess || query.isError) &&
    checked.versions === captureVersions;
  const autoState: string | null | undefined = !evidenceReady
    ? undefined
    : !issueOnlyAfterClicks
      ? null
      : settled
        ? (checkedStates.find((key) => {
            const count = missingByState.get(key);
            return count != null && count.missing < count.total;
          }) ?? checkedStates[0])
        : undefined;
  const openingScope = [scan, page, issueKey, directSelector, directSnippet].join("\n");
  const [opening, setOpening] = useState<{ scope: string; state: string | null } | null>(null);
  useEffect(() => {
    if (autoState !== undefined && opening?.scope !== openingScope) {
      setOpening({ scope: openingScope, state: autoState });
    }
  }, [autoState, opening, openingScope]);
  const defaultStateKey = opening?.scope === openingScope ? opening.state : autoState;
  const requestedState = params.get("state");
  const stateKey = requestedState ?? defaultStateKey;

  const { data, isLoading, isFetching, error } = useQuery({
    // The state belongs in the key: without it every finding on the page
    // would share one cached document and the picker would appear to do
    // nothing.
    queryKey: ["page-inspection", scan, page, stateKey],
    queryFn: () => api.getPageInspection(scan, page, stateKey),
    enabled: inspectEnabled && stateKey !== undefined,
    retry: false,
    // Hold the document already on screen while the next one is fetched.
    // Without it a state the cache has not seen makes `isLoading` true, the
    // route returns its spinner, and the picker the reviewer just operated is
    // unmounted mid-interaction: focus falls to <body> and the keyboard path
    // is lost. Keeping the previous data keeps the control mounted.
    placeholderData: keepPreviousData,
  });

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
   * Each finding belongs to exactly one state, the one it was first seen in.
   * A revealed state is the page plus whatever the click added, so load-state
   * markup is usually still in it, but listing it again there presented one
   * element once per state. It stays under "At page load" and the off-state
   * count points the reviewer to it.
   */
  /**
   * The occurrences that belong to the document on screen.
   *
   * An issue can span several states, and the evidence list was showing all of
   * them whichever state was selected: "At page load" listed markup that only
   * exists after a click, and a revealed state listed occurrences belonging to
   * a different control. Both are the same mistake this view exists to stop —
   * attaching evidence to a state that does not contain it.
   */
  const scopedFindings = useMemo(
    () => currentFindings.filter((f) => (f.revealed_state_key || null) === activeStateKey),
    [currentFindings, activeStateKey],
  );
  // Images were read at page load, so they belong to that state alone.
  const scopedImages = activeStateKey === null ? currentImages : [];
  const evidenceCount = scopedFindings.length + scopedImages.length;

  /**
   * The states worth offering for the issue being reviewed.
   *
   * A page keeps a capture for every state that revealed *any* new defect, so
   * an assignment dashboard has six. Opening one issue and being offered all
   * six says nothing about which of them holds it — five are about other
   * rules entirely. Only the states carrying an occurrence of this issue are
   * listed, with their counts, and "At page load" stays as the baseline the
   * others are read against.
   *
   * An issue found only at page load is offered no revealed states at all:
   * none of them holds an occurrence of it.
   *
   * With nothing specific under review (no `?issue=` or `?selector=`), every
   * state is offered: then the picker is for exploring, not for locating.
   */
  const offeredStates = useMemo(() => {
    const all = data?.states ?? [];
    if (!reviewing) return all;
    return all.filter((state) => findingStateKeys.has(state.state_key));
  }, [data?.states, findingStateKeys, reviewing]);

  /** Occurrences of this issue that were already present at page load. */
  const loadStateCount = useMemo(
    () => currentFindings.filter((f) => !f.revealed_state_key).length + shownImages.length,
    [currentFindings, shownImages],
  );

  const occurrencesByState = useMemo(() => {
    const counts = new Map<string, number>();
    for (const finding of currentFindings) {
      const key = finding.revealed_state_key;
      if (key) counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return counts;
  }, [currentFindings]);

  /**
   * The page states other than the one on screen that hold occurrences, for
   * the line under the picker: page load first, then each state in the
   * picker's order. `key` is "" for page load, as in the picker.
   */
  const elsewhere = useMemo(() => {
    const active = data?.render.state_key ?? null;
    const out: { key: string; label: string; count: number }[] = [];
    if (active && loadStateCount > 0) out.push({ key: "", label: "At page load", count: loadStateCount });
    for (const state of offeredStates) {
      const count = occurrencesByState.get(state.state_key) ?? 0;
      if (count > 0 && state.state_key !== active) {
        out.push({ key: state.state_key, label: `After clicking ${clickChain(state)}`, count });
      }
    }
    return out;
  }, [data?.render.state_key, loadStateCount, offeredStates, occurrencesByState]);
  const elsewhereCount = elsewhere.reduce((total, state) => total + state.count, 0);

  const scopedTargets = useMemo(
    () => targets.filter((target) => target.stateKey === activeStateKey),
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
          "Some of these were first flagged after a click on a control. This copy " +
          "shows the page at page load, so they may not be in it. The others " +
          "may have changed since the scan.",
        whenSomeFound:
          "The others were first flagged after a click on a control, or the page " +
          "may have changed since the scan.",
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
        `clicking ${list}. This copy shows the page at page load, so ` +
        `${one ? "it may not appear" : "they may not appear"} here.`,
      whenSomeFound: `The others were first flagged after clicking ${list}, so they may not be in this copy.`,
      certain: true,
    };
  }, [allTargetsRevealed, revealingControls, targets.length, activeStateKey]);

  const frameRef = useRef<HTMLIFrameElement | null>(null);

  // The captured markup is shown via `srcDoc`, which gives the frame no
  // document URL of its own, so every relative stylesheet/font/image in the
  // capture would resolve against the review UI's origin and 404 (the page
  // rendered unstyled). Injecting the page's own URL as <base> makes those
  // subresources resolve against the site they came from, and a copy whose
  // CSS the scan saved uses that instead of the site's stylesheets (see
  // `prepareCapture`). The DOM tab keeps the untouched capture.
  const savedStyles = data ? savedStylesFor(data) : null;
  const savedStylesUrl = savedStyles?.url ?? null;
  const documentHtml = useMemo(
    () =>
      prepareCapture(
        data?.render.dom_html ?? null,
        data?.render.final_url || data?.page.url || null,
        savedStylesUrl,
      ),
    [data?.render.dom_html, data?.render.final_url, data?.page.url, savedStylesUrl],
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
    // Located even with highlights hidden: whether the flagged element is in
    // this capture at all is labelled at the state picker either way.
    if (!html || scopedTargets.length === 0) {
      setHighlight(null);
      return;
    }
    setHighlight(null); // the raw capture shows while the outline is baked
    scheduleIdle(() => {
      if (request !== highlightRequest.current) return; // superseded
      setHighlight(buildHighlightedHtml(html, scopedTargets));
    });
  }, [documentHtml, scopedTargets]);

  const pageDoc = showHighlights && highlight ? highlight.srcDoc : (documentHtml ?? "");
  const srcDoc = layout?.css ? withStyle(pageDoc, layout.css) : pageDoc;
  const highlightedCount = showHighlights && highlight ? highlight.found : 0;
  const unreachableCount = highlight ? highlight.unreachable.shadow + highlight.unreachable.frame : 0;
  // Only what this view can hold: a view whose targets are all in other
  // states has nothing to highlight, and must not wait for it forever.
  const highlightPending = showHighlights && scopedTargets.length > 0 && highlight === null;

  /** Missing elements for one picker option; the state on screen uses its highlight. */
  const missingFor = (key: string): MissingCount | undefined => {
    if (key === (activeStateKey ?? "")) {
      return highlight && !isFetching
        ? {
            // One no saved copy can hold is not missing from this one.
            missing: highlight.total - highlight.located - unreachableCount,
            total: highlight.total,
          }
        : undefined;
    }
    return missingByState.get(key);
  };

  // Best-effort: if the sandbox permits contentDocument access, bring the
  // highlighted element into view. Never required, the outline is baked in.
  const scrollToElement = useCallback(() => {
    if (scopedTargets.length === 0) return;
    let attempt = 0;
    const tryScroll = () => {
      try {
        const doc = frameRef.current?.contentDocument;
        if (doc) {
          // The first outlined element in document order, so the view and
          // "Flagged element 1 of N" agree; the targets themselves when the
          // highlights are hidden.
          if (showMark(doc, 0)) return;
          let el: Element | null = null;
          for (const t of scopedTargets) {
            if (el) break;
            el = findTargetElement(doc, t);
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

  // Whether the saved copy is a page drawn on a drawing area (canvas), which
  // it cannot keep: said under the frame, highlights or not, since no
  // outline can point at anything the page drew. Checked when it loads, and
  // kept with the document it was checked in: a srcDoc frame can load before
  // an effect keyed on it would run.
  const [canvasCheck, setCanvasCheck] = useState<{ doc: string; drawn: boolean } | null>(null);
  const canvasPage = canvasCheck?.doc === srcDoc && canvasCheck.drawn;
  // Whether the saved copy, with its saved styles, still looks like the page
  // the scan checked (see ``lib/styleFingerprint``). Measured once its fonts
  // have settled, and kept with the document it was measured in, as above.
  const [styleCheck, setStyleCheck] = useState<{ doc: string; differs: boolean } | null>(null);
  const stylesDiffer = styleCheck?.doc === srcDoc && styleCheck.differs;
  const fingerprint = savedStyles?.fingerprint ?? null;
  const onFrameLoad = useCallback(() => {
    scrollToElement();
    try {
      const frame = frameRef.current;
      const doc = frame?.contentDocument;
      // Show the app's focus ring while focus is inside the saved copy. A
      // focused iframe matches none of :focus, :focus-within or
      // :focus-visible in the app's page, so CSS alone never drew a ring
      // and keyboard users could not see that focus had moved into the copy
      // (SC 2.4.7 Focus Visible, Level AA; October 2026 AAA audit). The copy
      // is same-origin, so its window's own focus and blur mark the frame,
      // and styles.css draws the ring on iframe[data-focused]. A new load
      // brings a new window, so the listeners never pile up.
      const view = frame?.contentWindow;
      if (frame && view) {
        delete frame.dataset.focused;
        view.addEventListener("focus", () => {
          frame.dataset.focused = "true";
        });
        view.addEventListener("blur", () => {
          delete frame.dataset.focused;
        });
      }
      // Escape inside the saved copy goes back to "Go to this element",
      // the way in (see there). The copy runs no scripts of its own, so no
      // key of the page's is taken.
      doc?.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && goToRef.current) {
          event.preventDefault();
          goToRef.current.focus();
        }
      });
      if (frame && doc) {
        setCanvasCheck({ doc: frame.srcdoc, drawn: drawnOnCanvas(doc) });
        if (fingerprint?.samples?.length) {
          const measured = frame.srcdoc;
          // `load` already waited for the stylesheets; fonts can still be
          // arriving, and one more settle tick lets late layout finish.
          void (doc.fonts?.ready ?? Promise.resolve())
            .then(() => new Promise((resolve) => window.setTimeout(resolve, 300)))
            .then(() => {
              if (frameRef.current?.srcdoc !== measured) return;
              setStyleCheck({ doc: measured, differs: looksDifferent(checkFingerprint(doc, fingerprint)) });
            })
            .catch(() => undefined);
        }
      }
    } catch {
      // Opaque document: nothing to measure.
    }
  }, [scrollToElement, fingerprint]);

  // What the element the reader is on is, for the line under the toolbar,
  // and the locator the occurrence was recorded with.
  const [currentElement, setCurrentElement] = useState<ElementDescription | null>(null);
  useEffect(() => setCurrentElement(null), [srcDoc]);

  /**
   * Make outlined element ``index`` the current one: solid outline, the
   * numbered box over it, scrolled to the centre, and described. False when
   * the document has no outlined elements (highlights off, or none found).
   */
  function showMark(doc: Document, index: number): boolean {
    const marks = Array.from(doc.querySelectorAll<HTMLElement>(`.${HIGHLIGHT_CLASS}`));
    if (marks.length === 0) {
      spotlight(null, "", doc);
      noteCurrent(doc, null, "");
      return false;
    }
    marks.forEach((mark, i) => markCurrent(mark, i === index));
    const target = marks[index] ?? null;
    spotlight(target, marks.length > 1 ? `${index + 1} of ${marks.length}` : "Flagged element", doc, (el) =>
      setCurrentElement(describeElement(el)),
    );
    noteCurrent(doc, target, marks.length > 1 ? `Flagged element ${index + 1} of ${marks.length}` : "Flagged element");
    if (target) keepCentered(target);
    return true;
  }

  // Which outlined element the reader is on, for Previous / Next in the
  // saved copy, as the Page code (DOM) tab has. Back to the first whenever the
  // frame's document changes.
  const [pageMark, setPageMark] = useState(0);
  useEffect(() => setPageMark(0), [srcDoc]);
  const currentTarget = scopedTargets[highlight?.steps[pageMark]?.targets[0] ?? -1];
  const currentLocator = readableLocator(currentTarget?.selector ?? null);
  // An image or an AI review finding is found by its place among elements of
  // its kind; its selector (``a[ord=6]``) is not one a browser can use.
  const currentPlace = currentTarget?.image?.locator
    ? {
        selector: currentTarget.image.locator.kind === "source" ? "picture > source" : currentTarget.image.locator.kind,
        index: currentTarget.image.locator.index,
        total: currentTarget.image.locator.total,
      }
    : (currentTarget?.place ?? null);
  const currentAddress = currentTarget?.image?.locator?.candidate ?? null;
  // How many occurrences share the element the reader is on.
  const sharedCount = highlight?.steps[pageMark]?.targets.length ?? 0;
  // readableLocator returns a selector unchanged and turns a Rule check
  // (Alfa) record into its XPath, so a changed string is an XPath. An AI
  // review selector such as ``a[ord=6]`` counts the analyzer's own list of
  // links, which no browser can use: it is not shown as a locator at all
  // (the table still says what the element is).
  const locatorIsXPath = currentLocator !== null && currentLocator !== currentTarget?.selector;
  const shownLocator = currentLocator && !/\[ord=\d+\]/.test(currentLocator) ? currentLocator : null;
  const locatorTerm = locatorIsXPath ? "Element locator (XPath)" : "Element locator (CSS selector)";
  // Whether the locator is shown in full. It stays as the reader set it while
  // they step, so every element's row keeps the same shape.
  const [locatorOpen, setLocatorOpen] = useState(false);
  // "Go to this element in the saved copy": the button, to come back to with
  // Escape, and what it says when the element cannot take focus.
  const goToRef = useRef<HTMLButtonElement>(null);
  const [goToNote, setGoToNote] = useState<{ attempt: number; text: string } | null>(null);
  const goToAttempts = useRef(0);
  useEffect(() => setGoToNote(null), [srcDoc, pageMark]);
  const goToElement = () => {
    goToAttempts.current += 1;
    const attempt = goToAttempts.current;
    let landed = false;
    try {
      const target = frameRef.current?.contentDocument?.querySelector<HTMLElement>("[data-axcess-current]");
      landed = Boolean(target && focusInCopy(target));
      if (target && landed && frameRef.current) {
        keepCentered(target);
        revealInPage(frameRef.current, target);
      }
    } catch {
      // Opaque document: focus cannot be moved into it.
    }
    setGoToNote(
      landed
        ? null
        : {
            attempt,
            text: "This element cannot take focus in the saved copy, because it is hidden there or it is the whole page. The table above describes it.",
          },
    );
  };
  const goToPageMark = (index: number) => {
    const bounded = Math.max(0, Math.min(highlightedCount - 1, index));
    setPageMark(bounded);
    try {
      const doc = frameRef.current?.contentDocument;
      if (!doc) return;
      showMark(doc, bounded);
    } catch {
      // Opaque document: the outlines are baked in, only the stepping is lost.
    }
  };

  // The Loaded DOM tab locates the flagged elements in its own inert parse of
  // the capture and reports how many it found; the count feeds the header line
  // beside the source. Stable across renders so the source is not re-walked
  // on every state change.
  const [domMarkCount, setDomMarkCount] = useState(0);
  const locateFlagged = useCallback(
    (doc: Document) =>
      scopedTargets
        .map((target) => findTargetElement(doc, target))
        .filter((element): element is Element => element !== null),
    [scopedTargets],
  );

  if (error) {
    return (
      <EmptyState
        title="This page cannot be shown"
        message={
          error instanceof Error
            ? error.message
            : "Axcess could not show this page. The scan may still be running, the page may be from a sign-in scan, or the page may be outside the scan's scope."
        }
        action={
          <LinkButton
            to={pageEvidencePath({
              scanId: scan,
              pageId: page,
              origin: params.get("origin") ?? undefined,
              backTo: params.get("back") ?? undefined,
            })}
            variant="primary"
          >
            Back to page evidence
          </LinkButton>
        }
      />
    );
  }
  if (stateKey === undefined) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-fg-muted" role="status">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Finding the page state where this issue appears…
      </div>
    );
  }
  if (isLoading || !data) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-fg-muted" role="status">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Getting the page ready…
      </div>
    );
  }

  const { page: pageInfo, render } = data;
  const displayTitle = pageInfo.title || pageInfo.url;
  const liveUrl = pageInfo.url;
  const status = render.status_code != null && render.status_code !== 200 ? ` (server code ${render.status_code})` : "";
  const renderNote = !render.ok
    ? "Could not load the live page"
    : render.source === "stored"
      ? status
        ? `Saved copy${status}`
        : null
      : render.source === "state"
        ? `Saved page state${status}`
        : `Live page${status}`;
  // What the first tab holds: a copy the scan saved, or the live page
  // loaded just now because no copy was saved.
  const copyName =
    render.source === "stored" || render.source === "state" ? "Saved copy" : "Live page";

  return (
    <>
      <ReportHeader
        scanId={scan}
        previousScanId={scanData?.previous_scan_id ?? null}
        title={displayTitle}
        meta={
          // The URL is the part worth a line: an issue's pages often share a
          // title ("Find a Room") and differ only in their query string. The
          // render is only mentioned when it is not the stored evidence at
          // its usual 200, which is what a reader assumes they are looking at.
          renderNote ? (
            <ReportMeta counts={renderNote} note={pageInfo.url} />
          ) : (
            <span
              className="break-all text-fg-subtle"
              title={
                pageInfo.captured_at
                  ? `Saved ${serverDate(pageInfo.captured_at).toLocaleString()}`
                  : undefined
              }
            >
              {pageInfo.url}
            </span>
          )
        }
        actions={
          <ExternalLinkButton
            href={liveUrl}
            variant="secondary"
            aria-label={`Open live page: ${displayTitle} (opens in a new tab)`}
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
                The scan did not save this page state
              </p>
              <p className="mt-1 text-sm text-fg">{render.error}</p>
              <p className="mt-2 text-2xs text-fg-muted">
                To see it yourself, open the live page and click the controls
                named in the Page state list above, in order. Or choose{" "}
                <span className="font-semibold">At page load</span> to see the
                page code this report saved.
              </p>
            </>
          ) : (
            <>
              <p className="text-sm font-semibold text-fg">This page could not be shown again</p>
              <p className="mt-1 text-sm text-fg">{render.error}</p>
              <p className="mt-2 text-2xs text-fg-muted">
                The evidence the scan saved for this page is still available. To
                see the page yourself, use{" "}
                <span className="font-semibold">Open live page</span>. Or go back
                to the page evidence.
              </p>
            </>
          )}
        </Card>
      )}

      {/* Which state, then which view of it. Two separate choices, so they
          are two separate controls rather than one row mixing both axes. A
          select, not the segmented row below: a busy page can reach a dozen
          states and chips would wrap into a block. */}
      {offeredStates.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Select
            id="inspect-state"
            label="Page state"
            aria-describedby={elsewhere.length > 0 ? ELSEWHERE_ID : undefined}
            value={stateKey ?? ""}
            onChange={(next) => navigate(stateHref(next || null), { replace: true })}
            options={[
              {
                value: "",
                label: `At page load${occurrencesHere(loadStateCount)}`,
                badge: issueOnlyAfterClicks ? (
                  <IssueNotHereChip />
                ) : (
                  <MissingChip count={missingFor("")} />
                ),
              },
              ...offeredStates.map((state) => {
                const count = occurrencesByState.get(state.state_key) ?? 0;
                // The whole chain, not just the last control: reaching a
                // nested state by hand means repeating every step. The count
                // says where this issue actually is, so the reviewer picks a
                // state instead of trying them.
                return {
                  value: state.state_key,
                  label: `After clicking ${clickChain(state)}${occurrencesHere(count)}`,
                  badge: <MissingChip count={missingFor(state.state_key)} />,
                };
              }),
            ]}
          />
          {/* The previous document stays on screen while the next one loads,
              so say which is which rather than letting the reviewer read the
              old state under the new label. Once loaded, nothing is said:
              "The scan saved this page state after clicking the control."
              only repeated the chosen option, which already reads "After
              clicking …". */}
          {isFetching && (
            <span className="inline-flex items-center gap-1.5 text-xs text-fg-muted" role="status">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              Loading this page state. The previous one stays on screen until it
              loads.
            </span>
          )}
        </div>
      )}

      {/* Where else this issue is, in one sentence, not a second control.

          The picker shows one page state at a time, so occurrences in the
          others were out of sight: nothing said a click had revealed more
          (eb39b33). That was first fixed with a box of pill links, one per
          page state holding occurrences. But while reviewing an issue the
          picker lists exactly those page states, with the same counts, so
          the pills were a second control for the same choice. Two ways to
          do one thing make a reader work out whether they differ (W3C COGA,
          "Making Content Usable", https://www.w3.org/TR/coga-usable/:
          keep the interface simple and consistent), and a pill per click
          path wraps into a large block on a busy page, where the select
          scales to dozens of states. So the select is the one control, and
          this sentence says what it holds. It is the select's description
          (aria-describedby), so a screen reader hears it on the control
          too. The term stays "page state": docs/plain-language.md lists
          "interaction state" as a word not to use. */}
      {elsewhere.length > 0 && (
        <p id={ELSEWHERE_ID} className="-mt-1 mb-3 flex items-start gap-2 text-sm text-fg">
          <Layers className="mt-0.5 h-4 w-4 shrink-0 text-umich-blue" aria-hidden />
          <span>{elsewhereSentence(elsewhereCount, elsewhere.length, Boolean(activeStateKey))}</span>
        </p>
      )}

      <Tabs
        mode="nav"
        label="How to view this page"
        className="mb-4"
        replace
        value={tab}
        items={[
          {
            key: "page",
            label: render.ok ? copyName : "Page",
            to: viewHref("page"),
          },
          // "Loaded DOM" was accurate while the only document was the page as
          // it loaded. It can now be a state captured after a click, so the
          // name says what it shows rather than when it was taken.
          { key: "dom", label: "Page code (DOM)", to: viewHref("dom") },
        ]}
      />

      <div
        id="inspect-panel-page"
        role="region"
        aria-label={render.ok ? copyName : "Page"}
        className="rounded-xs border border-border bg-surface shadow-card"
        hidden={tab !== "page"}
      >
        {render.ok && render.dom_html ? (
          <div>
            {/* Top corners as the panel's inner ones (8px less its 1px border),
                so the bar's fill does not paint square corners over them. */}
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-t-[7px] border-b border-border bg-surface-muted/40 px-3 py-2">
              <span className="text-xs font-semibold text-fg-subtle">
                {highlightPending
                  ? "Highlighting…"
                  : showHighlights && highlightedCount > 0
                    ? `${highlightedCount} place${highlightedCount === 1 ? "" : "s"} highlighted`
                    : copyName}
              </span>
              {!highlightPending && showHighlights && highlightedCount > 0 && (
                // Previous / Next through the outlined elements, the same
                // control as the Page code (DOM) tab's (FlaggedStepper).
                <FlaggedStepper
                  count={highlightedCount}
                  index={pageMark}
                  onGo={goToPageMark}
                  detail={
                    currentElement
                      ? `${currentElement.kind}${currentElement.text ? `, “${currentElement.text}”` : ""}`
                      : undefined
                  }
                  className="ml-auto"
                />
              )}
              {checkLayout && (
                // eslint-disable-next-line react/forbid-elements -- Convert: styled by hand like a secondary Button; use Button variant="secondary" size="sm"
                <button
                  type="button"
                  aria-pressed={!asChecked}
                  onClick={() => setAsChecked((value) => !value)}
                  className="inline-flex min-h-target items-center gap-1 rounded-xs border border-border-strong bg-surface px-3 text-xs font-semibold text-fg hover:bg-surface-muted"
                >
                  Show at full width
                </button>
              )}
              {hasTarget && (
                // eslint-disable-next-line react/forbid-elements -- Convert: styled by hand like a secondary Button; use Button variant="secondary" size="sm"
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
            {/* What the numbered box is on, as a short table with the same
                labels in the same places for every flagged element, so
                Previous / Next change only the values. The toolbar above
                already says which one you are on, so this does not repeat it. */}
            {showHighlights && highlightedCount > 0 && currentElement && (
              <div
                role="group"
                aria-label="The flagged element you are on"
                className="border-b border-border bg-surface px-3 py-2 text-sm text-fg"
              >
                <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 sm:gap-x-4">
                  <ElementFact term="What it is">{currentElement.kind}</ElementFact>
                  <ElementFact term="Text or label">
                    {currentElement.text ? (
                      `“${currentElement.text}”`
                    ) : (
                      <span className="text-fg-muted">None found</span>
                    )}
                  </ElementFact>
                  <ElementFact term="Size">
                    <span className="tabular-nums">
                      {pixels(currentElement.width)} wide, {pixels(currentElement.height)} tall
                    </span>
                    {/* The row below says where the box is when it is not on the element. */}
                    {currentElement.where === null &&
                      (currentElement.width === 0 || currentElement.height === 0) && (
                      <span className="block text-xs text-fg-muted">
                        It has no visible size in this saved copy, so the box marks where it sits.
                      </span>
                    )}
                  </ElementFact>
                  {currentElement.where && (
                    <ElementFact term="Where the box is">{BOX_NOTES[currentElement.where]}</ElementFact>
                  )}
                  {sharedCount > 1 && <ElementFact term="Occurrences">{sharedCount} on this element</ElementFact>}
                  {currentPlace ? (
                    <>
                      <ElementFact term="Where it is in the page code" stack>
                        Number {currentPlace.index + 1} of the {currentPlace.total}{" "}
                        <code translate="no" className="font-mono text-xs">
                          {currentPlace.selector}
                        </code>{" "}
                        {currentPlace.total === 1 ? "element" : "elements"}
                      </ElementFact>
                      {currentAddress && (
                        <ElementFact term="Image address">
                          <code translate="no" className="font-mono text-xs">
                            {currentAddress}
                          </code>
                        </ElementFact>
                      )}
                    </>
                  ) : (
                    shownLocator && (
                      <ElementFact term={locatorTerm} stack>
                        <LocatorValue
                          key={shownLocator}
                          id="inspect-locator"
                          value={shownLocator}
                          open={locatorOpen}
                          onOpenChange={setLocatorOpen}
                        />
                      </ElementFact>
                    )
                  )}
                </dl>
                {/* The way to the element itself for a screen reader or a
                    keyboard. The box in the copy is drawn for the eye, so
                    without this a screen reader user had to search the
                    whole copy for an element nothing marked. It moves focus
                    onto the element, where a screen reader reads it in its
                    place on the page, with "Flagged element 2 of 5" as its
                    description (noteCurrent), and Escape comes back here.
                    A separate button, not part of Next: moving focus into
                    the copy at every step would take the reader away from
                    Next each time. After the facts, so it is reached once
                    the reader knows what the element is. SC 2.1.1 Keyboard,
                    Level A; SC 2.4.3 Focus Order, Level A; SC 1.3.1 Info
                    and Relationships, Level A (the flag was only visual).
                    The hint is its description; the note, a status, says in
                    words when focus could not move. */}
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <Button
                    ref={goToRef}
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="min-h-target"
                    aria-describedby="inspect-go-to-hint"
                    onClick={goToElement}
                  >
                    Go to this element in the {copyName.toLowerCase()}
                  </Button>
                  <span id="inspect-go-to-hint" className="text-xs text-fg-muted">
                    Moves keyboard focus onto it. Press Escape to come back here.
                  </span>
                  <span role="status" className="basis-full text-xs text-fg empty:sr-only">
                    {goToNote && <span key={goToNote.attempt}>{goToNote.text}</span>}
                  </span>
                </div>
              </div>
            )}
            {/* Says when the saved copy may not look like the page Axcess
                checked: the scan could not save all of the page's styles, or
                its rendering here fails the style check (fewer than 70% of
                the sampled elements match the fonts and colours recorded
                during the scan, see ``lib/styleFingerprint``). Without it a
                copy that lost its styles looks like evidence of a broken
                page. It names the way to check, the Open live page button.
                Above the frame, so it is read before the page, and in words,
                not a colour or icon alone (SC 1.4.1 Use of Color, Level A).
                The check finishes after the frame loads, so the note is a
                polite live region that is always in the page and empty until
                there is something to say, as the stepper's status is (SC
                4.1.3 Status Messages, Level AA). An incomplete save is said
                whatever the check finds: it is a limitation of the evidence,
                and the plain-language rules say never to drop one. Rejected:
                a dismissible banner, which would hide that limitation. */}
            <div role="status" className="empty:sr-only">
              {savedStyles && (!savedStyles.complete || stylesDiffer) && (
                <p className="border-b border-sev-major/40 bg-sev-major-bg px-3 py-2 text-sm text-fg">
                  This saved copy may look different from the page Axcess checked.{" "}
                  {savedStyles.complete
                    ? "Some of its styles may not have loaded."
                    : "Axcess could not save all of this page's styles."}{" "}
                  Use <span className="font-semibold">Open live page</span> to compare.
                </p>
              )}
            </div>
            {layout && (
              <p className="border-b border-border bg-umich-blue/5 px-3 py-2 text-xs text-fg">
                <span className="font-semibold">As the zoom and layout check saw it: </span>
                {layout.label}
              </p>
            )}
            {/* The check's window, centred on a grey stage, so its width is
                the page's width, as it was when the issue was found. */}
            <div className={cn(layout?.width && "flex justify-center overflow-auto bg-surface-muted p-4")}>
              {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
              <iframe
                ref={frameRef}
                srcDoc={srcDoc}
                onLoad={onFrameLoad}
                title={`${copyName}: ${displayTitle}`}
                sandbox="allow-same-origin"
                referrerPolicy="no-referrer"
                className={cn(
                  "border-0 bg-white",
                  layout?.width ? "shrink-0 shadow-card ring-1 ring-border" : "h-[75vh] w-full",
                )}
                style={layout?.width ? { width: layout.width, height: layout.height ?? undefined } : undefined}
              />
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border px-3 py-2 text-xs text-fg-muted" aria-live="polite">
              {highlightPending && (
                <span>Highlighting the flagged element…</span>
              )}
              {!highlightPending && showHighlights && highlightedCount > 0 && (
                <span>
                  {highlightedCount > 1
                    ? `Dashed red outlines mark the ${highlightedCount} flagged elements on this page. The one you are on has a numbered blue box with a yellow ring, and the rest of the page is dimmed.`
                    : // Never describe a box that is not drawn (see ``drawsNoBox``).
                      drawsNoBox(currentElement?.where ?? null)
                      ? "No box marks the flagged element. The table above the saved copy says why."
                      : "A blue box with a yellow ring marks the flagged element."}
                </span>
              )}
              {!highlightPending &&
                showHighlights &&
                highlight !== null &&
                highlightedCount > 0 &&
                highlight.located + highlight.ambiguous + unreachableCount < highlight.total && (
                  <span className="text-sev-major">
                    Axcess found {highlight.located} of {highlight.total} flagged
                    occurrences.{" "}
                    {missingReason?.whenSomeFound ??
                      "The others may have changed since the scan."}
                  </span>
                )}
              {!highlightPending && showHighlights && highlight !== null && highlight.ambiguous > 0 && (
                // Never a guess: the same markup in several places, with no
                // locator to tell them apart, is said, not outlined.
                <span className="text-sev-major">
                  {highlight.ambiguous === 1
                    ? "1 occurrence is not outlined: its markup appears in more than one place in this saved copy, and Axcess does not guess which."
                    : `${highlight.ambiguous} occurrences are not outlined: their markup appears in more than one place in this saved copy, and Axcess does not guess which.`}
                </span>
              )}
              {!highlightPending && showHighlights && highlight !== null && unreachableCount > 0 && (
                // Never a guess: an element inside shadow DOM or a frame is
                // in no saved copy, and one that looks the same elsewhere is
                // not it (see ``unreachableLocator``). Said, with the reason.
                <span className="text-sev-major">
                  {unreachableSentence(highlight.unreachable.shadow, "shadow")}
                  {highlight.unreachable.shadow > 0 && highlight.unreachable.frame > 0 && " "}
                  {unreachableSentence(highlight.unreachable.frame, "frame")}
                </span>
              )}
              {!highlightPending &&
                showHighlights &&
                hasScopedTarget &&
                highlightedCount === 0 &&
                unreachableCount < (highlight?.total ?? 0) && (
                // Only drops the error styling when interaction accounts for
                // every miss. Then "not found" is the expected result and
                // flagging it warns about a fact of how the scan works; with a
                // mix, something genuinely should have been matched.
                <span className={missingReason?.certain ? undefined : "text-sev-major"}>
                  {missingReason?.whenNoneFound ??
                    "Axcess could not find the flagged element in this copy. The page may have changed since the scan."}
                </span>
              )}
              {canvasPage && (
                <span>
                  This page draws on a drawing area (canvas). The saved copy runs no scripts, so it does not show the
                  drawing, only any backup content the page gave. Nothing drawn on it can be outlined.
                </span>
              )}
              {activeStateKey === null && hiddenImageCount > 0 && (
                <span>
                  {hiddenImageCount === 1
                    ? "1 more occurrence is in page code that browsers do not show when scripts run (a <noscript> or <template> element), usually a backup copy of an image. It is not outlined."
                    : `${hiddenImageCount} more occurrences are in page code that browsers do not show when scripts run (a <noscript> or <template> element), usually backup copies of images. They are not outlined.`}
                </span>
              )}
              {offStateCount > 0 && (
                // Without this the issue looks smaller in a state view than it
                // is: the picker is the only way to the rest of it.
                <span>
                  {offStateCount} more {offStateCount === 1 ? "occurrence" : "occurrences"} of
                  this issue {offStateCount === 1 ? "is" : "are"} in another page
                  state. Choose it in the Page state list.
                </span>
              )}
              {!showHighlights && hasScopedTarget && (
                <span>Highlights are hidden for this page.</span>
              )}
              {!hasTarget && (
                <span>
                  {render.source === "stored"
                    ? "This is the copy the scan saved. This issue has no element to mark."
                    : "Axcess loaded this page just now. This issue has no element to mark."}
                </span>
              )}
              {!data.store_rendered_html && (
                <span>
                  This scan did not save copies of pages, so Axcess loads the
                  live page each time you open it.
                </span>
              )}
            </div>
            {/* Outside the live region above: this is standing context about
                the capture, not a status that changes, so it should not be
                re-announced every time the highlight count updates. It says
                where the styles come from, because that differs: a copy with
                saved styles uses them, an older copy loads the site's. The
                band spans the panel and the text inside it stops at a
                readable width (max-w-measure, SC 1.4.8 Visual Presentation,
                Level AAA): capping the band itself cut its top border short. */}
            <div className="border-t border-border px-3 py-2 text-2xs text-fg-muted">
              <p className="max-w-measure">
                {savedStyles
                  ? "The page code shown here is a copy. Its styles are the ones the scan saved. Its fonts and images load from the live site now, so they can look different from how they looked during the scan."
                  : "The page code shown here is a copy. Its styles, fonts, and images load from the live site now, so the page can look different from how it looked during the scan."}{" "}
                The page&rsquo;s own scripts never run here. So if the site would
                only show a flagged element with JavaScript, Axcess makes it
                visible to highlight it.
              </p>
            </div>
            {/* Below the page and closed: above it, the list pushed the page
                the reviewer came to see out of view. */}
            {evidenceCount > 0 && (
              <Disclosure
                id="inspect-evidence"
                title="Evidence from the scan"
                meta={`${evidenceCount} occurrence${evidenceCount === 1 ? "" : "s"}`}
                className="rounded-none border-0 border-t"
              >
                <ul className="space-y-2">
                  {scopedFindings.slice(0, 3).map((f) => (
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
                        <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap break-all rounded-2xs border border-border bg-surface px-2 py-1 text-2xs leading-relaxed text-fg-muted">
                          {f.html_snippet}
                        </pre>
                      )}
                    </li>
                  ))}
                  {scopedImages.slice(0, Math.max(0, 3 - scopedFindings.length)).map((image) => (
                    <li key={`image-${image.occurrence_id}`} className="text-xs">
                      <p className="font-semibold text-fg">
                        Image with text
                        {image.hidden_in_copy && (
                          <span className="ml-1 font-normal text-fg-muted">(a backup copy not shown here)</span>
                        )}
                      </p>
                      <p className="mt-0.5 text-fg-muted">{altTextLine(image.alt_text)}</p>
                      {image.ocr_text && (
                        <p className="mt-0.5 text-fg-muted">
                          Text in the image: “{shorten(normalizeWhitespace(image.ocr_text), 160)}”
                        </p>
                      )}
                      {image.locator?.kind !== "svg" && !image.src_url_canonical.startsWith("inline-svg:") && (
                        <code className="mt-0.5 block overflow-x-auto whitespace-nowrap rounded-2xs border border-border bg-surface px-2 py-1 text-2xs text-fg">
                          {image.locator?.candidate ?? image.src_url_canonical}
                        </code>
                      )}
                    </li>
                  ))}
                </ul>
                {evidenceCount > 3 && (
                  <p className="mt-1 text-2xs text-fg-muted">
                    + {evidenceCount - 3} more occurrence{evidenceCount - 3 === 1 ? "" : "s"} in this page state.
                  </p>
                )}
              </Disclosure>
            )}
          </div>
        ) : (
          <div className="p-6 text-sm text-fg-muted">
            {render.error || "This page could not be shown."}
          </div>
        )}
      </div>

      <div
        id="inspect-panel-dom"
        role="region"
        aria-label="Page code (DOM)"
        className="rounded-xs border border-border bg-surface shadow-card"
        hidden={tab !== "dom"}
      >
        {render.ok && render.dom_html ? (
          <div className="p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <p className="flex items-center gap-1.5 text-2xs font-semibold text-fg-subtle">
                <FileCode2 className="h-4 w-4" aria-hidden />
                Page code (DOM), as the browser built it
              </p>
              <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
                {hasScopedTarget && (
                  <span className="text-2xs text-fg-muted">
                    {domMarkCount > 0
                      ? `${domMarkCount} flagged ${domMarkCount === 1 ? "element is" : "elements are"} marked in the code below.`
                      : (missingReason?.whenNoneFound ??
                        "Axcess could not find the flagged element in this page code.")}
                  </span>
                )}
                {render.dom_truncated && (
                  <span className="text-2xs text-sev-major">
                    Cut short: only the first 2,000,000 characters are shown.
                  </span>
                )}
              </span>
            </div>
            {/* Scanned page markup is untrusted and rendered as text, never
                executed: DomSource re-walks DOMParser's inert document and
                prints one node per line, with each flagged element marked
                as a block, matching the page view. */}
            {tab === "dom" && (
              <DomSource html={render.dom_html} locate={locateFlagged} onMarked={setDomMarkCount} />
            )}
          </div>
        ) : (
          <div className="p-6 text-sm text-fg-muted">
            {render.dom_html
              ? "No page code was saved."
              : render.error || "This page could not be shown."}
          </div>
        )}
      </div>
    </>
  );
}

/**
 * The saved CSS for the document an inspection returned, or null.
 *
 * Only for a saved copy: the page as it loaded uses the page's own saved CSS,
 * a page state uses that state's. A live render is the site now, so its CSS
 * is the site's own. Older servers send no field at all, which reads as null.
 */
function savedStylesFor(inspection: PageInspection): SavedStyles | null {
  const { render } = inspection;
  if (!render.ok) return null;
  if (render.source === "stored") return inspection.saved_styles ?? null;
  if (render.source === "state") {
    return inspection.states.find((state) => state.state_key === render.state_key)?.saved_styles ?? null;
  }
  return null;
}

/**
 * Make a stored capture renderable in the inspector's frame.
 *
 * A capture is correct markup that renders wrongly the moment it leaves the
 * site it came from. What this does depends on whether the scan saved the
 * copy's CSS (`savedStylesUrl`).
 *
 * With saved CSS (new reports):
 *
 * 1. The copy's own `<link rel="stylesheet">` and `<style>` elements are
 *    removed and one `<link>` to the saved CSS goes at the end of `<head>`.
 *    The saved file holds all of their rules, in the same order, including
 *    rules the page's scripts added, which the markup never had. It comes
 *    from this app's own origin, so none of the problems below can stop it:
 *    the site's policy (`'self'` here is this app), `crossorigin`,
 *    `integrity`, CSS behind a sign-in, or CSS the site has since deleted.
 *    The link is absolute, because the `<base>` below points at the site.
 *    Rejected: keeping the site's stylesheets as well, which would load the
 *    site's current CSS over the saved one.
 *
 * Without saved CSS (reports made before it, or a copy whose CSS the scan
 * could not save), the copy loads the site's stylesheets live, and two edits
 * keep that working:
 *
 * 2. `crossorigin` on a stylesheet link was free on the site, where the sheet
 *    was same-origin. Here the frame's origin is the review UI, so the same
 *    attribute puts the request in CORS mode and the server -- serving what it
 *    believes is a same-origin asset -- sends no `Access-Control-Allow-Origin`.
 *    The stylesheet is refused and a fully styled application renders as
 *    unstyled serif text. Dropping the attribute makes it an ordinary no-CORS
 *    stylesheet load, which is what it effectively was. `integrity` goes with
 *    it: the browser can only check subresource integrity on a CORS request,
 *    so a link that keeps `integrity` without `crossorigin` is refused
 *    outright (CDN Font Awesome and Bootstrap links carry both).
 *
 * On both paths:
 *
 * 3. Relative subresources resolve against the review UI, so `<base href>` is
 *    injected (see `withBaseHref`). Fonts and images still come from the
 *    live site, with saved CSS too: its `url()` values were made absolute.
 * 4. A `<meta http-equiv="Content-Security-Policy">` was written for the
 *    site's own address. In this frame `'self'` means the review UI, so a
 *    policy such as `style-src 'self' https://cdn...` refuses the site's own
 *    stylesheets, and with saved CSS it would refuse the site's fonts and
 *    images. The frame's real limits are its `sandbox` (no scripts) and the
 *    app's own policy, which a `srcdoc` document inherits; the site's policy
 *    adds nothing but the refusal.
 * 5. `<noscript>` content becomes visible because the frame runs with scripts
 *    disabled, so a single-page app announces "You need to enable JavaScript
 *    to run this app" over markup that was captured with JavaScript running.
 *    It is the alternative to a state this document is not in.
 *
 * The DOM-source view deliberately does not go through this: that tab shows
 * the evidence as stored, and these edits exist only to render it.
 */
function prepareCapture(html: string | null, url: string | null, savedStylesUrl: string | null = null): string | null {
  if (!html) return html;
  let rendered = html
    .replace(/<meta\b[^>]*http-equiv\s*=\s*["']?content-security-policy[^>]*>/gi, "")
    .replace(/<noscript\b[^>]*>[\s\S]*?<\/noscript>/gi, "");
  if (savedStylesUrl) {
    rendered = withSavedStyles(
      rendered
        .replace(/<link\b[^>]*>/gi, (tag) => (isStylesheetLink(tag) ? "" : tag))
        .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ""),
      api.savedStylesUrl(savedStylesUrl),
    );
  } else {
    rendered = rendered.replace(/<link\b[^>]*>/gi, (tag) =>
      tag.replace(/\s+(crossorigin|integrity)(=("[^"]*"|'[^']*'|[^\s>]*))?/gi, ""),
    );
  }
  return withBaseHref(rendered, url);
}

/** Whether a `<link>` tag loads a stylesheet (`rel` lists `stylesheet`). */
function isStylesheetLink(tag: string): boolean {
  const rel = /\brel\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))/i.exec(tag);
  const value = rel ? (rel[2] ?? rel[3] ?? rel[4] ?? "") : "";
  return value.toLowerCase().split(/\s+/).includes("stylesheet");
}

/** Put a link to the saved CSS last in `<head>`, where the page's own CSS ended. */
function withSavedStyles(html: string, href: string): string {
  const tag = `<link rel="stylesheet" href="${escapeAttribute(href)}" data-axcess-saved-styles>`;
  const close = html.search(/<\/head>/i);
  if (close !== -1) return html.slice(0, close) + tag + html.slice(close);
  const body = html.search(/<body\b/i);
  if (body !== -1) return html.slice(0, body) + tag + html.slice(body);
  return tag + html;
}

/**
 * Give the captured markup the page's own URL as its base.
 *
 * A `srcDoc` frame has no document URL, so a capture's relative and
 * root-relative subresources (`href="/site.css"`, `src="logo.png"`) would be
 * requested from the review UI's origin and 404 — the page renders with no CSS
 * at all. A `<base href>` restores the original resolution, so the frame loads
 * the site's real stylesheets, fonts and images.
 *
 * When the capture has its own `<base href>`, that one decides how the page's
 * relative URLs resolve, exactly as on the site, so it is resolved against the
 * page's address and the absolute result goes first (the first `<base>` in a
 * document wins). Left as it was, a relative one such as Angular's
 * `<base href="/">` would resolve against the frame's `about:srcdoc` and load
 * nothing. Left untouched when the URL is not an http(s) address we should
 * point a browser at.
 */
function withBaseHref(html: string | null, url: string | null): string | null {
  if (!html || !url) return html;
  const own = /<base\b[^>]*\bhref\s*=\s*["']?([^"'\s>]+)/i.exec(html)?.[1]?.replace(/&amp;/g, "&");
  let href: string;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return html;
    href = new URL(own ?? url, parsed).href;
  } catch {
    return html;
  }
  const tag = `<base href="${escapeAttribute(href)}">`;
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
 * Scroll the inspector page so ``target``, inside the saved copy's frame, is
 * in view below the sticky top bar, after "Go to this element" put focus on
 * it. Focus moves without scrolling (``focusInCopy``) and ``keepCentered``
 * scrolls only the frame, which is right while stepping, where the page must
 * not jump. But this button is above the frame, so on a short window (or
 * with a tall facts table) focus landed on an element below the bottom of
 * the screen, and a keyboard user could not see where it went (SC 2.4.11
 * Focus Not Obscured (Minimum), Level AA; found by review). The page moves
 * only when the element is not fully shown already, and then centres it in
 * the room under the bar (the page's scroll-padding-top, styles.css).
 */
function revealInPage(frame: HTMLIFrameElement, target: HTMLElement): void {
  const outer = frame.getBoundingClientRect();
  const inner = boxPlace(target).rect;
  // The part of the element the frame shows, in the page's view.
  const top = outer.top + frame.clientTop + Math.max(0, inner.top);
  const bottom = outer.top + frame.clientTop + Math.min(frame.clientHeight, Math.max(inner.bottom, inner.top + 1));
  const reserved = parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 0;
  if (top >= reserved && bottom <= window.innerHeight) return;
  const middle = (top + bottom) / 2;
  window.scrollBy({ top: middle - (reserved + (window.innerHeight - reserved) / 2), behavior: "instant" });
}

/**
 * Center ``target`` in its frame and hold it there while the layout settles.
 *
 * A single `scrollIntoView` is not enough: the capture's fonts and images (and,
 * for a copy without saved styles, stylesheets) are fetched from the live site
 * and can arrive *after* the frame fires `load`, and every one of them reflows
 * the document, so an element centered at load time
 * drifts far off-screen a moment later. This re-centers until the element's
 * position in the document stops moving (two consecutive quiet checks), with a
 * hard ceiling so a page that never stops animating cannot spin forever.
 * An element taller or wider than the view is scrolled to its start instead
 * (see ``toCentre``).
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
      // Where the box goes: an element with no box of its own (an option,
      // an image map area) is centred by what stands for it.
      const placed = boxPlace(target);
      // The whole page is everywhere, and an element that is not displayed or
      // is off the screen is nowhere to scroll to: moving the view would only
      // lose the reader's place, so it stays where it is.
      if (
        placed.note === "whole-page" ||
        placed.note === "hidden" ||
        placed.note === "off-screen" ||
        placed.note === "focus-unread"
      )
        return;
      const top = placed.rect.top + win.scrollY;
      quiet = previous !== null && Math.abs(top - previous) < 2 ? quiet + 1 : 0;
      previous = top;
      // Scroll the *frame* only. `scrollIntoView` also scrolls every ancestor
      // scroll container, including the page that holds the iframe, so each
      // re-centre yanked the reader down the inspector page; where the page
      // itself starts is the app shell's decision (the top), not the frame's.
      // An app-style page scrolls a panel of its own (a sidebar) rather than
      // the window, so each panel around the element, innermost first, is
      // centred on it before the frame is.
      for (const panel of scrollPanels(placed.on)) {
        const outer = panel.getBoundingClientRect();
        const inner = boxPlace(target).rect;
        const fromTop = inner.top - outer.top - panel.clientTop;
        const fromLeft = inner.left - outer.left - panel.clientLeft;
        panel.scrollTo({
          top: panel.scrollTop + toCentre(fromTop, inner.height, panel.clientHeight, "top"),
          left: panel.scrollLeft + toCentre(fromLeft, inner.width, panel.clientWidth, "left"),
          behavior: "instant",
        });
      }
      const rect = boxPlace(target).rect;
      win.scrollTo({
        top: win.scrollY + toCentre(rect.top, rect.height, win.innerHeight, "top"),
        left: win.scrollX + toCentre(rect.left, rect.width, win.innerWidth, "left"),
        behavior: "instant",
      });
      ticks += 1;
      if (quiet < 2 && ticks < 20) window.setTimeout(step, 300);
    } catch {
      // The frame navigated or unmounted mid-settle; nothing left to center.
    }
  };
  step();
}

/**
 * How far to scroll a view so an element starting ``start`` pixels into it,
 * ``size`` pixels long, is centred; or, when it is longer than the view,
 * so it starts a little way in.
 *
 * Centring a flagged ``<main>`` or long form that is taller than the view put
 * its middle on screen and scrolled away its top, where it starts, and the
 * box's numbered label above it: the reader saw an unmarked stretch of page.
 * Rejected: centring on the element's top, which would waste half the view
 * above it. The margin leaves room for the label above the box (the label is
 * about 30 pixels tall, see ``spotlight``); sideways, only for the box's
 * ring. No WCAG criterion covers where a tool scrolls; the nearest is SC
 * 2.4.11 Focus Not Obscured (Minimum), Level AA, which asks (paraphrased)
 * that the item a reader is on is not hidden from them.
 */
function toCentre(start: number, size: number, view: number, axis: "top" | "left"): number {
  const margin = axis === "top" ? 48 : 16;
  return size > view ? start - margin : start - (view - size) / 2;
}

/** A state's flagged elements that its capture does not hold, of how many. */
type MissingCount = { missing: number; total: number };

/**
 * The picker's red "No longer here" chip, for a state whose capture does not
 * hold the element it was flagged on. Plain words, since the chip is read as
 * part of the option's name.
 *
 * The chip style is uppercase, and Chromium carries CSS text-transform into
 * the accessibility tree, where some screen readers spell short capitalized
 * words letter by letter. So the visible text is hidden from them and they
 * get the same words in sentence case, with a comma so it does not run into
 * the state's name.
 */
function MissingChip({ count }: { count: MissingCount | undefined }) {
  if (!count || count.missing <= 0) return null;
  const text =
    count.missing === count.total
      ? "No longer here"
      : `${count.missing} of ${count.total} no longer here`;
  return (
    <span className="sev-chip sev-chip--critical shrink-0">
      <span aria-hidden>{text}</span>
      <span className="sr-only">{text}, </span>
    </span>
  );
}

/**
 * The picker's neutral "Issue not here" chip, for the page as it loaded when
 * every occurrence under review came after a click. The option stays, as the
 * baseline the other states are read against, but the issue is not in it.
 *
 * Literal words, not "For reference": that says the option is secondary but
 * not why, and plain-language guidance asks for the fact itself. Neutral,
 * not red, so it does not read as the "No longer here" problem: nothing is
 * wrong with this capture. Screen readers get sentence case, as with
 * ``MissingChip``.
 */
/** The sentence under the Page state picker, and the picker's description. */
const ELSEWHERE_ID = "inspect-state-elsewhere";

/**
 * "3 more occurrences are in 2 other page states. Choose one in the Page
 * state list." From page load, the others all come after a click, so it
 * says so. Counts and states are both given: a state can hold several.
 */
function elsewhereSentence(occurrences: number, states: number, inClickedState: boolean): string {
  const many = occurrences === 1 ? "1 more occurrence" : `${occurrences.toLocaleString()} more occurrences`;
  const where = states === 1 ? "1 page state" : `${states} page states`;
  const choose = states === 1 ? "Choose it in the Page state list." : "Choose one in the Page state list.";
  if (inClickedState) {
    const others = states === 1 ? "another page state" : `${states} other page states`;
    return `${many} ${occurrences === 1 ? "is" : "are"} in ${others}. ${choose}`;
  }
  return `${many} ${occurrences === 1 ? "appears" : "appear"} only after clicking a control, in ${where}. ${choose}`;
}

function IssueNotHereChip() {
  return (
    <span className="sev-chip shrink-0 bg-surface-muted text-fg-muted">
      <span aria-hidden>Issue not here</span>
      <span className="sr-only">Issue not here, </span>
    </span>
  );
}

/**
 * Where the numbered box is, in words, when it is not simply around the
 * flagged element (see ``boxPlace``). A row of its own in the table, after
 * Size, and only when it applies, so every other element's table keeps the
 * same labels in the same places. Said in words because the box's position
 * alone cannot tell the reader that an option was marked on its list box:
 * WCAG 2.2 SC 1.3.3 Sensory Characteristics (Level A). The technical name is
 * in parentheses for developers (docs/plain-language.md, rule 6).
 */
const BOX_NOTES: Record<BoxNote, string> = {
  contents: "Around what it holds. It has no box of its own (display: contents).",
  "list-box": "On its list box. An option has no box of its own.",
  "image-map": "On the part of its image it covers. An area of an image map (<area>) has no box of its own.",
  "whole-page": "No box, because it is the whole page. Nothing is dimmed.",
  "focus-only": "It shows only when it has keyboard focus. The box is where it shows then.",
  "off-screen": "No box. It is off the screen in this saved copy.",
  "focus-unread":
    "No box. It is off the screen in this saved copy. Pages often place a link there and show it only when it has keyboard focus.",
  "part-clipped": "Around the part that shows. The part of the page around it hides the rest (overflow: hidden).",
  clipped: "No box. The part of the page around it hides it (overflow: hidden).",
  opened: "Around it. Axcess opened the closed section it is in (<details>) in this saved copy.",
  hidden: "No box. It was hidden in this saved copy (display: none).",
  canvas:
    "Around a drawing area (canvas). The saved copy runs no scripts, so it shows the area's backup content, not the drawing.",
};

/**
 * Why some occurrences are not outlined: where they are, and that the saved
 * copy does not keep that part. Empty for none.
 */
function unreachableSentence(count: number, where: Unreachable): string {
  if (count === 0) return "";
  const lead =
    count === 1 ? "1 occurrence is not outlined: it is" : `${count} occurrences are not outlined: they are`;
  return where === "shadow"
    ? `${lead} inside a part of the page that keeps its own page code (shadow DOM). The saved copy does not keep that code.`
    : `${lead} inside another page shown within this one (an iframe). The saved copy does not keep that page.`;
}

/** "1 pixel", "924 pixels". */
function pixels(n: number): string {
  return `${n} ${n === 1 ? "pixel" : "pixels"}`;
}

/**
 * One labelled fact about the flagged element: the label, then its value,
 * lined up with the rows above and below. A long label (`stack`) sits above
 * its value until the screen is wide, so the value keeps its room on a
 * narrow screen.
 */
function ElementFact({ term, stack = false, children }: { term: string; stack?: boolean; children: ReactNode }) {
  return (
    <div
      className={cn(
        "col-span-2",
        stack ? "lg:grid lg:grid-cols-subgrid lg:items-baseline" : "grid grid-cols-subgrid items-baseline",
      )}
    >
      <dt className="text-xs font-semibold text-fg-muted">{term}</dt>
      <dd className="min-w-0 [overflow-wrap:anywhere]">{children}</dd>
    </div>
  );
}

/**
 * An element locator on one line, cut at its start, so its end, the part
 * that names the element, stays in view. "Show all" puts each step on its
 * own line. "Copy element locator" copies all of it either way. The cut is
 * visual only: the text in the page is the whole locator, character for
 * character, and a screen reader reads all of it. The copy button's words
 * never change; the result is given in words in a status beside it.
 */
function LocatorValue({
  id,
  value,
  open,
  onOpenChange,
}: {
  id: string;
  value: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const codeRef = useRef<HTMLElement>(null);
  const probeRef = useRef<HTMLSpanElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const copyRef = useRef<HTMLButtonElement>(null);
  const [cut, setCut] = useState(false);
  // Whether the locator is wider than its box, measured on a hidden copy of
  // it on one line (the probe), so the answer holds while it is shown in
  // full too. The box's width never depends on the answer: the toggle keeps
  // its place when it is not needed, only hidden. (It used to appear only
  // when needed, which could narrow the box, change the answer and remove
  // it again, every frame.) A font that arrives late resizes the probe,
  // which measures again.
  useLayoutEffect(() => {
    const code = codeRef.current;
    const probe = probeRef.current;
    if (!code || !probe) return;
    const measure = () => {
      const isCut = probe.getBoundingClientRect().width > code.clientWidth + 0.5;
      // The toggle is about to hide: move its focus on rather than lose it.
      if (!isCut && !open && document.activeElement === toggleRef.current) copyRef.current?.focus();
      setCut(isCut);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(code);
    observer.observe(probe);
    return () => observer.disconnect();
  }, [open]);

  // Each copy gets a new key, so the status is new content every time and a
  // second "Copied" is announced like the first.
  const attempts = useRef(0);
  const [copied, setCopied] = useState<{ attempt: number; ok: boolean } | null>(null);
  const copy = async () => {
    attempts.current += 1;
    const attempt = attempts.current;
    try {
      await navigator.clipboard.writeText(value);
      setCopied({ attempt, ok: true });
    } catch {
      // No clipboard, for example plain http on a network address. Show the
      // whole locator and select it, so Ctrl+C or Command+C copies it.
      setCopied({ attempt, ok: false });
      if (open) selectLocator();
      else {
        selectWhenOpen.current = true;
        onOpenChange(true);
      }
    }
  };
  const selectLocator = () => {
    const code = codeRef.current;
    if (code) window.getSelection()?.selectAllChildren(code);
  };
  // Selected once the whole locator is on screen, not on a guess at when that is.
  const selectWhenOpen = useRef(false);
  useLayoutEffect(() => {
    if (!open || !selectWhenOpen.current) return;
    selectWhenOpen.current = false;
    selectLocator();
  });

  // Split before each " > ", so the steps join back into the exact locator.
  // The split is for display only: textContent, copy and tests stay exact.
  const steps = value.split(/(?= > )/);
  const last = steps.length - 1;
  const stepSpans = (block: boolean) =>
    steps.map((step, index) => (
      <span
        key={index}
        className={cn(block && "block pl-4 -indent-4", index === last && steps.length > 1 && "font-semibold")}
      >
        {step}
      </span>
    ));
  const needed = cut || open;
  return (
    <div className="relative flex flex-wrap items-baseline gap-x-2 gap-y-1">
      {/* Out of the flow and clipped to nothing, so it never widens the page. */}
      <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-0 overflow-hidden">
        <span ref={probeRef} className="invisible inline-block whitespace-nowrap font-mono text-xs">
          {stepSpans(false)}
        </span>
      </span>
      <code
        id={id}
        ref={codeRef}
        translate="no"
        className={cn(
          "min-w-0 flex-[1_1_12rem] font-mono text-xs text-fg",
          !open && "overflow-hidden text-ellipsis whitespace-nowrap text-left [direction:rtl]",
        )}
      >
        <span dir="ltr" className={open ? "block" : undefined}>
          {stepSpans(open)}
        </span>
      </code>
      <span className="ml-auto flex flex-wrap items-center justify-end gap-1">
        <Button
          ref={toggleRef}
          type="button"
          variant="ghost"
          size="sm"
          className={cn("min-h-target", !needed && "invisible")}
          aria-expanded={open}
          aria-controls={id}
          onClick={() => {
            // Closing a locator that fits hides this button: focus Copy first.
            if (open && !cut) copyRef.current?.focus();
            onOpenChange(!open);
          }}
        >
          {open ? <ChevronUp className="h-3.5 w-3.5" aria-hidden /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden />}
          {open ? "Show less" : "Show all"}
        </Button>
        <Button ref={copyRef} type="button" size="sm" className="min-h-target" onClick={copy}>
          <Copy className="h-3.5 w-3.5" aria-hidden />
          Copy element locator
        </Button>
      </span>
      <span role="status" className="basis-full text-xs text-fg empty:sr-only">
        {copied &&
          (copied.ok ? (
            <span key={copied.attempt} className="inline-flex items-center gap-1">
              <Check className="h-3.5 w-3.5" aria-hidden />
              Copied
            </span>
          ) : (
            <span key={copied.attempt}>
              Not copied. Your browser did not allow it. The element locator is now shown in full and selected.
              Press Ctrl+C, or Command+C on a Mac, to copy it.
            </span>
          ))}
      </span>
    </div>
  );
}

/**
 * How many of this issue's occurrences a page state holds, in words:
 * ": 19 occurrences". A bare "(19)" left the reader to guess what was
 * counted. Nothing is added when the page state holds none.
 */
/**
 * The controls clicked to reach a page state, in order: "“Menu” → “Help”".
 * The whole chain, not just the last control, since reaching a nested state
 * by hand means repeating every step. A control's name is its text, which
 * for a card can run on ("Fellowships · FundedTeach For Nepal…"), so each
 * name is cut at a word near 40 characters.
 */
function clickChain(state: { path_labels: string[]; revealed_by: string }): string {
  const names = state.path_labels.length > 0 ? state.path_labels : [state.revealed_by];
  return names.map((name) => `“${shortName(name)}”`).join(" → ");
}

function shortName(name: string, max = 40): string {
  const text = name.replace(/\s+/g, " ").trim();
  if (text.length <= max) return text;
  const cut = text.slice(0, max);
  const space = cut.lastIndexOf(" ");
  return `${(space > max / 2 ? cut.slice(0, space) : cut).replace(/[\s·,.;:–-]+$/, "")}…`;
}

function occurrencesHere(count: number): string {
  if (count === 0) return "";
  return `: ${count.toLocaleString()} occurrence${count === 1 ? "" : "s"}`;
}

/**
 * How the zoom and layout check saw the page when it found an issue, from
 * the issue's rule, so the inspector can show it the same way. The window
 * sizes and the spacing stylesheet mirror audit/analyzer/responsive/probe.py
 * (``_REFLOW_VIEWPORT``, ``_ZOOM_VIEWPORT``, ``_TEXT_SPACING_CSS``).
 */
type CheckLayout = { width: number | null; height: number | null; css: string | null; label: string };

const TEXT_SPACING_CSS = `
* {
  line-height: 1.5 !important;
  letter-spacing: 0.12em !important;
  word-spacing: 0.16em !important;
}
p {
  margin-bottom: 2em !important;
}
`;

/** What an image's alt text is, in words: whether it is missing, empty, or says something. */
function altTextLine(alt: string | null): string {
  if (alt === null) return "No alt text (the text a screen reader reads for an image): the image has no alt attribute.";
  if (!alt.trim()) return "Empty alt text: the image is marked as decorative, so screen readers skip it.";
  return `Alt text (what a screen reader reads): “${shorten(normalizeWhitespace(alt), 160)}”`;
}

function shorten(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}

/**
 * Whether a finding is an occurrence of the issue ``key`` names, reading the
 * keys the Issues page builds: ``axe:rule`` and ``keyboard:rule`` (and the
 * other browser checks), ``semantic:2.4.6`` for AI review (whose findings
 * keep the whole key as their rule), and ``alfa:rule:failed`` or
 * ``alfa:rule:cant_tell``, one issue for each Alfa outcome.
 */
function findingInIssue(finding: PageEvidence["a11y_findings"][number], key: string): boolean {
  const [pipeline, rule, outcome] = key.split(":");
  if (!pipeline || !rule || finding.pipeline !== pipeline) return false;
  if (pipeline === "semantic") return finding.rule_id === key || finding.rule_id === rule;
  if (finding.rule_id !== rule) return false;
  if (pipeline === "alfa") return (finding.engine_outcome || "failed") === (outcome || "failed");
  return true;
}

function layoutForIssue(issueKey: string | null): CheckLayout | null {
  const [pipeline, rule] = (issueKey ?? "").split(":");
  if (pipeline !== "responsive") return null;
  switch (rule) {
    case "responsive-reflow-overflow":
      return {
        width: 320,
        height: 900,
        css: null,
        label: "320 pixels wide, where content must fit without scrolling sideways (WCAG 1.4.10).",
      };
    case "responsive-text-clipped":
      return {
        width: 640,
        height: 450,
        css: null,
        label: "640 by 450 pixels, which is how the page lays out at 200% zoom on a 1280-pixel screen (WCAG 1.4.4).",
      };
    case "responsive-text-spacing-clipped":
      return {
        width: null,
        height: null,
        css: TEXT_SPACING_CSS,
        label:
          "with WCAG's text spacing: line height 1.5, letter spacing 0.12 em, word spacing 0.16 em, and 2 em after each paragraph (WCAG 1.4.12).",
      };
    default:
      return null;
  }
}

/** ``html`` with a stylesheet added at the end of its head, so it wins the cascade. */
function withStyle(html: string, css: string): string {
  const style = `<style data-axcess-check-layout>${css}</style>`;
  const head = html.search(/<\/head>/i);
  return head === -1 ? style + html : html.slice(0, head) + style + html.slice(head);
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

