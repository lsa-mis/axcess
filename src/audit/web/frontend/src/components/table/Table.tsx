import {
  Fragment,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type HTMLAttributes,
  type ReactNode,
  type Ref,
  type RefObject,
  type TdHTMLAttributes,
  type ThHTMLAttributes,
} from "react";
import { ArrowDown, ArrowRight, ArrowUp, ArrowUpDown, Search } from "lucide-react";
import { cn } from "../../lib/cn";
import { ariaSort, nextSort, sortChip, type Sort, type SortKind } from "./sort";

/*
 * The one table design, laid out top to bottom the way every table reads:
 *
 *   TableBar       search and the Filter menu (./FilterMenu) on the left,
 *                  the pager (../TablePagination) on the right, and the
 *                  active filters written out beneath
 *   TableStatus    the polite line that says how the rows are ordered
 *   TableRegion    the keyboard-scrollable region
 *     Table, TableHead, SortHeader / ColumnHeader
 *     Row, RowHeader, Cell    striped rows, one target tall
 *   TableFoot      the pager again, under the last row (../TablePagination,
 *                  `place="end"`), so a reader who has read to the end
 *                  turns the page there
 *
 * A paged table wraps everything from TableBar down in `PagedTable`
 * (../TablePagination), which draws the pager in TableBar and in TableFoot
 * as one pair, so no table can have one without the other.
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
 *
 * The left group asks for 20rem only when it holds a search box, the room
 * the box needs to be usable before the pager wraps under it. Without one
 * (the Documents tab: only "Filter documents") it asks for its controls'
 * own width. A fixed 20rem there pushed a wide pager (909 documents, 91
 * pages) onto a second line under a lone button at 1440px, leaving the
 * bar's right half empty on the first line (the developer's report,
 * 2026-11-16). Rejected: a prop on TableBar for "no search", which every
 * caller would have to remember; the bar can see whether it has a search
 * box itself (CSS ``:has()``). The pager still wraps under the controls
 * when the row is too narrow for both, so nothing scrolls sideways at
 * 320px (SC 1.4.10 Reflow, Level AA).
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
        {children && (
          <div className="flex min-w-0 flex-[1_1_auto] flex-wrap items-center gap-2 has-[[type=search]]:basis-80">
            {children}
          </div>
        )}
        {pager}
      </div>
      {footer}
    </div>
  );
}

/**
 * The bar under a table's last row, styled like `TableBar` above it, with
 * the pager on the right where it sits in the top bar. It holds only the
 * end-of-table pager (`TablePagination` with `place="end"` draws it, and
 * `PagedTable` draws that with the top pager), so it is there exactly when
 * the top pager is: on a table with more than one page. Search and
 * filters stay in the top bar only; they change what the table holds,
 * which a reader decides before reading it, not after.
 */
export function TableFoot({ children }: { children: ReactNode }) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-end border-t border-border bg-surface-subtle px-4 py-3",
        CARD_EDGE,
      )}
    >
      {children}
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
 *
 * `announce={false}` drops the live region, for a table that shows this
 * line only some of the time: a live region added to the page with its words
 * already in it is not read out, so such a table keeps its own live region
 * mounted all the time instead (the Issues table, routes/Issues.tsx).
 */
export function TableStatus({
  children,
  actions,
  announce = true,
  className,
}: {
  children: ReactNode;
  actions?: ReactNode;
  announce?: boolean;
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
      {announce ? (
        <p role="status" aria-live="polite">
          {children}
        </p>
      ) : (
        <p>{children}</p>
      )}
      {actions}
    </div>
  );
}

/**
 * The scroll region around a table. Keyboard users need focus on it to
 * scroll a wide table sideways, so it takes focus and carries a name. (It
 * used to hold a paged table at its tallest page's height; see usePagedRows
 * for why that was dropped.)
 */
export function TableRegion({
  label,
  busy,
  regionRef,
  className,
  children,
}: {
  label: string;
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
  // Whether the table is wider than the region, so the region scrolls
  // sideways. Measured whenever either changes size.
  const [scrolls, setScrolls] = useState(false);
  // The table's full width, for the top bar's track (see below).
  const [scrollWidth, setScrollWidth] = useState(0);
  const [node, setNode] = useState<HTMLDivElement | null>(null);
  const [top, setTop] = useState<HTMLDivElement | null>(null);
  const setRef = useCallback(
    (element: HTMLDivElement | null) => {
      setNode(element);
      if (typeof regionRef === "function") regionRef(element);
      else if (regionRef) (regionRef as { current: HTMLDivElement | null }).current = element;
    },
    [regionRef],
  );
  useEffect(() => {
    if (!node) return;
    const measure = () => {
      setScrolls(node.scrollWidth > node.clientWidth + 1);
      setScrollWidth(node.scrollWidth);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    for (const child of Array.from(node.children)) observer.observe(child);
    // Keyboard focus only: bring the table's top back into view when the
    // browser's centring left it above the top bar (see the comment below).
    const onFocus = (event: FocusEvent) => {
      if (event.target !== node || !node.matches(":focus-visible")) return;
      if (node.getBoundingClientRect().top < 88) node.scrollIntoView({ block: "start", behavior: "instant" });
    };
    node.addEventListener("focus", onFocus);
    return () => {
      observer.disconnect();
      node.removeEventListener("focus", onFocus);
    };
  }, [node]);
  // The top bar and the region scroll together: moving either moves the
  // other to the same place. Equal positions end the back-and-forth.
  useEffect(() => {
    if (!node || !top) return;
    top.scrollLeft = node.scrollLeft;
    const follow = (from: HTMLElement, to: HTMLElement) => () => {
      if (Math.abs(to.scrollLeft - from.scrollLeft) >= 1) to.scrollLeft = from.scrollLeft;
    };
    const fromRegion = follow(node, top);
    const fromTop = follow(top, node);
    // A click on the bar would focus it (a scrolling box takes focus), and
    // focus must never rest on something hidden from screen readers (axe
    // aria-hidden-focus). It goes to the region instead, the one keyboard
    // control for this scrolling, so the arrow keys carry on from the click.
    const toRegion = () => node.focus({ preventScroll: true });
    node.addEventListener("scroll", fromRegion, { passive: true });
    top.addEventListener("scroll", fromTop, { passive: true });
    top.addEventListener("focus", toRegion);
    return () => {
      node.removeEventListener("scroll", fromRegion);
      top.removeEventListener("scroll", fromTop);
      top.removeEventListener("focus", toRegion);
    };
  }, [node, top]);
  return (
    <>
      {/* A scroll bar over a table that is wider than its region, at the
          top, so it shows as soon as the table does that the table scrolls
          sideways, and it can be dragged without first scrolling down to
          the region's own bar under the last row (the developer's request,
          2026-11-16). Shown only while the table scrolls. It is the
          browser's own scroll bar, on a strip as wide as the region with a
          track as wide as the table, kept in step with the region (the
          effect above), and styled thin and always visible
          (.ax-scrollbar in styles.css), so it does not fade away as
          overlay scroll bars do on a Mac. Its target size, contrast and
          forced-colours behaviour are set out there.
          It is for the pointer only, as a browser's own scroll bar is: a
          scroll bar is never a Tab stop. The keyboard way to scroll is to
          focus the scrolling box and use the arrow keys, and the region
          below is that box (SC 2.1.1 Keyboard, Level A; axe
          scrollable-region-focusable). So the bar is out of the Tab order
          (tabIndex -1; without it, recent Chromium makes any scrolling box
          a Tab stop), hidden from screen readers (aria-hidden: a second
          thing to scroll, read out, would be two controls for one job, W3C
          COGA, "Making Content Usable"), and a click on it sends focus to
          the region (the effect above), so focus never rests on hidden
          content. It has no scrollbar role, as before: a role="scrollbar"
          widget (WAI-ARIA APG) would need its own focus, value and arrow
          keys, all of which the region already gives. Rejected: a drawn bar with a draggable thumb, which
          would be a custom widget, and a "Scroll for more columns" note,
          which tells but does not let the reader scroll. */}
      {scrolls && (
        <div
          ref={setTop}
          aria-hidden="true"
          tabIndex={-1}
          className={cn("ax-scrollbar overflow-x-auto overflow-y-hidden border-b border-border", CARD_EDGE)}
        >
          <div style={{ width: scrollWidth, height: 1 }} />
        </div>
      )}
    <div
      ref={setRef}
      role="region"
      aria-label={label}
      aria-busy={busy || undefined}
      // In the tab order only while it scrolls sideways. A keyboard user needs
      // focus on a region to scroll it (axe scrollable-region-focusable; WCAG
      // 2.2 SC 2.1.1 Keyboard), but a table that fits had a tab stop that did
      // nothing, one more for every table on the way to its links. It stays
      // focusable from code (-1): a table takes focus when the control that
      // reordered it goes away ("Back to recommended order"), so focus is
      // not lost to the page.
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
      tabIndex={scrolls ? 0 : -1}
      // A browser brings a focused element into view by centring it when it
      // is off the screen, so tabbing to a table taller than the window
      // dropped the reader in its middle, away from the header row that
      // names the columns: a jump the reader did not ask for (SC 3.2.1 On
      // Focus, Level A, is about that kind of surprise, paraphrased). On
      // keyboard focus, when the table's top has gone above the top bar,
      // its top is brought back into view, just under the bar (the page's
      // scroll-padding-top in styles.css leaves room for the 72px top bar
      // and 16px more); see the effect above.
      // A mouse click inside it moves nothing.
      // `relative`: screen-reader-only text in a cell is positioned
      // absolutely (`sr-only`). Without a positioned region it was placed
      // against the page, outside this clip, and on a phone widened the whole
      // page (615px at 320), so it scrolled sideways (SC 1.4.10 Reflow).
      className={cn(
        "relative overflow-x-auto focus:outline-none focus-visible:shadow-focus",
        CARD_EDGE,
        className,
      )}
    >
      {children}
    </div>
    </>
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
  ruled = true,
  className,
  children,
}: {
  caption: ReactNode;
  captionClassName?: string;
  /**
   * A thin line between columns, top to bottom, so a value can be followed
   * up to its column's header. On for every table since 2026-11-02, the
   * developer's call: Reports had them first (user testing, 2026-10-28,
   * where a site's scans are compared by their numbers), and the other
   * tables without them looked like a different kind of table. One pattern
   * for one kind of thing (W3C COGA, "Making Content Usable",
   * https://www.w3.org/TR/coga-usable/; SC 3.2.4 Consistent Identification,
   * Level AA, in spirit). Off only for a table that is not read down its
   * columns at all (`ruled={false}`); none is today. Until then they were off
   * by default, on the view that most tables are read a row at a time and
   * the stripes guide the eye across; the lines do not get in the way of
   * that, and they help reading down.
   *
   * The line is an inset shadow on each cell's right, not a border. The
   * sticky row header draws its own edge the same way (see RowHeader), and
   * a border beside it doubled the line; a collapsed border also stays put
   * while a sticky cell scrolls, and a shadow moves with it.
   */
  ruled?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <table
      className={cn(
        "w-full text-sm",
        ruled && "[&_:is(th,td):not(:last-child)]:shadow-[inset_-1px_0_0_theme(colors.border.DEFAULT)]",
        className,
      )}
    >
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
  align,
  chip,
  wrap = "chip",
  hint,
  help,
  className,
  children,
  ...th
}: HeaderProps & {
  column: K;
  sort: Sort<K> | null;
  onSort: (next: Sort<K>) => void;
  kind?: SortKind;
  /**
   * Which side the heading sits on: its column's content's side (see
   * ``ColumnHeader``). Defaults from ``kind``: right for a number column,
   * left otherwise. Set it for a column that sorts by a number but shows
   * words (Issues' Priority sorts by score and shows High, Medium, Low).
   */
  align?: "left" | "right";
  /** Words for the chip when the column's order is not plain text, number or date. */
  chip?: (sort: Sort<K>) => string;
  wrap?: "chip" | "words";
  /**
   * What the column holds, as a hover hint on the sort button: the element
   * that takes focus, so it is also the button's description for a screen
   * reader and shows on focus in the "Always" hints setting.
   */
  hint?: string;
  /**
   * A ``HelpTip`` ("?") after the sort button, for a column whose values
   * need explaining (Issues' "How sure"). Beside the button, not inside it:
   * one control sorts and the other explains, so neither does two things.
   * In the middle of the label's line, on the column's side, like the label.
   *
   * With a "?", a label that wraps keeps the "?" beside its words: the sort
   * button is shrunk to its longest line (``useFitToLines``). A wrapped
   * button is otherwise as wide as the space it was given, not as its text,
   * so the "?" after it floated apart from the words it explains
   * ("Accessibility / problems? ⇅ … ?", the developer's screenshot,
   * 2026-11-16). Proximity says what belongs together (W3C COGA, "Making
   * Content Usable"). Here, not on one header, so every header with a "?"
   * gets it; a label on one line looks the same either way. Rejected:
   * aligning the lines to the "?" (it moved the heading off its column's
   * side, the rule above) and keeping such a label on one line (it widened
   * the column until the table scrolled sideways at 1280px).
   */
  help?: ReactNode;
  className?: string;
  /** The header's label. Defaults to the column key. */
  children?: ReactNode;
}) {
  const active = sort?.column === column;
  const right = (align ?? (kind === "number" ? "right" : "left")) === "right";
  const button = useRef<HTMLButtonElement>(null);
  useFitToLines(button, help != null, `${active}-${sort?.direction}-${typeof children === "string" ? children : column}`);
  const Arrow = !sort || !active ? ArrowUpDown : sort.direction === "asc" ? ArrowUp : ArrowDown;
  const words = wrap === "words";
  const label = children ?? column;
  const indicator =
    sort && active ? (
      <span
        key={`${sort.column}-${sort.direction}`}
        data-sort-mark
        className={cn(
          "inline-flex items-center gap-0.5 whitespace-nowrap rounded-full bg-umich-blue px-1.5 py-px text-2xs font-semibold normal-case tracking-normal text-fg-inverse motion-safe:animate-sort-pop",
        )}
      >
        <Arrow className="h-3 w-3 shrink-0" aria-hidden />
        {withDrawnArrows(chip ? chip(sort) : sortChip(kind, sort.direction))}
      </span>
    ) : (
      <Arrow
        className={cn(
          "h-3.5 w-3.5 shrink-0 opacity-40 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100",
          words && (right ? "inline-block" : "ml-1 inline-block align-[-2px]"),
        )}
        aria-hidden
      />
    );
  return (
    <th
      scope="col"
      aria-sort={sort ? ariaSort(active, sort.direction) : "none"}
      className={cn(
        // 16px at the sides, as the body cells (Cell, RowHeader), with the
        // sort button pulled out by its own 4px padding (-mx-1 below), so
        // the heading's words start on the same line as the words under it.
        // A table that pads its cells otherwise (Issues: px-1.5) gives its
        // headers the same class, and the two still line up. They were 12px
        // plus the button's 4px, which matched only the default: with any
        // other padding the heading sat 4px in from its column's words, and
        // further where a row header kept the default (the developer's
        // report, 2026-11-16: "Issue type" was not left-aligned with the
        // issue types under it).
        "px-4 py-1.5 font-semibold",
        right ? "text-right" : "text-left",
        active && "shadow-[inset_0_-3px_0_theme(colors.umich.blue)]",
        className,
      )}
      {...th}
    >
      {help ? (
        <span className={cn("inline-flex items-center", right ? "justify-end" : "justify-start")}>
          {sortButton()}
          {help}
        </span>
      ) : (
        sortButton()
      )}
    </th>
  );

  function sortButton() {
    return (
      <button
        ref={button}
        type="button"
        title={hint}
        onClick={() => onSort(nextSort(sort, column, kind))}
        className={cn(
          // -mx-1: its padding (the hover fill and focus ring's room) sits
          // outside the words, not in front of them (see the cell above).
          "group -mx-1 inline-flex min-h-target min-w-target rounded-xs px-1 text-sm font-semibold normal-case tracking-normal hover:bg-border/50 focus-visible:outline-none focus-visible:shadow-focus",
          right ? "justify-end text-right" : "justify-start text-left",
          // Words in the middle of the target, so every label sits in the
          // middle of the header row (the developer's request, 2026-11-16).
          // They were at its foot, to keep the last line of a two-line label
          // level with its one-line neighbours, but a one-line label then
          // sat visibly low. The target keeps its full height (SC 2.5.5).
          "items-center",
          !words && "flex-wrap gap-x-1.5 gap-y-0.5",
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
              <span className={cn("mt-0.5 flex", right ? "justify-end" : "justify-start")}>{indicator}</span>
            </span>
          ) : right ? (
            // A right-aligned label that wraps ("Issue / occurrences"): the
            // lines are right-aligned to each other and the arrow stands in
            // its own column after them, centred on the label. With the
            // arrow after the last word, the last line was pushed left of the
            // others and "Issue" no longer ended where "occurrences" did
            // (the developer's screenshots, 2026-11-16). Rejected: the arrow
            // inline after the last word, the left-aligned columns' way,
            // which is right where the lines start on the left. Proximity
            // and alignment: W3C COGA, "Making Content Usable"
            // (https://www.w3.org/TR/coga-usable/); the sort mark is still
            // inside the one button (SC 2.5.3 Label in Name, Level A).
            <span className="inline-flex items-center gap-1">
              <span className="text-right">{label}</span>
              {indicator}
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
    );
  }
}

/**
 * Shrinks a sort button whose label wrapped to the width of its longest
 * line, so a "?" after it sits beside the words (see SortHeader's ``help``).
 * CSS has no width that fits wrapped lines: a box that wraps is as wide as
 * the space it was given. So this measures the label's text and its sort
 * mark (arrow or chip) after layout and caps the button at that width, and
 * measures again whenever the header cell changes size (a window resized,
 * a column re-laid out). Lines never change: they already fit inside it.
 * A cap (``max-width``), not a ``width``: a set width would also be the
 * narrowest the column could get, where a cap leaves that at the label's
 * longest word, as without this step.
 * Off without a "?". ``key`` changes when the button's content does.
 */
function useFitToLines(button: RefObject<HTMLButtonElement | null>, enabled: boolean, key: string) {
  useLayoutEffect(() => {
    const el = button.current;
    if (!enabled || !el) return;
    const fit = () => {
      el.style.maxWidth = "";
      const rects: DOMRect[] = [];
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      const range = document.createRange();
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (!node.textContent?.trim()) continue;
        range.selectNodeContents(node);
        rects.push(...Array.from(range.getClientRects()));
      }
      el.querySelectorAll("svg, [data-sort-mark]").forEach((mark) => rects.push(mark.getBoundingClientRect()));
      const shown = rects.filter((rect) => rect.width > 0);
      if (shown.length === 0) return;
      const style = getComputedStyle(el);
      const needed = Math.ceil(
        Math.max(...shown.map((rect) => rect.right)) -
          Math.min(...shown.map((rect) => rect.left)) +
          parseFloat(style.paddingLeft) +
          parseFloat(style.paddingRight),
      );
      if (needed < el.getBoundingClientRect().width - 1) el.style.maxWidth = `${needed}px`;
    };
    fit();
    const cell = el.closest("th");
    if (!cell || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(fit);
    observer.observe(cell);
    return () => {
      observer.disconnect();
      el.style.maxWidth = "";
    };
  }, [button, enabled, key]);
}

/**
 * A sort chip's words with each "→" drawn as an icon ("high → low").
 *
 * The app's font has no arrows, so a typed "→" came from whatever font the
 * computer had, and took a different width on each one: the Issues table
 * fitted 1280px here and was 13px too wide in CI with a column sorted
 * (test_issue_table_fits_the_default_desktop_width, 2026-11-16). The icon is
 * one width everywhere, like the chip's own direction arrow. The "→" stays
 * in the text, visually hidden, so the button's name and text are unchanged.
 */
function withDrawnArrows(words: string): ReactNode {
  const parts = words.split("→");
  if (parts.length === 1) return words;
  return parts.map((part, index) => (
    <Fragment key={index}>
      {index > 0 && (
        <>
          <ArrowRight className="h-2.5 w-2.5 shrink-0" aria-hidden />
          <span className="sr-only">→</span>
        </>
      )}
      {part}
    </Fragment>
  ));
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
 * A column header that does not sort.
 *
 * Every heading, sorting or not, sits on the side its column's content
 * does: left over words, links and tags, right over numbers (``numeric``
 * here, ``Cell numeric`` under it). The developer's rule, 2026-11-16,
 * replacing centred headings (e905267, 2026-09-26), which floated away
 * from the left edge of the text under them, more so in wide columns, so a
 * reader using screen magnification, or anyone tracking a dense table,
 * could lose which heading went with which column (W3C COGA, "Making
 * Content Usable", https://www.w3.org/TR/coga-usable/: keep related things
 * visibly together). Numbers sit right so they line up by place value.
 * The GOV.UK Design System, the U.S. Web Design System and Material align
 * headings with their data the same way (paraphrased). WCAG has no
 * criterion on it; a screen reader is unaffected, since it reads
 * ``th``/``scope``. tests/ui/test_table_alignment.py checks every screen.
 */
export function ColumnHeader({
  className,
  children,
  scope = "col",
  numeric = false,
  ...th
}: HeaderProps & {
  scope?: "col" | "colgroup";
  className?: string;
  /** The column holds numbers: the heading sits right, over them. */
  numeric?: boolean;
  children: ReactNode;
}) {
  return (
    <th
      scope={scope}
      className={cn("px-4 py-3 font-semibold", numeric ? "text-right" : "text-left", className)}
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
 * A body cell. `numeric` sets it in tabular figures, on one line, on the
 * right, so numbers line up by place value under their right-aligned
 * heading. Other cells are left-aligned: running text such as a title or an
 * address reads best from a straight left edge (see ``ColumnHeader``).
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
        numeric && "whitespace-nowrap text-right tabular-nums",
        className,
      )}
      {...td}
    >
      {children}
    </td>
  );
}

/**
 * What a table shows in place of rows when none match or none exist.
 *
 * Centred in a column about 72 characters wide (52ch, the measure the
 * report's short paragraphs use), not the card's full width. An empty table
 * often says why it is empty and where to look next, in two or three
 * sentences (Issues: "That does not mean the site meets WCAG… See “What was
 * checked”, below this table."); across a 1280px card those ran to about 150
 * characters a line. SC 1.4.8 Visual Presentation (Level AAA) asks for no
 * more than 80. Rejected: keeping each message to one short sentence, which
 * is how Documents worked around it and which pushed the caveat out of the
 * empty table. A one-line message looks the same as before.
 */
export function TableEmpty({ children }: { children: ReactNode }) {
  return <p className="mx-auto max-w-[52ch] px-4 py-8 text-center text-sm text-fg-muted">{children}</p>;
}
