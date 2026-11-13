/**
 * Copy text to the clipboard. Resolves true if it was copied, false if not.
 *
 * Why a fallback: browsers only give pages the modern clipboard API
 * (`navigator.clipboard`) on a secure address, meaning https, localhost or
 * 127.0.0.1. Axcess is often opened from another computer on the local
 * network over plain http (see docs/hosting.md), where that API is missing
 * and every copy button failed. The older method (copy the selection of a
 * hidden text box with `document.execCommand("copy")`) still works there.
 * It is deprecated but supported in every current browser, so it is tried
 * only when the modern API is missing or refuses.
 *
 * The fallback puts focus back where it was and restores the person's text
 * selection, so a keyboard or screen-reader user is not moved
 * (SC 2.4.3 Focus Order, Level A). The text box is read-only, off screen and
 * hidden from assistive technology, so nothing new is announced.
 *
 * Each copy button shows its own message when this returns false, so people
 * can still select the text and copy it by hand.
 */
export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Refused (for example a permission policy): try the older method.
    }
  }
  return copyWithSelection(text);
}

function copyWithSelection(text: string): boolean {
  const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const selection = window.getSelection();
  const ranges: Range[] = [];
  if (selection) for (let i = 0; i < selection.rangeCount; i += 1) ranges.push(selection.getRangeAt(i));

  const box = document.createElement("textarea");
  box.value = text;
  box.readOnly = true;
  box.setAttribute("aria-hidden", "true");
  box.tabIndex = -1;
  // Off screen but rendered: some browsers will not select a hidden element.
  box.style.position = "fixed";
  box.style.top = "0";
  box.style.left = "-9999px";
  box.style.opacity = "0";
  document.body.appendChild(box);

  let ok = false;
  try {
    box.focus({ preventScroll: true });
    box.select();
    box.setSelectionRange(0, text.length);
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  } finally {
    box.remove();
    active?.focus({ preventScroll: true });
    if (selection) {
      selection.removeAllRanges();
      for (const range of ranges) selection.addRange(range);
    }
  }
  return ok;
}
