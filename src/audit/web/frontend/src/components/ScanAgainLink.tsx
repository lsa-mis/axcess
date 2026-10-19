import { RotateCw } from "lucide-react";
import { LinkButton } from "./ui";
import { cn } from "../lib/cn";

/**
 * "Scan again": opens New scan with one report's settings filled in
 * (`/scans/new?from=<id>`, the same path as "Change settings first" on a
 * failed scan). Used in each site's Actions menu on Reports (RowActionsMenu)
 * and beside "Export report" on Issues, so the same action reads the same,
 * with the same icon, in both places (WCAG 2.2 SC 3.2.4 Consistent
 * Identification, Level AA).
 *
 * - A link to the form, not a button that starts the scan. A scan crawls a
 *   real site and only one can run at a time; one stray click must not
 *   start one. The form is the confirmation step, and it shows what the
 *   scan will do before it starts. Starting at once was considered and
 *   rejected for that reason (the developer chose the form, Oct 2026). A
 *   sign-in scan also needs someone to sign in, which only the form offers.
 * - The icon comes with words. The developer first asked for an icon-only
 *   button; an icon alone makes a sighted reader guess what the arrow means,
 *   and a voice-control user cannot say its name (W3C COGA, "Making Content
 *   Usable", https://www.w3.org/TR/coga-usable/: clear words, not only
 *   symbols; docs/plain-language.md rule 8, a verb and an object). The
 *   developer chose the icon with "Scan again".
 * - The visible words come first in the name, then screen-reader-only words
 *   that say which site and whose settings (technique C7), so the name
 *   contains the visible label (SC 2.5.3 Label in Name, Level A) and the
 *   link makes sense out of its row (SC 2.4.9 Link Purpose (Link Only),
 *   Level AAA). No `aria-label`: real words carry the meaning.
 */
export default function ScanAgainLink({
  scanId,
  site,
  variant = "secondary",
  className,
}: {
  /** The report whose settings the form starts from. */
  scanId: number;
  /** The site as it is shown, for the screen-reader-only words. */
  site: string;
  variant?: "secondary" | "ghost";
  className?: string;
}) {
  return (
    <LinkButton
      to={`/scans/new?from=${scanId}`}
      variant={variant}
      className={cn("whitespace-nowrap", className)}
    >
      <RotateCw className="h-4 w-4" aria-hidden />
      Scan again
      <span className="sr-only">: {site}, starting from the settings of Report #{scanId}</span>
    </LinkButton>
  );
}
