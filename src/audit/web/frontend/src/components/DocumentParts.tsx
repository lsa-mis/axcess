import { Fragment } from "react";
import type { DocumentRefWay, LinkedFileRow } from "../api/types";
import BreakableUrl from "./BreakableUrl";
import HowSureTag from "./HowSureTag";
import {
  LINKED_FILE_CHECK_PROBLEM,
  LINKED_FILE_REF_LABEL,
  LINKED_FILE_STATUS_HELP,
  LINKED_FILE_STATUS_LABEL,
  LINKED_FILE_TYPE_LABEL,
  linkedFileReasonText,
} from "../lib/terms";

/*
 * The parts the Documents table (routes/Documents.tsx) and one document's
 * own page (routes/DocumentDetail.tsx) both show, so a fact about a file
 * looks and reads the same in both places (SC 3.2.4 Consistent
 * Identification, Level AA).
 */

/**
 * The name of the column that holds each file's value (Mostly sure, Not
 * sure, Could not check), said as the question those values answer.
 *
 * The values are Issues' words, but the column is not called "How sure" as
 * Issues' is: on its own, "How sure" did not say how sure of what, so "0
 * Mostly sure" told the reader nothing about the files (the developer's
 * report, 2026-11-13). Named as the question, the values read as answers:
 * "Accessibility problems? Mostly sure." The developer asked to keep the
 * values and change only this name. Rejected: new values ("Problems found",
 * "A person must check", "Not checked"), which the developer declined, and
 * "How sure", which left the question unsaid (SC 2.4.6 Headings and Labels,
 * Level AA; SC 3.3.2 Labels or Instructions, Level A).
 */
export const RESULT_COLUMN = "Accessibility problems?";

/**
 * The last column's name: the pages of the report where the file appears,
 * as a link or shown inside the page. The developer asked for "where it
 * appears" (2026-11-13); "Pages it appears on" keeps that word and says the
 * answer is pages. The order's second step in the labels note uses the same
 * words, so the column and its explanation match. Rejected: "Linked from",
 * which did not say from what and does not fit a file shown in a frame;
 * "Pages that link to it", which has the same frame problem; and "Where it
 * appears", too close to Issues' "Where it shows", which means something
 * else there (at page load, after clicking, in an image) (W3C COGA, "Making
 * Content Usable", https://www.w3.org/TR/coga-usable/, paraphrased: the
 * same word for the same thing, and different words for different things;
 * SC 3.2.4 Consistent Identification, Level AA).
 */
export const PAGES_COLUMN = "Pages it appears on";

/**
 * The name of the column, and of the fact on a document's page, that says
 * where the file is kept: its host ("docs.google.com") and whether that is
 * this site or another one. "Hosted on", not "Site" (the developer's
 * request, 2026-11-14): "Site" could be read as the page of our site the
 * file is on, which is "Pages it appears on". "Hosted on" says what the
 * column holds, the place the file itself lives (W3C COGA, "Making Content
 * Usable", https://www.w3.org/TR/coga-usable/, paraphrased: different words
 * for different things; SC 2.4.6 Headings and Labels, Level AA). Rejected:
 * "What hosts it", a question where the other headers are names.
 */
export const HOSTED_COLUMN = "Hosted on";

/** The host of a file's address ("hr.umich.edu"), or null for one that does not parse. */
export function hostOf(url: string): string | null {
  try {
    return new URL(url).host;
  } catch {
    return null;
  }
}

/** The file's "Accessibility problems?" value, as the Issues table's tag. */
export function ResultTag({ status }: { status: LinkedFileRow["status"] }) {
  return (
    <HowSureTag
      label={LINKED_FILE_STATUS_LABEL[status]}
      help={LINKED_FILE_STATUS_HELP[status]}
      quiet={status === "could_not_check"}
    />
  );
}

/**
 * What the checks found, for the Documents table's "What Axcess found"
 * column: each failed check by its short name, one a line, most serious
 * first; for a file that passed, what a person must still check; for one
 * Axcess could not check, why.
 *
 * Short names, not the sentence each used to be (LINKED_FILE_CHECK_PROBLEM
 * in terms.ts; the developer's choice, 2026-11-14): a column of hundreds of
 * files is scanned, not read, and why each matters is on the document's own
 * page, in its table of checks. Still a list (`ul`), without bullets, so a
 * screen reader says how many problems there are; the order is the
 * report's own severity order. "Has a form to fill in" is not here any
 * more: it is a fact about the file, not a problem, and read as one beside
 * them; it is under the Type (TypeCell). Rejected: tags for each problem,
 * which look like controls or filters (W3C COGA, "Making Content Usable":
 * what is not a control should not look like one); and "2 problems" with
 * the rest hidden, which takes the problems out of the table.
 */
export function Found({ row }: { row: LinkedFileRow }) {
  if (row.status === "mostly_sure") {
    return (
      <ul className="space-y-1">
        {row.failed_checks.map((check) => (
          <li key={check}>{LINKED_FILE_CHECK_PROBLEM[check]}</li>
        ))}
      </ul>
    );
  }
  if (row.status === "not_sure") return <p>{LINKED_FILE_STATUS_HELP.not_sure}</p>;
  return <p>{row.reason ? linkedFileReasonText(row.reason, row.http_status) : LINKED_FILE_STATUS_HELP.could_not_check}</p>;
}

/**
 * The file's type, and under it "Has a form to fill in" for a PDF with form
 * fields: what the file is, together. It used to sit with the problems in
 * "What Axcess found", where it read as one more problem.
 */
export function TypeCell({ row }: { row: LinkedFileRow }) {
  return (
    <>
      <span className="block">{LINKED_FILE_TYPE_LABEL[row.file_type]}</span>
      {row.is_form && <span className="block text-2xs text-fg-muted">Has a form to fill in</span>}
    </>
  );
}

/**
 * Where the file is kept (the "Hosted on" column, HOSTED_COLUMN): the site's name (its host, such as
 * docs.google.com) and whether that is the scanned site or another one.
 *
 * Its own column, as the developer asked, in place of the file's full
 * address and an "On another site" line under its name. The full address
 * was long, broke mid-word, and, inside the row header, was read out again
 * by a screen reader in every cell of the row (row headers are announced
 * with each cell; technique H63). The host says what a reader needs (whose
 * site, and whether it is ours) in a few words; the full address is the
 * target of the document page's "Open the file" link. Rejected: the full address in this column, which
 * kept the length; and the host under the name, which kept it in the row
 * header (SC 1.3.1 Info and Relationships, Level A; W3C COGA, "Making
 * Content Usable", https://www.w3.org/TR/coga-usable/, paraphrased: one
 * idea per chunk).
 */
export function SiteCell({ url, offSite }: { url: string; offSite: boolean }) {
  const host = hostOf(url);
  return (
    <>
      {host && (
        <span className="block" data-scanned-content>
          <BreakableUrl text={host} />
        </span>
      )}
      <span className="block text-2xs text-fg-muted">{offSite ? "Another site" : "This site"}</span>
    </>
  );
}

/**
 * The pages that reach the file, each a page link to the inspector, which
 * marks the link (or frame) there; and how, when it is not a plain link.
 *
 * The page's title only. Its full address and the link's own words are not
 * shown, as the developer asked (2026-11-13): the address was long and said
 * little, and the inspector now shows the link itself, outlined, in place.
 * The address still appears when two pages in the cell share a title, so
 * they can be told apart (SC 2.4.9 Link Purpose (Link Only), Level AAA).
 * No count line ("2 pages link to it."): the column's name says what the
 * list is, and the list is the count; only pages past the shown 20 are
 * counted, under it.
 */

/**
 * How one page shows the file: "Link", "Link, shown only after pressing
 * “More forms”", or "Shown inside the page (in a frame)", with the link's
 * own words where it has them. One line per way, for the document page's
 * "How it appears" column. The link's words are scanned content, quoted.
 */
export function HowItAppears({ ways }: { ways: DocumentRefWay[] }) {
  return (
    <ul className="space-y-1">
      {ways.map((way, index) => (
        <li key={`${way.how}-${index}`}>
          {way.how === "link" || way.how === "revealed_link" ? "Link" : LINKED_FILE_REF_LABEL[way.how]}
          {way.link_text && (
            <Fragment>
              {": "}
              <span data-scanned-content>&ldquo;{way.link_text}&rdquo;</span>
            </Fragment>
          )}
          {way.how === "revealed_link" && (
            <span className="block text-fg-muted">
              Appears only after pressing{" "}
              <span data-scanned-content>&ldquo;{way.revealed_by ?? "a control"}&rdquo;</span>
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
