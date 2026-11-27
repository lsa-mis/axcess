import { Fragment } from "react";
import { FileSpreadsheet, FileText, Presentation } from "lucide-react";
import { dayKey, formatDay } from "../lib/days";
import { documentThumbnailUrl } from "../api/client";
import type { DocumentRefWay, LinkedFileRow, LinkedFileType } from "../api/types";
import BreakableUrl from "./BreakableUrl";
import HowSureTag from "./HowSureTag";
import ColumnHelp from "./table/ColumnHelp";
import {
  LINKED_FILE_CHECKED_AS_LABEL,
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

/**
 * The "Creation date" column (the developer's request, 2026-11-25, to tell
 * current documents from old ones that may be archived): the day the file
 * says it was first created, from its own properties (a Word or PowerPoint
 * file's core properties, a PDF's document information or XMP metadata;
 * audit/linked_files/file_dates.py). Named as the developer asked.
 *
 * Its limits are said where the date is read, in the column's "?" and in
 * "What the labels mean" (CREATED_HELP), never left out to keep it short
 * (AGENTS.md, Interface language rule 4): a creation date is not the day a
 * file was posted (on finance.umich.edu, 16 of 33 files were created more
 * than a year before their upload month), Google Docs and Slides exports
 * never carry one, and it is only as right as the clock of the computer
 * that made the file.
 *
 * The day is shown as the file records it, not moved into the reader's
 * time zone: a file made at midnight UTC on 17 July is a 17 July file
 * everywhere. Written out in the reader's own way ("July 17, 2018" or "17
 * July 2018"), as the report's other dates are (CompareReports), not as
 * 2018-07-17, which readers in different countries read differently; the
 * ISO date goes in the `<time>` element's dateTime, for software (HTML's
 * own element for a date; no ARIA needed).
 *
 * Known cost: the column makes the Documents table wider than 1280px with
 * the sidebar open, so "Pages it appears on" now scrolls into view in the
 * table's own region (TableRegion; SC 1.4.10 Reflow, Level AA, allows this
 * for a data table). The developer accepted this, 2026-11-25.
 */
export const CREATED_COLUMN = "Creation date";

/** The two things the column can say, for its "?" and the labels note. */
export const CREATED_HELP = {
  // Google files since 2026-11-26: a scan signed in to Google reads the
  // day from Google's File, Details (linked_files/google_session.py).
  date: "The day the file says it was first created, read from the file itself. For a Google Doc, Sheet or Slides file, it is the day Google’s File, Details says it was created. It is not the day the file was posted on the site: a file copied from an older one keeps the older date. It can also be wrong if the computer that made the file had the wrong date.",
  unknown:
    "The file does not say when it was created, Axcess could not open the file, or the report was made before Axcess version 0.2.12. A Google Doc, Sheet or Slides file has a date only when the scan was signed in to Google with an account that can open it.",
} as const;

/** A file's creation date for its cell, or "Not known" (CREATED_HELP). */
export function CreatedDate({ iso }: { iso: string | null | undefined }) {
  const key = dayKey(iso);
  if (!key) return <span className="text-fg-muted">Not known</span>;
  return <time dateTime={key}>{formatDay(key)}</time>;
}

/**
 * The "?" on the "Creation date" header: what a date and "Not known" mean,
 * in the words "What the labels mean" uses (CREATED_HELP). A "?" because
 * the date's limits change how it can be used (ColumnHelp: a "?" where a
 * word needs explaining).
 */
export function CreatedColumnHelp() {
  return (
    <ColumnHelp
      question={`What does \u201c${CREATED_COLUMN}\u201d mean`}
      answers="when the file says it was first created"
      items={[
        { key: "date", term: <span className="font-semibold text-fg">A date</span>, help: CREATED_HELP.date },
        { key: "unknown", term: <span className="text-fg-muted">Not known</span>, help: CREATED_HELP.unknown },
      ]}
    />
  );
}

/** One document's own page, where its facts and every page it appears on are listed. */
export function documentPath(scanId: number, fileId: number): string {
  return `/scans/${scanId}/documents/${fileId}`;
}

/** The host of a file's address ("hr.umich.edu"), or null for one that does not parse. */
export function hostOf(url: string): string | null {
  try {
    return new URL(url).host;
  } catch {
    return null;
  }
}

/**
 * The file's "Accessibility problems?" value, as the Issues table's tag.
 * ``hint={false}`` drops its hover hint where the meaning is already written
 * beside it (the column's "?", StatusColumnHelp), as Issues' LaneTag does.
 */
export function ResultTag({ status, hint = true }: { status: LinkedFileRow["status"]; hint?: boolean }) {
  return (
    <HowSureTag
      label={LINKED_FILE_STATUS_LABEL[status]}
      help={hint ? LINKED_FILE_STATUS_HELP[status] : undefined}
      quiet={status === "could_not_check"}
    />
  );
}

const STATUS_ORDER = ["mostly_sure", "not_sure", "could_not_check"] as const;

/**
 * The "?" on the Documents table's "Accessibility problems?" header (the
 * developer's request, 2026-11-16, like Issues' How sure): what the column
 * asks and what each value means, in the words the tags' hints and "What
 * the labels mean" use (LINKED_FILE_STATUS_HELP). The shared ColumnHelp
 * says why only some headers have one.
 */
export function StatusColumnHelp() {
  return (
    <ColumnHelp
      question={`What does \u201c${RESULT_COLUMN}\u201d mean`}
      answers="how sure Axcess is that the file has accessibility problems"
      items={STATUS_ORDER.map((status) => ({
        key: status,
        term: <ResultTag status={status} hint={false} />,
        help: LINKED_FILE_STATUS_HELP[status],
      }))}
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
  return (
    <>
      <FoundResult row={row} />
      {/* A copy of another file in the list (the same bytes at another
          address): its result is that file's, and one fix fixes both, so
          the row says which. Words only, not a link: the row's one link is
          its name (one way to do one thing; W3C COGA, "Making Content
          Usable"); the document's own page links to the first copy. */}
      {row.same_as && (
        <p className="mt-1 text-2xs text-fg-muted">
          Same file as <span data-scanned-content>{row.same_as.name}</span>
        </p>
      )}
    </>
  );
}

/*
 * Possible problems (Word and PowerPoint only: table header rows,
 * headings, heading levels, link text, a document title) come after the
 * problems, under their own words, "Possible problems:", so a reader never
 * takes one for a proven problem: they do not make a file Mostly sure
 * (office_check.COUNTED; the developer's rule of 2026-11-17, only a
 * machine-checkable barrier to a screen reader user counts, and the two
 * tiers of 2026-11-20, only the checks with no false alarm on real files
 * count). A list of its own, so a screen reader says
 * how many. Rejected: one list with both kinds, which would let a link's
 * words look as serious as an image with no alt text; and leaving them to
 * the document's page, which hides them from the table a reader works
 * from (W3C COGA, "Making Content Usable", https://www.w3.org/TR/coga-usable/,
 * paraphrased: group related content, and make the most important thing
 * clear).
 */
function FoundResult({ row }: { row: LinkedFileRow }) {
  const possible = row.possible_problems ?? [];
  if (row.status === "could_not_check") {
    return (
      <p>
        {row.reason ? linkedFileReasonText(row.reason, row.http_status, row.file_type, row.url) : LINKED_FILE_STATUS_HELP.could_not_check}
      </p>
    );
  }
  return (
    <>
      {row.status === "mostly_sure" ? (
        <ul className="space-y-1">
          {row.failed_checks.map((check) => (
            <li key={check}>{LINKED_FILE_CHECK_PROBLEM[check]}</li>
          ))}
        </ul>
      ) : (
        <p>{LINKED_FILE_STATUS_HELP.not_sure}</p>
      )}
      {possible.length > 0 && (
        <>
          <p className="mt-2 text-fg-muted">Possible problems:</p>
          <ul className="space-y-1 text-fg-muted">
            {possible.map((check) => (
              <li key={check}>{LINKED_FILE_CHECK_PROBLEM[check]}</li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}

/**
 * The file's type, and under it "Has a form to fill in" for a PDF with form
 * fields: what the file is, together. It used to sit with the problems in
 * "What Axcess found", where it read as one more problem.
 *
 * Also under it, when the check read the file as another type than its
 * link names (``checkedAsNote``): a Google Doc "Checked as the Word file
 * Google exports" (the developer's request, 2026-11-17), since a Google file
 * has no original file and the results are about Google's export of it.
 */
export function TypeCell({ row }: { row: LinkedFileRow }) {
  const checkedAs = checkedAsNote(row);
  return (
    <>
      <span className="block">{LINKED_FILE_TYPE_LABEL[row.file_type]}</span>
      {checkedAs && <span className="block text-2xs text-fg-muted">{checkedAs}</span>}
      {row.is_form && <span className="block text-2xs text-fg-muted">Has a form to fill in</span>}
    </>
  );
}

/** The type a link names, as the check would read it; null for one no check reads. */
const NAMED_AS: Partial<Record<LinkedFileType, NonNullable<LinkedFileRow["checked_as"]>>> = {
  pdf: "pdf",
  docx: "docx",
  pptx: "pptx",
};

/**
 * What the check read a file as, when that is not what its link names; null
 * otherwise. A Google Doc or Slides deck is checked as the Word or
 * PowerPoint file Google exports (google.export_address); a file kept in
 * Google Drive, or a link that led to another type, as what its bytes are.
 */
export function checkedAsNote(row: LinkedFileRow): string | null {
  const as = row.checked_as;
  if (!as || NAMED_AS[row.file_type] === as) return null;
  if (row.file_type === "google_doc" || row.file_type === "google_slides") {
    return `Checked as the ${LINKED_FILE_CHECKED_AS_LABEL[as]} file that Google exports`;
  }
  return `Checked as a ${LINKED_FILE_CHECKED_AS_LABEL[as]} file`;
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

const SHEETS: ReadonlySet<LinkedFileType> = new Set(["xlsx", "xls", "ods", "google_sheet"]);
const SLIDES: ReadonlySet<LinkedFileType> = new Set(["pptx", "ppt", "odp", "google_slides"]);

/**
 * A small picture of the document's first page, above its name in the
 * Documents table: the same 72 by 48 framed box, white behind the picture,
 * as an image's thumbnail on the Images tab (routes/Images.tsx, ImageRow),
 * the developer's request (2026-11-16), so the two lists of things found on
 * the pages look alike (SC 3.2.4 Consistent Identification, Level AA).
 *
 * Only a PDF the check could read has a picture (the scan draws page 1;
 * audit.linked_files.thumbnail). Any other file gets the same box with an
 * icon for its kind (text, spreadsheet, slides), so a missing picture does
 * not look like a broken one. Rejected: letters such as "DOCX" in the box,
 * as the Images tab writes "SVG": an abbreviation a reader may not know
 * (WCAG SC 3.1.4 Abbreviations, Level AAA), and the Type column already
 * says the kind in words.
 *
 * Decorative (alt="", the icon aria-hidden): the file's name is right under
 * it, inside the same link, and says which file it is; describing the
 * picture would only repeat it (WCAG technique H2, image and text in one
 * link; H67, decorative images). Inside the name's link, not a link of its
 * own: one link per row (one way to do one thing; W3C COGA, "Making Content
 * Usable"), and a bigger target. Not a button that opens a viewer as on
 * Images: there the picture is what is judged; here the document's own page
 * shows it larger (DocumentPreview).
 *
 * The Images tab draws its box inline; this is its own component because
 * the Images tab is being changed elsewhere (2026-11-16). Both should use
 * one shared thumbnail box once that work lands.
 */
export function DocumentThumbnail({ scanId, row }: { scanId: number; row: LinkedFileRow }) {
  if (row.has_thumbnail) {
    return (
      <img
        src={documentThumbnailUrl(scanId, row.file_id, "small")}
        alt=""
        loading="lazy"
        decoding="async"
        width={72}
        height={48}
        className="h-12 w-[72px] shrink-0 rounded-xs border border-border bg-white object-contain"
      />
    );
  }
  const Icon = SHEETS.has(row.file_type) ? FileSpreadsheet : SLIDES.has(row.file_type) ? Presentation : FileText;
  return (
    <span
      aria-hidden="true"
      className="flex h-12 w-[72px] shrink-0 items-center justify-center rounded-xs border border-border bg-surface-muted text-fg-muted"
    >
      <Icon className="h-5 w-5" />
    </span>
  );
}

/**
 * The first page, larger, on the document's own page, beside its facts: a
 * reader can tell the file at a glance before opening it. 160 CSS pixels
 * wide (the picture is drawn 480 wide, so it stays sharp). A ``figure``
 * whose caption says what the picture is, "First page", so the picture
 * itself is alt="" (WCAG technique H67) rather than a made-up description
 * of a page no one has read. Nothing is drawn for a file without a picture:
 * the Type fact beside it already says what kind of file it is.
 */
export function DocumentPreview({ scanId, row }: { scanId: number; row: LinkedFileRow }) {
  if (!row.has_thumbnail) return null;
  return (
    <figure className="w-40 shrink-0">
      <img
        src={documentThumbnailUrl(scanId, row.file_id)}
        alt=""
        decoding="async"
        width={160}
        className="w-40 rounded-xs border border-border bg-white"
      />
      <figcaption className="mt-1 text-2xs text-fg-muted">First page</figcaption>
    </figure>
  );
}
