import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, Download } from "lucide-react";
import { exportUrl } from "../api/client";
import { Button } from "./ui";

/**
 * The report's downloads, behind one control.
 *
 * The header used to carry two side-by-side download buttons ("Download
 * workbook", "Download report") competing with the page's own actions, while
 * the CSV and JSON renderers the server already exposes had no UI at all.
 * They are all the same job, take this report elsewhere, so they share one
 * button.
 *
 * This is the APG *disclosure* pattern, deliberately not the menu pattern:
 * the contents are ordinary links, so Tab, Enter, and a screen reader's link
 * list all behave the way users already expect. A `role="menu"` here would
 * take the links out of the tab order and buy nothing.
 */
const FORMATS: { format: string; label: string; hint: string }[] = [
  { format: "xlsx", label: "Remediation workbook", hint: "Excel · one row per issue, with fixes" },
  { format: "audit", label: "Audit report", hint: "Markdown · narrative report" },
  { format: "csv", label: "Issue table", hint: "CSV · one row per occurrence" },
  { format: "json", label: "Raw findings", hint: "JSON · full evidence payload" },
];

export default function ExportMenu({ scanId }: { scanId: number }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnOutsidePointer = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnOutsideFocus = (event: FocusEvent) => {
      // Re-entering the window refocuses <body> without the user having moved
      // anywhere; treating that as "focus left the menu" would snap the panel
      // shut whenever they alt-tabbed back to it.
      if (event.target === document.body) return;
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      // Escape returns focus to the trigger; closing a disclosure must never
      // drop the user at the top of the document.
      setOpen(false);
      buttonRef.current?.focus();
    };
    document.addEventListener("mousedown", closeOnOutsidePointer);
    // `focusin` is the keyboard half of the same rule: tabbing past the last
    // link dismisses the panel, so focus never lands behind something that is
    // still covering the page.
    document.addEventListener("focusin", closeOnOutsideFocus);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsidePointer);
      document.removeEventListener("focusin", closeOnOutsideFocus);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <Button
        ref={buttonRef}
        type="button"
        variant="secondary"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
      >
        <Download className="h-4 w-4" aria-hidden />
        Export
        <ChevronDown className="h-3.5 w-3.5" aria-hidden />
      </Button>
      <div
        id={panelId}
        hidden={!open}
        className="absolute right-0 z-30 mt-1.5 w-[19rem] max-w-[calc(100vw-2rem)] rounded-xs border border-border bg-surface p-1.5 shadow-raised"
      >
        <ul>
          {FORMATS.map((entry) => (
            <li key={entry.format}>
              {/* A plain <a download>, not a Router <Link>: the SPA is mounted
                  under basename="/app" and a Link would rewrite the /api path.
                  `draft=acknowledged` keeps an incomplete report downloadable
                  as a visibly labeled draft, which is the server's contract. */}
              <a
                href={exportUrl(scanId, entry.format, true)}
                download=""
                onClick={() => setOpen(false)}
                className="flex min-h-target flex-col justify-center rounded-2xs px-3 py-2 no-underline hover:bg-surface-muted"
              >
                <span className="text-sm font-semibold text-fg">{entry.label}</span>
                <span className="text-xs text-fg-muted">{entry.hint}</span>
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
