import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { dayKey, formatDay } from "../../lib/days";
import { cn } from "../../lib/cn";
import { Button } from "../ui";

/*
 * A date range group in a Filter menu (FilterMenu, a group with
 * `dateRange`): a From day and a To day, each in Month, Day and Year boxes,
 * and one "Apply dates" button. Either day can be left empty, so one group
 * gives "on or after", "on or before" and "between". First used by the
 * Documents tab's Creation date (the developer's requests, 2026-11-25: "the
 * specific month and date matters", then "you also need to allow
 * inbetween"; whole years were too coarse, a From day alone too narrow).
 *
 * Why this design:
 * - Each day is three labelled text boxes in its own fieldset ("From",
 *   "To") inside the group's fieldset ("Creation date"), so a screen reader
 *   names a box "Creation date, From, Month". This is the memorable-date
 *   pattern of the U.S. Web Design System
 *   (https://designsystem.digital.gov/components/memorable-date/) and the
 *   GOV.UK Design System's date input
 *   (https://design-system.service.gov.uk/components/date-input/). Month,
 *   Day, Year is the USWDS order and the order the app writes dates in
 *   ("April 24, 2026", the reader's locale); GOV.UK's Day, Month, Year is
 *   the British order and would have 4 5 2026 read two ways.
 * - One group with both ends and one button, not two groups with a button
 *   each: the two days are one choice, a range, and two Apply buttons in
 *   one menu would each apply half of it (one control, one job; W3C COGA,
 *   "Making Content Usable", https://www.w3.org/TR/coga-usable/,
 *   paraphrased).
 * - Month is a text box that takes a number or a month name ("4", "Apr",
 *   "April"). GOV.UK found many people type month names and that accepting
 *   them cut errors sharply (paraphrased). USWDS uses a dropdown for the
 *   month; rejected here because the app's dropdown (Select) opens its list
 *   inside the Filter panel, which scrolls, and three boxes of one kind are
 *   one way to fill in a day.
 * - type="text" with inputmode="numeric" for Day and Year, not
 *   type="number": both systems advise against number inputs (USWDS:
 *   "Use “text” instead of “number” inputs"). No maxlength, which cuts
 *   typing off without saying so; a wrong length gets an error instead.
 *   Focus never jumps to the next box on its own (USWDS: "Don’t
 *   auto-advance focus"), so a mistake is easy to go back and fix.
 * - It applies only when the reader presses "Apply dates" or Enter, unlike
 *   the Filter menu's boxes, which apply at once: a half-typed day ("2" as
 *   a year) would empty the table at every key. WCAG 2.2 SC 3.2.2 On Input,
 *   Level A.
 * - Errors follow GOV.UK's wording ("The From date must include a year",
 *   "must be a real date", "must be the same as or before") and its order:
 *   something missing first, then something that cannot be right. One error
 *   at a time, as real text under the hints, starting "Error:" as on the AI
 *   setup page. Only the boxes that are wrong are marked (aria-invalid) and
 *   point at it (aria-describedby), the group points at the hints and the
 *   error as GOV.UK's markup does, and focus moves to the first wrong box.
 *   SC 3.3.1 Error Identification (Level A), SC 3.3.3 Error Suggestion
 *   (Level AA), techniques ARIA21 and G85.
 * - A polite status line under the buttons says what is applied, so
 *   pressing "Apply dates" is confirmed without moving focus (SC 4.1.3
 *   Status Messages, Level AA). "Clear dates" appears once a date is
 *   applied and puts focus back in the first Month box when it goes.
 *
 * A new component, not an extension of NumberField (newScan/NumberField):
 * that is one type="number" box, which this pattern rules out, and it has
 * no group, no month names and no date check.
 */

const MONTHS = [
  "january",
  "february",
  "march",
  "april",
  "may",
  "june",
  "july",
  "august",
  "september",
  "october",
  "november",
  "december",
] as const;

type Side = "from" | "to";
type Part = "month" | "day" | "year";
type Box = `${Side}.${Part}`;
const SIDES: readonly Side[] = ["from", "to"];
const PARTS: readonly Part[] = ["month", "day", "year"];
type Day = Record<Part, string>;
type Draft = Record<Side, Day>;
const EMPTY: Day = { month: "", day: "", year: "" };
const SIDE_LABEL: Record<Side, string> = { from: "From", to: "To" };
const PART_LABEL: Record<Part, string> = { month: "Month", day: "Day", year: "Year" };
const WIDTHS: Record<Part, string> = { month: "w-28", day: "w-16", year: "w-20" };

/** A range as kept in a URL: "2018-07-17..2020-12-31", either end may be empty. */
export type DateRange = { from: string; to: string };

/** The real days in "from..to"; an end that is not a real day is dropped. */
export function parseDateRange(value: string | null | undefined): DateRange {
  const [from = "", to = ""] = (value ?? "").split("..");
  return { from: dayKey(from) ?? "", to: dayKey(to) ?? "" };
}

/** "from..to", or "" when neither end is set. */
export function dateRangeValue({ from, to }: DateRange): string {
  return from || to ? `${from}..${to}` : "";
}

/** "July 17, 2018 to December 31, 2020", "on or after July 17, 2018"… */
export function describeDateRange(value: string): string {
  const { from, to } = parseDateRange(value);
  const [start, end] = [formatDay(from), formatDay(to)];
  if (start && end) return `${start} to ${end}`;
  if (start) return `on or after ${start}`;
  if (end) return `on or before ${end}`;
  return "";
}

/** 4 from "4", "04", "Apr", "apr." or "April"; null when it is not a month. */
export function parseMonth(raw: string): number | null {
  const text = raw.trim().toLowerCase().replace(/\.$/, "");
  if (/^\d{1,2}$/.test(text)) {
    const month = Number(text);
    return month >= 1 && month <= 12 ? month : null;
  }
  if (text.length < 3) return null;
  const index = MONTHS.findIndex((name) => name.startsWith(text));
  return index >= 0 ? index + 1 : null;
}

type Problem = { error: string; boxes: Box[] };

/** One side's day as "YYYY-MM-DD", "" when left empty, or what is wrong with it. */
function readDay(side: Side, typed: Day): { day: string } | Problem {
  const name = `The ${SIDE_LABEL[side]} date`;
  const boxes = (parts: readonly Part[]) => parts.map((part) => `${side}.${part}` as Box);
  const missing = PARTS.filter((part) => !typed[part].trim());
  if (missing.length === PARTS.length) return { day: "" };
  if (missing.length) {
    return { error: `${name} must include a ${missing.join(" and a ")}.`, boxes: boxes(missing) };
  }
  const month = parseMonth(typed.month);
  if (month === null) {
    return {
      error: `${name} must have a month from 1 to 12 or a month name, for example 4 or April.`,
      boxes: boxes(["month"]),
    };
  }
  const day = typed.day.trim();
  if (!/^\d{1,2}$/.test(day)) {
    return { error: `${name} must have a day that is a number, for example 24.`, boxes: boxes(["day"]) };
  }
  const year = typed.year.trim();
  if (!/^\d{4}$/.test(year)) {
    return { error: `${name} must have a year with 4 numbers, for example 2026.`, boxes: boxes(["year"]) };
  }
  const key = dayKey(`${year}-${String(month).padStart(2, "0")}-${day.padStart(2, "0")}`);
  if (!key) return { error: `${name} must be a real date, for example April 24 2026.`, boxes: boxes(PARTS) };
  return { day: key };
}

/**
 * The typed range, or the one error to show and the boxes it is about. One
 * error at a time, the most basic first (GOV.UK), From before To.
 */
export function readDateRange(draft: Draft): { range: DateRange } | Problem {
  const from = readDay("from", draft.from);
  if ("error" in from) return from;
  const to = readDay("to", draft.to);
  if ("error" in to) return to;
  if (!from.day && !to.day) {
    return {
      error: "Enter a From date, a To date or both, for example April 24 2026.",
      boxes: ["from.month", "from.day", "from.year"],
    };
  }
  if (from.day && to.day && from.day > to.day) {
    return {
      error: `The From date must be the same as or before the To date, ${formatDay(to.day)}.`,
      boxes: ["from.month", "from.day", "from.year"],
    };
  }
  return { range: { from: from.day, to: to.day } };
}

/** The boxes as they show an applied range. */
function draftOf(value: string): Draft {
  const range = parseDateRange(value);
  const day = (key: string): Day => {
    if (!key) return { ...EMPTY };
    const [year, month, date] = key.split("-");
    return { month: String(Number(month)), day: String(Number(date)), year };
  };
  return { from: day(range.from), to: day(range.to) };
}

export default function FilterDate({
  label,
  hint,
  value,
  onApply,
}: {
  /** The group's legend, "Creation date". */
  label: string;
  /** The group's own sentence, read with it (FilterGroup's `hint`). */
  hint?: string;
  /** The applied range, "from..to" (DateRange); "" when none. */
  value: string;
  /** Called with "from..to", or "" to clear both days. */
  onApply: (value: string) => void;
}) {
  const id = useId();
  const [draft, setDraft] = useState<Draft>(() => draftOf(value));
  const [problem, setProblem] = useState<Problem | null>(null);
  const [cleared, setCleared] = useState(false);
  const inputs = useRef<Partial<Record<Box, HTMLInputElement | null>>>({});
  // A value set from outside (Clear all filters, a link) replaces what was
  // typed; the value this group just applied does not.
  const applied = useRef(value);
  useEffect(() => {
    if (value === applied.current) return;
    applied.current = value;
    setDraft(draftOf(value));
    setProblem(null);
  }, [value]);

  const hintId = `${id}-hint`;
  const exampleId = `${id}-example`;
  const errorId = `${id}-error`;
  const shown = describeDateRange(value);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const result = readDateRange(draft);
    if ("error" in result) {
      setProblem(result);
      inputs.current[result.boxes[0]]?.focus();
      return;
    }
    setProblem(null);
    setCleared(false);
    const next = dateRangeValue(result.range);
    applied.current = next;
    onApply(next);
  };
  const clear = () => {
    setDraft({ from: { ...EMPTY }, to: { ...EMPTY } });
    setProblem(null);
    setCleared(true);
    applied.current = "";
    onApply("");
    inputs.current["from.month"]?.focus();
  };

  return (
    <form noValidate onSubmit={submit} className="mb-3 border-b border-border pb-3 last-of-type:mb-0">
      <fieldset
        aria-describedby={[hint ? hintId : null, exampleId, problem ? errorId : null].filter(Boolean).join(" ")}
      >
        <legend className="mb-1 px-2 text-xs font-semibold text-fg">{label}</legend>
        {hint && (
          <p id={hintId} className="mb-1 px-2 text-xs text-fg-muted">
            {hint}
          </p>
        )}
        <p id={exampleId} className="mb-1 px-2 text-xs text-fg-muted">
          Fill in From, To or both. Both days are included. For example, April 24 2026. Type the
          month as a number or a name.
        </p>
        {problem && (
          <p id={errorId} className="mb-1 px-2 text-sm font-semibold text-sev-critical">
            {`Error: ${problem.error}`}
          </p>
        )}
        {SIDES.map((side) => (
          <fieldset key={side} className="px-2 pt-2">
            <legend className="text-sm font-semibold text-fg">{SIDE_LABEL[side]}</legend>
            <div className="flex flex-wrap items-end gap-3 pt-1">
              {PARTS.map((part) => {
                const box: Box = `${side}.${part}`;
                const wrong = problem?.boxes.includes(box);
                return (
                  <div key={part} className="flex flex-col gap-1">
                    <label htmlFor={`${id}-${side}-${part}`} className="text-sm text-fg">
                      {PART_LABEL[part]}
                    </label>
                    <input
                      ref={(element) => {
                        inputs.current[box] = element;
                      }}
                      id={`${id}-${side}-${part}`}
                      name={`${side}-${part}`}
                      type="text"
                      inputMode={part === "month" ? "text" : "numeric"}
                      autoComplete="off"
                      spellCheck={false}
                      value={draft[side][part]}
                      aria-invalid={wrong || undefined}
                      aria-describedby={wrong ? errorId : undefined}
                      onChange={(event) => {
                        const text = event.target.value;
                        setDraft((current) => ({ ...current, [side]: { ...current[side], [part]: text } }));
                      }}
                      className={cn(
                        "min-h-target rounded-xs border bg-surface px-3 py-2 text-base text-fg focus:border-umich-blue focus:outline-none focus-visible:shadow-focus",
                        wrong ? "border-2 border-sev-critical" : "border-border-strong",
                        WIDTHS[part],
                      )}
                    />
                  </div>
                );
              })}
            </div>
          </fieldset>
        ))}
      </fieldset>
      <div className="flex flex-wrap items-center gap-2 px-2 pt-3">
        <Button type="submit">Apply dates</Button>
        {value && (
          <Button type="button" variant="ghost" onClick={clear}>
            Clear dates
          </Button>
        )}
      </div>
      <p role="status" className="px-2 pt-1 text-sm text-fg-muted">
        {shown ? `Applied: ${label.toLowerCase()} ${shown}.` : cleared ? "No dates are applied." : ""}
      </p>
    </form>
  );
}
