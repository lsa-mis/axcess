/**
 * Framed mode: the app running as one panel of Compare reports.
 *
 * Compare reports (routes/CompareReports.tsx) shows two reports side by side,
 * each the real app page in an `<iframe>`, so each panel works like its own
 * browser tab: open an issue, filter, go back, without changing the other.
 * Inside such a frame the app knows it is a panel, and this module is the one
 * place that decides it:
 *
 * - `FRAMED` is true only in a frame whose top window is Axcess itself (the
 *   same origin). A page framed by any other origin is not a panel: reading
 *   `window.top.location` throws there, and the app draws as usual.
 * - AppShell then leaves out the sidebar and top bar, so a panel shows only
 *   the page; ReportWorkspaceNav leaves out the "Compare reports" tab, and
 *   the Compare reports route shows a link to open it in the whole window,
 *   so frames never nest.
 *
 * **Each panel keeps its own history.** Frames share one history with the
 * window they are in, the "joint session history" of the HTML standard. The
 * browser's Back steps back in whichever frame changed last, and so does
 * `history.back()` or `navigation.back()` called on a frame's own window: we
 * measured this in Chromium (2026-10-29) with two frames, where Back called on
 * the first frame undid the second frame's last step. An iframe's `load` event
 * does not fire for the app's in-page navigation either (`pushState`), so the
 * outer page cannot follow a panel that way. So, in a panel:
 *
 * 1. Every navigation that would add a history entry replaces the current one
 *    instead (`pushState` becomes `replaceState`), and the entry it leaves is
 *    kept on this panel's own stack, here in the frame.
 * 2. The panel tells the outer page where it is, and whether it can go back,
 *    after every change (`reportPaneLocation`, from AppShell), by
 *    `postMessage` to its own origin only.
 * 3. The outer page's "Go back" button for the panel sends `back`; the panel
 *    puts the previous entry back and tells the router with a `popstate`
 *    event, exactly as the browser would for Back. The router then treats it
 *    as Back, so useScrollRestoration returns the panel to where the reader
 *    was: offsets are saved per entry key, and the restored entry keeps its key.
 *
 * The browser's Back and Forward, and the desktop app's swipe, then move only
 * the outer page: its address holds the two reports, so they undo a change of
 * report and never step one panel behind the other's back.
 *
 * Why the stack lives in the frame, not in the outer page: the entries are the
 * router's own history states (the key the scroll offsets are saved under),
 * which only the frame has; the outer page needs only "where" and "can it go
 * back", which the messages carry. A new report in a panel is a new frame
 * (CompareReports keys the iframe by report), so its stack starts empty and
 * "Go back" is exact: it is available only when the stack has an entry.
 *
 * Rejected: `iframe.contentWindow.history.back()`, the first plan, for the
 * joint history above; keeping the panels' pages in the outer address, so a
 * reload restores them, which would make the browser's Back step back
 * whichever panel changed last again; an Electron-only split view, which the
 * browser build would not get.
 */

/** Marks the messages a panel and the Compare reports page send each other. */
export const PANE_MESSAGE_SOURCE = "axcess-pane";

/** A panel's place, sent to the outer page after every change. */
export type PaneLocation = {
  /** The in-app path and query, with the `/app` base: "/app/scans/24/issues?q=x". */
  path: string;
  /** The page's name, as the document title gives it: "Accessibility issues". */
  title: string;
  /** Whether the panel's "Go back" has anywhere to go. */
  canGoBack: boolean;
};

export type PaneMessage =
  | ({ source: typeof PANE_MESSAGE_SOURCE; type: "location" } & PaneLocation)
  /** Outer page to panel: step back once in the panel's own history. */
  | { source: typeof PANE_MESSAGE_SOURCE; type: "back" }
  /** Outer page to panel: say where you are (sent when the frame loads). */
  | { source: typeof PANE_MESSAGE_SOURCE; type: "report" };

export function isPaneMessage(data: unknown): data is PaneMessage {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as { source?: unknown }).source === PANE_MESSAGE_SOURCE &&
    typeof (data as { type?: unknown }).type === "string"
  );
}

function detectFramed(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.self !== window.top && window.top?.location.origin === window.location.origin;
  } catch {
    // Another origin framed this page: not one of our panels.
    return false;
  }
}

/** Whether this document is a panel of Compare reports. Fixed for its lifetime. */
export const FRAMED = detectFramed();

/** How many steps back a panel remembers. */
const MAX_STEPS = 50;

type Entry = { state: unknown; url: string };
const stack: Entry[] = [];
let installed = false;
let replaceEntry: History["replaceState"] | null = null;
let lastTitle = "";

/**
 * Turn this document's history into a panel's own history (see above). Call
 * once, before the router is created; does nothing outside a panel.
 */
export function installPaneHistory(): void {
  if (!FRAMED || installed) return;
  installed = true;
  const history = window.history;
  const replace = history.replaceState.bind(history);
  replaceEntry = replace;
  history.pushState = (state: unknown, unused: string, url?: string | URL | null) => {
    stack.push({ state: history.state as unknown, url: window.location.href });
    if (stack.length > MAX_STEPS) stack.shift();
    replace(state, unused, url);
  };
  window.addEventListener("message", (event: MessageEvent) => {
    // Only the Compare reports page that holds this panel may drive it.
    if (event.origin !== window.location.origin || event.source !== window.parent) return;
    if (!isPaneMessage(event.data)) return;
    if (event.data.type === "back") paneBack();
    else if (event.data.type === "report") reportPaneLocation();
  });
}

function paneBack(): void {
  const entry = stack.pop();
  if (!entry || !replaceEntry) return;
  replaceEntry(entry.state, "", entry.url);
  // What the browser fires for Back: the router reads the restored entry,
  // treats it as Back (POP), and AppShell reports the new place.
  window.dispatchEvent(new PopStateEvent("popstate", { state: entry.state }));
}

/**
 * Tell the outer page where this panel is. AppShell calls it after every
 * change of place, with the page's name; does nothing outside a panel.
 */
export function reportPaneLocation(title?: string): void {
  if (!FRAMED) return;
  if (title) lastTitle = title;
  const message: PaneMessage = {
    source: PANE_MESSAGE_SOURCE,
    type: "location",
    path: window.location.pathname + window.location.search,
    title: lastTitle,
    canGoBack: stack.length > 0,
  };
  window.parent.postMessage(message, window.location.origin);
}
