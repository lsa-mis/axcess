import { RotateCw } from "lucide-react";
import { LinkButton } from "./ui";

/**
 * "Scan again": opens New scan with one report's settings filled in
 * (`/scans/new?from=<id>`, the same path as "Change settings first" on a
 * failed scan). Used beside "Export report" on Issues, its one home: Reports
 * opens the report in one click and leaves "Scan again" to it (see the
 * comment on routes/Scans.tsx for the dropdown this replaced).
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
 *   link makes sense on its own (SC 2.4.9 Link Purpose (Link Only),
 *   Level AAA). No `aria-label`: real words carry the meaning.
 */
export default function ScanAgainLink({
  scanId,
  site,
}: {
  /** The report whose settings the form starts from. */
  scanId: number;
  /** The site as it is shown, for the screen-reader-only words. */
  site: string;
}) {
  return (
    <LinkButton to={`/scans/new?from=${scanId}`} variant="secondary" className="whitespace-nowrap">
      <RotateCw className="h-4 w-4" aria-hidden />
      Scan again
      <span className="sr-only">: {site}, starting from the settings of report #{scanId}</span>
    </LinkButton>
  );
}
