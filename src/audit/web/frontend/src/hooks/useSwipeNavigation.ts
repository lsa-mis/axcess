import { useEffect } from "react";

/**
 * Two-finger touchpad swipe to go back and forward, in the desktop app.
 *
 * Chromium browsers already do this, so in a browser tab the hook does
 * nothing: handling it here as well would navigate twice. The desktop app is
 * an Electron window with no such gesture, and no toolbar either, so there it
 * is implemented from the page's own wheel events, which is how a touchpad's
 * two-finger horizontal swipe arrives.
 *
 * It follows the browser's rules so it never fights scrolling:
 * - Only a mostly-horizontal pixel scroll counts. Vertical scrolling, a
 *   mouse wheel (line or page deltas), Shift+wheel and pinch-zoom (Ctrl)
 *   are ignored.
 * - A swipe over something that can still scroll sideways in that
 *   direction (the issue table on a narrow window, a long input) scrolls
 *   it instead. A gesture that scrolled anything never navigates, even
 *   once it reaches the edge, so scrolling to the end of a table does not
 *   carry on into the previous page.
 * - One gesture, one step. Touchpads keep sending momentum events after the
 *   fingers lift; the gesture only ends after a short quiet gap.
 *
 * Direction matches Chromium: scrolling past the left edge (negative
 * ``deltaX``) goes back, past the right edge goes forward.
 */
const THRESHOLD_PX = 120;
const GESTURE_GAP_MS = 250;

export function isDesktopApp(userAgent = navigator.userAgent): boolean {
  return /\bElectron\//.test(userAgent);
}

export function useSwipeNavigation(enabled = isDesktopApp()): void {
  useEffect(() => {
    if (!enabled) return;
    let travelled = 0;
    let done = false; // navigated or scrolled: ignore the rest of this gesture
    let lastEvent = 0;

    const onWheel = (event: WheelEvent) => {
      if (event.timeStamp - lastEvent > GESTURE_GAP_MS) {
        travelled = 0;
        done = false;
      }
      lastEvent = event.timeStamp;
      if (done) return;
      if (event.deltaMode !== WheelEvent.DOM_DELTA_PIXEL || event.ctrlKey || event.shiftKey) return;
      if (Math.abs(event.deltaX) <= Math.abs(event.deltaY)) return;

      const direction = event.deltaX < 0 ? -1 : 1;
      if (canScrollSideways(event.target, direction)) {
        done = true;
        return;
      }
      travelled += event.deltaX;
      if (Math.abs(travelled) < THRESHOLD_PX) return;
      done = true;
      if (travelled < 0) window.history.back();
      else window.history.forward();
    };

    window.addEventListener("wheel", onWheel, { passive: true });
    return () => window.removeEventListener("wheel", onWheel);
  }, [enabled]);
}

/** Whether ``target`` or an ancestor can still scroll further left (-1) or right (1). */
function canScrollSideways(target: EventTarget | null, direction: -1 | 1): boolean {
  for (
    let node = target instanceof Element ? target : null;
    node && node !== document.documentElement;
    node = node.parentElement
  ) {
    const scrolls =
      node instanceof HTMLInputElement ||
      node instanceof HTMLTextAreaElement ||
      /(auto|scroll)/.test(getComputedStyle(node).overflowX);
    if (!scrolls || node.scrollWidth <= node.clientWidth) continue;
    const atStart = node.scrollLeft <= 0;
    const atEnd = node.scrollLeft + node.clientWidth >= node.scrollWidth - 1;
    if (direction < 0 ? !atStart : !atEnd) return true;
  }
  return false;
}
