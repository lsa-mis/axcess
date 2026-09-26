import { X } from "lucide-react";
import { useModalDialog } from "../hooks/useModalDialog";
import { Button } from "./ui";

/** The global shortcuts, in the order the Settings page lists them. */
export const SHORTCUTS: ReadonlyArray<{ keys: string; action: string }> = [
  { keys: "⌘/Ctrl + K", action: "Search everything" },
  { keys: "⌘/Ctrl + B", action: "Show or hide the sidebar" },
  { keys: "Alt + 1", action: "Go to Reports" },
  { keys: "Alt + 2", action: "Go to About" },
  { keys: "Alt + 3", action: "Go to Settings" },
  { keys: "?", action: "Show this list" },
];

/**
 * The "?" shortcut list. A native modal <dialog>: the browser traps focus,
 * makes the page behind it inert and closes it on Escape, and focus returns
 * to wherever it was when the dialog opened.
 */
export default function ShortcutsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useModalDialog(open);

  return (
    <dialog
      ref={ref}
      aria-labelledby="shortcuts-title"
      onClose={onClose}
      className="w-[min(92vw,28rem)] rounded-xs border border-border bg-surface p-0 text-fg shadow-raised backdrop:bg-black/40"
    >
      <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-3">
        <h2 id="shortcuts-title" className="text-base font-semibold">
          Keyboard shortcuts
        </h2>
        <Button type="button" variant="ghost" onClick={onClose} aria-label="Close keyboard shortcuts">
          <X className="h-5 w-5" aria-hidden />
        </Button>
      </div>
      <dl className="divide-y divide-border px-5 py-2 text-sm">
        {SHORTCUTS.map((shortcut) => (
          <div key={shortcut.keys} className="flex items-center justify-between gap-4 py-2.5">
            <dt>{shortcut.action}</dt>
            <dd>
              <kbd className="rounded-2xs border border-border-strong bg-surface-muted px-2 py-0.5 font-mono text-xs">
                {shortcut.keys}
              </kbd>
            </dd>
          </div>
        ))}
      </dl>
      <p className="border-t border-border px-5 py-3 text-xs text-fg-muted">
        Turn these off in Settings if they clash with your assistive technology.
      </p>
    </dialog>
  );
}
