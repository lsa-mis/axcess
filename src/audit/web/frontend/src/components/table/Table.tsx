import {
  useEffect,
  useRef,
  useState,
  type HTMLAttributes,
  type ReactNode,
  type Ref,
  type TdHTMLAttributes,
  type ThHTMLAttributes,
} from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, Search } from "lucide-react";
import { cn } from "../../lib/cn";
import { ariaSort, nextSort, sortChip, type Sort, type SortKind } from "./sort";

/*
 * The one table design, laid out top to bottom the way every table reads:
 *
 *   TableBar       search and the Filter menu (./FilterMenu) on the left,
 *                  the pager (../TablePagination) on the right, and the
 *                  active filters written out beneath
 *   TableStatus    the polite line that says how the rows are ordered
 *   TableRegion    the keyboard-scrollable region, and the height hold that
 *                  keeps the table's foot still between pages
 *     Table, TableHead, SortHeader / ColumnHeader
 *     Row, RowHeader, Cell    striped rows, one target tall
 *
 * Tables compose these rather than restyling a <table>, so a change to the
 * design lands everywhere at once.
 */

/**
 * Rounds a table part's corners when it is the first or last thing in a Card
 * (`data-card`, ../ui.tsx), so its fill follows the card's corners instead of
 * painting square ones over them. 7px is the card's radius (`rounded-xs`,
 * 8px) less its 1px border. A part that clips (the scroll region) clips its
 * rows to the same curve.
 */
const CARD_EDGE = "[[data-card]>&:first-child]:rounded-t-[7px] [[data-card]>&:last-child]:rounded-b-[7px]";

/**
 * The one bar over every table, styled like a pager bar: what narrows the
 * rows (search, the Filter menu) on the left, the pager on the right, and
 * `footer` (the active filters) under both. It wraps on a narrow screen
 * rather than clipping: the pager drops under the search.
 */
export function TableBar({
  children,
  pager,
  footer,
}: {
  children?: ReactNode;
  pager?: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className={cn("border-b border-border bg-surface-subtle", CARD_EDGE)}>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 px-4 py-3">
        {children && <div className="flex min-w-0 flex-[1_1_20rem] flex-wrap items-center gap-2">{children}</div>}
        {pager}
      </div>
      {footer}
    </div>
  );
}

/**
 * Search box for a table's bar. Keystrokes stay in the box; the term
 * reaches the table after a short pause, so a long table re-sorts and
 * re-filters once per pause rather than once per key. Escape clears it at
 * once. A term set from outside (a cleared filter, a pasted link) replaces
 * what was typed.
 */
export function TableSearch({
  label,
  value,
  onChange,
  placeholder = label,
  id,
  delay = 200,
  className,
}: {
  /** The accessible name, "Search issues". */
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  id?: string;
  delay?: number;
  className?: string;
}) {
  const [draft, setDraft] = useState(value);
  const latest = useRef(onChange);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const published = useRef(value);
  useEffect(() => {
    latest.current = onChange;
  }, [onChange]);
  useEffect(() => {
    if (value === published.current) return;
    published.current = value;
    clearTimeout(timer.current);
    setDraft(value);
  }, [value]);
  useEffect(() => () => clearTimeout(timer.current), []);
  const publish = (next: string) => {
    clearTimeout(timer.current);
    published.current = next;
    latest.current(next);
  };
  return (
    <div className={cn("relative min-w-[min(100%,14rem)] max-w-sm flex-1 basis-64", className)}>
      <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle" aria-hidden />
      <input
        id={id}
        type="search"
        aria-label={label}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        value={draft}
        onChange={(event) => {
          const next = event.target.value;
          setDraft(next);
          clearTimeout(timer.current);
          timer.current = setTimeout(() => publish(next), delay);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape" && draft) {
            event.preventDefault();
            setDraft("");
            publish("");
          }
        }}
        className="min-h-target w-full rounded-xs border border-border-strong bg-surface py-2 pl-10 pr-3 text-base text-fg focus:border-umich-blue focus:outline-none focus-visible:shadow-focus"
      />
    </div>
  );
}

/**
 * The line under the bar that says how the table is ordered and
 * filtered. It is a polite live region and it is visible, so a sort or a
 * filter is confirmed to everyone, not only to a screen reader. `actions`
 * sit beside it, outside the live region, so their names are not read out
 * with every change.
 */
export function TableStatus({
  children,
  actions,
  className,
}: {
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-h-target flex-wrap items-center gap-x-3 border-b border-border bg-surface-subtle px-3 py-1 text-xs text-fg-muted",
        CARD_EDGE,
        className,
      )}
    >
      <p role="status" aria-live="polite">
        {children}
      </p>
      {actions}
    </div>
  );
}

/** What `TableRegion` needs from `usePagedRows`. */
type Paged = {
  hold: { ref: (node: HTMLElement | null) => void; style: { minHeight?: number } };
};

/**
 * The scroll region around a table. Keyboard users need focus on it to
 * scroll a wide table sideways, so it takes focus and carries a name. With
 * `paged`, it holds the tallest page's height, so turning to a short last
 * page does not pull everything under the table up the screen.
 */
export function TableRegion({
  label,
  paged,
  busy,
  regionRef,
  className,
  children,
}: {
  label: string;
  paged?: Paged;
  busy?: boolean;
  regionRef?: Ref<HTMLDivElement>;
  /**
   * A frame, for a table inside another box: `rounded-xs border`. The frame
   * goes here, not on the <table>: a table's own corners stay square
   * (browsers ignore border-radius on a table with collapsed borders), and
   * the region, which clips, clips the rows to its rounded corners.
   */
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      ref={regionRef}
      role="region"
      aria-label={label}
      aria-busy={busy || undefined}
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
      tabIndex={0}
      className={cn("overflow-x-auto focus:outline-none focus-visible:shadow-focus", CARD_EDGE, className)}
    >
      {paged ? <div {...paged.hold}>{children}</div> : children}
    </div>
  );
}

/**
 * The table and its caption. The caption is visually hidden unless
 * `captionClassName` gives it a look, but it is always there: it is the
 * table's accessible name.
 */
export function Table({
  caption,
  captionClassName = "sr-only",
  className,
  children,
}: {
  caption: ReactNode;
  captionClassName?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <table className={cn("w-full text-sm", className)}>
      <caption className={captionClassName}>{caption}</caption>
      {children}
    </table>
  );
}

export function TableHead({ children, className }: { children: ReactNode; className?: string }) {
  // fg-muted, not fg-subtle: 7.7:1 even on a tinted group header (fg-subtle
  // was 5.9:1 there, and only just 7.2:1 on the plain header). The same
  // size as the cells (14px), not smaller: a header is read to make sense
  // of every cell under it.
  return <thead className={cn("bg-surface-muted text-sm text-fg-muted", className)}>{children}</thead>;
}

type HeaderProps = Omit<ThHTMLAttributes<HTMLTableCellElement>, "scope" | "children" | "className" | "align">;

/**
 * A column header that sorts (WAI-ARIA sortable table): `aria-sort` on the
 * cell and a real button inside it, so the sort is reachable and operable
 * by keyboard.
 *
 * The sorted column is underlined in blue across the whole cell, so the eye
 * finds it before reading anything, and its button says how it is sorted,
 * in words, in a chip ("high → low"). The chip re-keys on each change so it
 * pops in again, a quiet cue that the order just moved. Unsorted headers
 * keep a faint two-way arrow, the promise that they sort too.
 *
 * The cell does not forbid wrapping, so a tight table stays inside its
 * region. By default (`wrap="chip"`) the label stays on one line and the
 * chip drops under it. With `wrap="words"` the label's words wrap, the
 * arrow stays on the line of the last word and the chip goes under the
 * label, for long labels ("Views opened by clicking") in a table with many
 * columns.
 */
export function SortHeader<K extends string>({
  column,
  sort,
  onSort,
  kind = "text",
  chip,
  wrap = "chip",
  hint,
  className,
  children,
  ...th
}: HeaderProps & {
  column: K;
  sort: Sort<K> | null;
  onSort: (next: Sort<K>) => void;
  kind?: SortKind;
  /** Words for the chip when the column's order is not plain text, number or date. */
  chip?: (sort: Sort<K>) => string;
  wrap?: "chip" | "words";
  /**
   * What the column holds, as a hover hint on the sort button: the element
   * that takes focus, so it is also the button's description for a screen
   * reader and shows on focus in the "Always" hints setting.
   */
  hint?: string;
  className?: string;
  /** The header's label. Defaults to the column key. */
  children?: ReactNode;
}) {
  const active = sort?.column === column;
  const Arrow = !sort || !active ? ArrowUpDown : sort.direction === "asc" ? ArrowUp : ArrowDown;
  const words = wrap === "words";
  const label = children ?? column;
  const indicator =
    sort && active ? (
      <span
        key={`${sort.column}-${sort.direction}`}
        className={cn(
          "inline-flex items-center gap-0.5 whitespace-nowrap rounded-full bg-umich-blue px-1.5 py-px text-2xs font-semibold normal-case tracking-normal text-fg-inverse motion-safe:animate-sort-pop",
        )}
      >
        <Arrow className="h-3 w-3 shrink-0" aria-hidden />
        {chip ? chip(sort) : sortChip(kind, sort.direction)}
      </span>
    ) : (
      <Arrow
        className={cn(
          "h-3.5 w-3.5 shrink-0 opacity-40 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100",
          words && "ml-1 inline-block align-[-2px]",
        )}
        aria-hidden
      />
    );
  return (
    <th
      scope="col"
      aria-sort={sort ? ariaSort(active, sort.direction) : "none"}
      className={cn(
        "px-3 py-1.5 text-center font-semibold",
        active && "shadow-[inset_0_-3px_0_theme(colors.umich.blue)]",
        className,
      )}
      {...th}
    >
      <button
        type="button"
        title={hint}
        onClick={() => onSort(nextSort(sort, column, kind))}
        className={cn(
          "group inline-flex min-h-target rounded-xs px-1 text-sm font-semibold normal-case tracking-normal hover:bg-border/50 focus-visible:outline-none focus-visible:shadow-focus",
          // Words at the foot of the target, not its middle: with the cell
          // bottom-aligned, the last line of every label then sits on one
          // line, right over the column's data, however many lines each
          // label takes. The target keeps its full height (SC 2.5.5).
          words ? "items-end pb-1.5" : "items-center",
          !words && "flex-wrap justify-center gap-x-1.5 gap-y-0.5",
          "text-center",
          active ? "text-umich-blue" : "text-fg-muted",
        )}
      >
        {words ? (
          // The arrow follows the last word and never parts from it: an
          // arrow alone on a line of its own reads as a separate thing. The
          // chip is wider, so it has a line of its own under the label,
          // rather than widening the column it sorts.
          active ? (
            <span>
              {label}
              <span className="mt-0.5 flex justify-center">{indicator}</span>
            </span>
          ) : (
            <span>{withLastWord(label, indicator)}</span>
          )
        ) : (
          <>
            <span className="whitespace-nowrap">{label}</span>
            {indicator}
          </>
        )}
      </button>
    </th>
  );
}

/**
 * ``label`` with ``after`` kept on one line with its last word ("Images with
 * [text ⇅]"). A label that is not plain text is left as it is.
 */
function withLastWord(label: ReactNode, after: ReactNode): ReactNode {
  if (typeof label !== "string") {
    return (
      <>
        {label}
        {after}
      </>
    );
  }
  const cut = label.trimEnd().lastIndexOf(" ");
  return (
    <>
      {cut >= 0 && label.slice(0, cut + 1)}
      <span className="whitespace-nowrap">
        {label.slice(cut + 1)}
        {after}
      </span>
    </>
  );
}

/**
 * A column header that does not sort. Every heading, sorting or not, is
 * centred over its column, so a row of headings reads as one even line
 * whatever the widths of the columns under them.
 */
export function ColumnHeader({
  className,
  children,
  scope = "col",
  ...th
}: HeaderProps & {
  scope?: "col" | "colgroup";
  className?: string;
  children: ReactNode;
}) {
  return (
    <th
      scope={scope}
      className={cn("px-4 py-3 text-center font-semibold", className)}
      {...th}
    >
      {children}
    </th>
  );
}

/** The stripe for row `index` (counted across pages): every second row is shaded. */
export function rowBand(index: number): string {
  return index % 2 === 1 ? "bg-surface-subtle" : "bg-surface";
}

/**
 * A striped body row. A sticky row header takes the row's stripe with
 * `bg-inherit`, so it stays opaque while the table scrolls under it.
 */
export function Row({
  index,
  className,
  children,
  ...tr
}: HTMLAttributes<HTMLTableRowElement> & { index: number; children: ReactNode }) {
  return (
    <tr className={cn(rowBand(index), "border-t border-border", className)} {...tr}>
      {children}
    </tr>
  );
}

/** The cell that names its row. `sticky` pins it while a wide table scrolls. */
export function RowHeader({
  sticky = false,
  className,
  children,
  ...th
}: Omit<ThHTMLAttributes<HTMLTableCellElement>, "scope"> & { sticky?: boolean; children: ReactNode }) {
  return (
    <th
      scope="row"
      className={cn(
        "px-4 py-3.5 text-left align-middle font-semibold leading-6",
        sticky && "sticky left-0 z-[1] bg-inherit shadow-[inset_-1px_0_0_theme(colors.border.DEFAULT)]",
        className,
      )}
      {...th}
    >
      {children}
    </th>
  );
}

/**
 * A body cell. `numeric` sets it in tabular figures, on one line, centred
 * under its centred heading. Other cells stay left-aligned: running text
 * such as a title or an address reads best from a straight left edge.
 */
export function Cell({
  numeric = false,
  className,
  children,
  ...td
}: TdHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean; children?: ReactNode }) {
  return (
    <td
      className={cn(
        "px-4 py-3.5 align-middle leading-6",
        numeric && "whitespace-nowrap text-center tabular-nums",
        className,
      )}
      {...td}
    >
      {children}
    </td>
  );
}

/** What a table shows in place of rows when none match or none exist. */
export function TableEmpty({ children }: { children: ReactNode }) {
  return <p className="px-4 py-8 text-center text-sm text-fg-muted">{children}</p>;
}
