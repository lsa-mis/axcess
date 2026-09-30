import { useEffect, useRef, useState } from "react";
import type { Announcements, Hints } from "../lib/preferences";
import { usePreferences } from "../hooks/usePreferences";

/**
 * The preferences that CSS alone cannot apply: the reading guide, how live
 * regions speak, and where control hints show. Mounted once by AppShell.
 *
 * Announcements and hints are applied to the DOM after React renders rather
 * than threaded through every component, so the twenty-odd live regions and
 * the many `title` hints in the app follow the setting without each having
 * to know it exists. Both keep the original value beside the one they write
 * and put it back when the setting returns to its default.
 */
export default function PreferenceEffects() {
  const prefs = usePreferences();
  useLiveRegionMode(prefs.announcements);
  useHintMode(prefs.hints);
  return (
    <>
      {prefs.readingGuide === "on" && <ReadingGuide />}
      {prefs.hints === "always" && <FocusHint />}
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Announcements                                                       */
/* ------------------------------------------------------------------ */

const LIVE_ORIGINAL = "data-axcess-live";
// Polite regions only, explicit or implied by role="status". Alerts stay
// assertive in every mode: an error must be heard even with "Visual only".
const LIVE_SELECTOR = `[aria-live="polite"], [role="status"]:not([aria-live]), [${LIVE_ORIGINAL}]`;

function applyLiveMode(el: Element, mode: Announcements) {
  if (!el.hasAttribute(LIVE_ORIGINAL)) {
    if (mode === "polite") return;
    el.setAttribute(LIVE_ORIGINAL, el.getAttribute("aria-live") ?? "");
  }
  if (mode === "polite") {
    const original = el.getAttribute(LIVE_ORIGINAL);
    el.removeAttribute(LIVE_ORIGINAL);
    if (original) el.setAttribute("aria-live", original);
    else el.removeAttribute("aria-live");
    return;
  }
  const wanted = mode === "immediate" ? "assertive" : "off";
  if (el.getAttribute("aria-live") !== wanted) el.setAttribute("aria-live", wanted);
}

function useLiveRegionMode(mode: Announcements) {
  useEffect(() => {
    const sweep = (root: ParentNode) => {
      root.querySelectorAll(LIVE_SELECTOR).forEach((el) => applyLiveMode(el, mode));
    };
    sweep(document);
    if (mode === "polite") return;
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "attributes") {
          applyLiveMode(record.target as Element, mode);
        } else {
          record.addedNodes.forEach((node) => {
            if (!(node instanceof Element)) return;
            if (node.matches(LIVE_SELECTOR)) applyLiveMode(node, mode);
            sweep(node);
          });
        }
      }
    });
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["aria-live"],
    });
    return () => observer.disconnect();
  }, [mode]);
}

/* ------------------------------------------------------------------ */
/* Descriptions and hints                                              */
/* ------------------------------------------------------------------ */

const TITLE_ORIGINAL = "data-axcess-title";

/**
 * "Off" parks each `title` so the browser shows no tooltip; the text is kept
 * on the element and restored when hints come back. Accessible names never
 * depend on `title` in this app (controls carry a label or aria-label), so
 * parking it removes a tooltip, not a name.
 */
function useHintMode(mode: Hints) {
  useEffect(() => {
    if (mode !== "off") {
      document.querySelectorAll(`[${TITLE_ORIGINAL}]`).forEach((el) => {
        el.setAttribute("title", el.getAttribute(TITLE_ORIGINAL) ?? "");
        el.removeAttribute(TITLE_ORIGINAL);
      });
      return;
    }
    const park = (el: Element) => {
      const title = el.getAttribute("title");
      if (!title) return;
      el.setAttribute(TITLE_ORIGINAL, title);
      el.removeAttribute("title");
    };
    document.querySelectorAll("[title]").forEach(park);
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "attributes") park(record.target as Element);
        record.addedNodes.forEach((node) => {
          if (!(node instanceof Element)) return;
          park(node);
          node.querySelectorAll("[title]").forEach(park);
        });
      }
    });
    observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["title"] });
    return () => observer.disconnect();
  }, [mode]);
}

/**
 * "Always": the hover tooltip becomes a visible hint under the control, and
 * it shows on keyboard focus too, where a native tooltip never appears. It
 * is aria-hidden because the same text is already the control's title (and
 * so its description) for assistive tech.
 */
function FocusHint() {
  const [hint, setHint] = useState<{ text: string; top: number; left: number } | null>(null);

  useEffect(() => {
    let active: Element | null = null;
    let parked = "";
    // Whether an aria-description was added while a title was parked, so
    // only that one is taken away again.
    let addedDescription = false;
    const show = (el: Element | null, pointer = false) => {
      if (active && parked) {
        active.setAttribute("title", parked);
        if (addedDescription) active.removeAttribute("aria-description");
      }
      active = null;
      parked = "";
      addedDescription = false;
      const target = el?.closest("[title]");
      const text = target?.getAttribute("title")?.trim();
      if (!target || !text) return setHint(null);
      // Under a pointer, park the title while ours shows, so the native
      // tooltip does not stack on it, and keep its words as the control's
      // description meanwhile: a screen reader user may also use a pointer.
      // On keyboard focus a browser shows no tooltip, and the title stays.
      if (pointer) {
        active = target;
        parked = text;
        target.removeAttribute("title");
        if (!target.hasAttribute("aria-description")) {
          target.setAttribute("aria-description", text);
          addedDescription = true;
        }
      }
      const box = target.getBoundingClientRect();
      setHint({ text, top: box.bottom + 6, left: Math.max(8, Math.min(box.left, window.innerWidth - 328)) });
    };
    const onOver = (event: Event) => show(event.target as Element, true);
    const onFocus = (event: Event) => show(event.target as Element);
    const onLeave = () => show(null);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") show(null);
    };
    document.addEventListener("pointerover", onOver);
    document.addEventListener("focusin", onFocus);
    document.addEventListener("focusout", onLeave);
    window.addEventListener("scroll", onLeave, true);
    document.addEventListener("keydown", onKey);
    return () => {
      show(null);
      document.removeEventListener("pointerover", onOver);
      document.removeEventListener("focusin", onFocus);
      document.removeEventListener("focusout", onLeave);
      window.removeEventListener("scroll", onLeave, true);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  if (!hint) return null;
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed z-[60] max-w-[320px] rounded-xs border border-border-strong bg-surface px-2.5 py-1.5 text-xs text-fg shadow-raised"
      style={{ top: hint.top, left: hint.left }}
    >
      {hint.text}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Reading guide                                                       */
/* ------------------------------------------------------------------ */

/**
 * A soft band at the pointer's height. It never takes a click, is hidden
 * from assistive tech, and follows the pointer directly (no easing), so it
 * is not motion in the SC 2.3.3 sense.
 */
function ReadingGuide() {
  const band = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const move = (event: PointerEvent) => {
      const el = band.current;
      if (!el) return;
      el.style.transform = `translateY(${event.clientY}px)`;
      el.style.opacity = "1";
    };
    const hide = () => {
      if (band.current) band.current.style.opacity = "0";
    };
    window.addEventListener("pointermove", move, { passive: true });
    document.documentElement.addEventListener("pointerleave", hide);
    return () => {
      window.removeEventListener("pointermove", move);
      document.documentElement.removeEventListener("pointerleave", hide);
    };
  }, []);
  return (
    <div
      ref={band}
      aria-hidden
      className="pointer-events-none fixed inset-x-0 top-0 z-[55] -mt-5 h-10 border-y border-umich-blue/25 bg-umich-maize/15 opacity-0"
    />
  );
}
