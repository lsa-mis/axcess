import { useEffect, useRef, type RefObject } from "react";

/**
 * Keep a native ``<dialog>`` open as a modal while ``open`` is true.
 *
 * ``showModal()`` is what makes the dialog modal: the browser traps focus in
 * it, makes the page behind inert, closes it on Escape, and puts focus back on
 * the control that opened it. The dialog's own ``onClose`` should set ``open``
 * back to false, so Escape and the close button end in the same state.
 */
export function useModalDialog(open: boolean): RefObject<HTMLDialogElement | null> {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return ref;
}
