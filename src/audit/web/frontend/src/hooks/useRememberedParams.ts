import { useEffect, useLayoutEffect, useRef } from "react";
import { useSearchParams } from "react-router";

/**
 * Keeps some of a page's view parameters for the rest of the browser tab, so
 * coming back to the page by a link that carries none of them (the
 * navigation's "Reports") brings the view back as the reader left it.
 *
 * Why: a view kept in the URL survives Back, but not a fresh visit from the
 * navigation, which opens the bare address. Testers (2026-10-28) opened a
 * site's scans, went to another page, came back through the navigation, and
 * had to open the site again every time. W3C COGA, "Making Content Usable"
 * (https://www.w3.org/TR/coga-usable/), asks not to make people redo steps
 * (paraphrased); the cost of redoing them falls hardest on keyboard and
 * screen reader users, who find their place again row by row.
 *
 * On arrival, if the address names none of `names`, the remembered values
 * are put back in it, replacing the history entry, before the page paints.
 * An address that names any of them wins: a copied or bookmarked link opens
 * what it says. After that, every change is remembered.
 *
 * sessionStorage, not localStorage: the view lasts while the tab is open, as
 * history does, and a new tab starts clean. Storage that is off or full
 * leaves the page as it was without this.
 */
export function useRememberedParams(store: string, names: readonly string[]): void {
  const [params, setParams] = useSearchParams();
  const arrived = useRef(false);
  // The save after a restore would still see the address from before it.
  const skipSave = useRef(false);

  useLayoutEffect(() => {
    if (arrived.current) return;
    arrived.current = true;
    if (names.some((name) => params.has(name))) return;
    const saved = read(store).filter(([name]) => names.includes(name));
    if (saved.length === 0) return;
    const next = new URLSearchParams(params);
    for (const [name, value] of saved) next.append(name, value);
    skipSave.current = true;
    setParams(next, { replace: true });
    // Once, on arrival: later changes to the address are the reader's own.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const snapshot = JSON.stringify(names.flatMap((name) => params.getAll(name).map((value) => [name, value])));
  useEffect(() => {
    if (skipSave.current) {
      skipSave.current = false;
      return;
    }
    write(store, snapshot);
  }, [store, snapshot]);
}

function read(store: string): [string, string][] {
  try {
    const parsed: unknown = JSON.parse(window.sessionStorage.getItem(store) ?? "[]");
    return Array.isArray(parsed)
      ? parsed.filter(
          (pair): pair is [string, string] =>
            Array.isArray(pair) && pair.length === 2 && pair.every((part) => typeof part === "string"),
        )
      : [];
  } catch {
    return [];
  }
}

function write(store: string, snapshot: string): void {
  try {
    window.sessionStorage.setItem(store, snapshot);
  } catch {
    // Storage off or full: the page opens with its default view, as before.
  }
}
