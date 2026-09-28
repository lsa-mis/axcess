import { useEffect, useLayoutEffect, useRef } from "react";
import { useLocation, useNavigationType } from "react-router";

/**
 * Where the window is scrolled, per history entry: a new page starts at the
 * top, and Back or Forward returns to where the reader was.
 *
 * Every route used to start at the top, Back included: opening a report from
 * far down the Reports table and pressing Back put the reader at the top of
 * the table, to find their place again row by row, which costs most for
 * keyboard and screen reader users (W3C COGA, "Making Content Usable",
 * https://www.w3.org/TR/coga-usable/: do not make people redo steps). The
 * browser's own restoration cannot do this for an app that draws its page
 * after the address changes, so it is turned off (`manual`) and done here:
 *
 * - A new page (a link, pushed) starts at the top, as before: opening a
 *   short page from a long one must not land the reader partway down it.
 * - Back and Forward (POP) return to the entry's saved offset, retried for
 *   a moment while the page's content arrives and grows tall enough.
 * - A replaced entry on the same page (a sort, a search, a row opened, kept
 *   in the URL) keeps the offset: the reader has not gone anywhere.
 *
 * Offsets are saved as the reader scrolls, under the entry's key, in
 * sessionStorage, so a reload returns to the same place too. Focus is not
 * moved here: AppShell moves it to the main content on every change of
 * page, Back included. (Returning it to the link the reader followed is
 * not done yet.)
 */
export function useScrollRestoration(): void {
  const location = useLocation();
  const type = useNavigationType();
  const keyRef = useRef(location.key);
  const pathRef = useRef<string | null>(null);

  useEffect(() => {
    if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
    const onScroll = () => save(keyRef.current, window.scrollY);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useLayoutEffect(() => {
    const previousKey = keyRef.current;
    const previousPath = pathRef.current;
    keyRef.current = location.key;
    pathRef.current = location.pathname;
    const samePage = previousPath === location.pathname;

    if (type === "POP") {
      const saved = read(location.key);
      if (saved !== null) return restore(saved);
      if (!samePage) window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      return;
    }
    if (samePage) {
      // The view changed in place: carry the offset to the new entry.
      const offset = read(previousKey) ?? window.scrollY;
      save(location.key, offset);
      return;
    }
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }, [location.key, location.pathname, type]);
}

const STORE = "axcess-scroll";
const MAX_ENTRIES = 50;

function load(): Record<string, number> {
  try {
    return JSON.parse(window.sessionStorage.getItem(STORE) ?? "{}") as Record<string, number>;
  } catch {
    return {};
  }
}

function save(key: string, offset: number): void {
  try {
    const all = load();
    delete all[key];
    all[key] = Math.round(offset);
    const keys = Object.keys(all);
    for (const old of keys.slice(0, Math.max(0, keys.length - MAX_ENTRIES))) delete all[old];
    window.sessionStorage.setItem(STORE, JSON.stringify(all));
  } catch {
    // Storage off or full: Back starts at the top, as it did before.
  }
}

function read(key: string): number | null {
  const offset = load()[key];
  return typeof offset === "number" ? offset : null;
}

/**
 * Scroll to ``offset``, again every 50ms for up to 1.5s while the page is
 * not yet tall enough to reach it (its data still arriving). Returns the
 * cleanup that stops trying, for the effect.
 */
function restore(offset: number): () => void {
  let tries = 0;
  let timer: number | undefined;
  const attempt = () => {
    window.scrollTo({ top: offset, left: 0, behavior: "instant" });
    tries += 1;
    if (Math.abs(window.scrollY - offset) > 1 && tries < 30) timer = window.setTimeout(attempt, 50);
  };
  attempt();
  // A reader who scrolls on their own while it retries is not pulled back.
  const stop = () => window.clearTimeout(timer);
  window.addEventListener("wheel", stop, { once: true, passive: true });
  window.addEventListener("keydown", stop, { once: true });
  window.addEventListener("touchstart", stop, { once: true, passive: true });
  return () => {
    stop();
    window.removeEventListener("wheel", stop);
    window.removeEventListener("keydown", stop);
    window.removeEventListener("touchstart", stop);
  };
}
