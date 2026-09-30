import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, ListFilter } from "lucide-react";
import { cn } from "../../lib/cn";

/*
 * One Filter control per table. Every way a table can be narrowed (Level,
 * Type, Finding type, Change…) is a group inside it, so the bar over the
 * table stays one row however many filters a table has.
 *
 * It is a disclosure, not an ARIA menu: a button with `aria-expanded` that
 * shows a panel of native form controls right after it in the tab order. A
 * fieldset names each group. A `multiple` group is a set of checkboxes, so
 * several values can be on at once (Level A and Level AA); a group whose
 * data can only take one value is a set of radios, and arrow keys move
 * within it as radios always do. A choice applies at once. Escape, Done, a
 * press outside, or focus moving out closes the panel. Escape and Done
 * return focus to the button.
 * What is filtered is also written out under the bar (`ActiveFilters`), so
 * the state never lives only in the button.
 */

export type FilterOption = { value: string; label: string; count?: number };

export type FilterGroup = {
  /** Where the choice is kept: the URL parameter or state field. */
  key: string;
  /** The group's name, "Level". */
  label: string;
  /**
   * What is chosen; "" means the group does not narrow the table. A
   * `multiple` group keeps its checked values comma-separated, in option
   * order ("A,AA"), the form the URL parameters take.
   */
  value: string;
  /**
   * A radio group leads with `{ value: "", label: "All" }` so it can be
   * undone on its own. A `multiple` group needs no "All": nothing checked is
   * all, and an option with value "" is skipped.
   */
  options: readonly FilterOption[];
  /** Checkboxes, several at once. Only where the data can take a list. */
  multiple?: boolean;
};

/** A group's value as a list: "A,AA" → ["A", "AA"]; "" → []. */
export function splitFilter(value: string): string[] {
  return value ? value.split(",").filter(Boolean) : [];
}

/** The checked values after toggling `option`, in the group's option order. */
function toggled(group: FilterGroup, current: string, option: string): string {
  const on = new Set(splitFilter(current));
  if (on.has(option)) on.delete(option);
  else on.add(option);
  return group.options
    .map((candidate) => candidate.value)
    .filter((value) => value && on.has(value))
    .join(",");
}

export function FilterMenu({
  groups,
  onChange,
  onReset,
  label = "Filter",
}: {
  groups: readonly FilterGroup[];
  onChange: (key: string, value: string) => void;
  /**
   * Sets every group back to "All" in ONE update. Not a loop of `onChange`:
   * react-router's `setSearchParams` starts each call in an event from the
   * same query string, so a second call puts back what the first removed.
   */
  onReset: () => void;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const button = useRef<HTMLButtonElement>(null);
  const wrapper = useRef<HTMLDivElement>(null);
  // The choice as pressed, until the table's own state catches up. A table
  // that keeps its filters in the URL hears about the change a moment after
  // the click; without this the radio would flip back to unchecked in
  // between, and a screen reader could announce "not checked".
  const [pending, setPending] = useState<Record<string, { value: string; from: string }>>({});
  // Once any group's real value moves, the pressed choices have landed (or
  // been overtaken, say by a stat card); forget them.
  const signature = groups.map((group) => `${group.key}=${group.value}`).join("&");
  const [seen, setSeen] = useState(signature);
  if (seen !== signature) {
    setSeen(signature);
    setPending({});
  }
  const valueOf = (group: FilterGroup) => {
    const choice = pending[group.key];
    return choice && choice.from === group.value ? choice.value : group.value;
  };
  const choose = (group: FilterGroup, value: string) => {
    setPending((current) => ({ ...current, [group.key]: { value, from: group.value } }));
    onChange(group.key, value);
  };
  const active = groups.filter((group) => valueOf(group)).length;

  // While open: a press elsewhere or focus moving elsewhere closes the
  // panel; Escape closes it and returns focus to the button.
  useEffect(() => {
    if (!open) return;
    const outside = (target: EventTarget | null) => !wrapper.current?.contains(target as Node | null);
    const onPointer = (event: PointerEvent) => {
      if (outside(event.target)) setOpen(false);
    };
    const onFocus = (event: FocusEvent) => {
      // Pressing an option's text (not its box) moves focus to the nearest
      // focusable ancestor, the page's <main>, before the click lands. That
      // is not focus leaving the menu; closing on it swallowed the click.
      const target = event.target as Node | null;
      if (target?.contains(wrapper.current)) return;
      if (outside(target)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setOpen(false);
      button.current?.focus();
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("focusin", onFocus);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("focusin", onFocus);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const close = () => {
    setOpen(false);
    button.current?.focus();
  };

  return (
    <div ref={wrapper} className="relative">
      <button
        ref={button}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
        className={cn(
          "inline-flex min-h-target items-center gap-2 rounded-xs border px-3 text-sm font-semibold focus-visible:outline-none focus-visible:shadow-focus",
          active
            ? "border-umich-blue bg-umich-blue/10 text-umich-blue"
            : "border-border-strong bg-surface text-fg hover:bg-surface-muted",
        )}
      >
        <ListFilter className="h-4 w-4 shrink-0" aria-hidden />
        {label}
        {active > 0 && (
          <span className="rounded-full bg-umich-blue px-1.5 text-2xs tabular-nums text-fg-inverse">
            {active}
            <span className="sr-only"> active</span>
          </span>
        )}
        <ChevronDown
          className={cn("h-4 w-4 shrink-0 transition-transform motion-reduce:transition-none", open && "rotate-180")}
          aria-hidden
        />
      </button>
      {/* Always in the DOM, so `aria-controls` names a real element. */}
      <div
        id={panelId}
        hidden={!open}
        className="absolute left-0 top-full z-30 mt-1 max-h-[70vh] w-[min(22rem,calc(100vw-2rem))] overflow-y-auto rounded-xs border border-border-strong bg-surface p-3 text-fg shadow-lg"
      >
        {groups.map((group) => (
          <fieldset key={group.key} className="mb-3 border-b border-border pb-3 last-of-type:mb-0">
            <legend className="mb-1 px-2 text-xs font-semibold text-fg">{group.label}</legend>
            {group.options.map((option) => {
              if (group.multiple && !option.value) return null;
              const current = valueOf(group);
              const checked = group.multiple
                ? splitFilter(current).includes(option.value)
                : current === option.value;
              return (
                <label
                  key={option.value || "all"}
                  // The whole row is the target, not just the box: a
                  // full-width strip at least one target tall, padded so a
                  // press anywhere on it toggles the option.
                  className={cn(
                    "flex min-h-target w-full cursor-pointer select-none items-center gap-3 rounded-xs px-3 py-2 text-sm hover:bg-surface-muted",
                    checked && "bg-umich-blue/5 font-semibold",
                  )}
                >
                  <input
                    type={group.multiple ? "checkbox" : "radio"}
                    name={`${panelId}-${group.key}`}
                    value={option.value}
                    data-value={option.value}
                    checked={checked}
                    onChange={() =>
                      choose(group, group.multiple ? toggled(group, current, option.value) : option.value)
                    }
                    className="h-5 w-5 shrink-0 cursor-pointer accent-umich-blue focus-visible:outline-none focus-visible:shadow-focus"
                  />
                  <span className="flex-1">{option.label}</span>
                  {option.count !== undefined && (
                    <span className="font-normal tabular-nums text-fg-muted">{option.count.toLocaleString()}</span>
                  )}
                </label>
              );
            })}
          </fieldset>
        ))}
        <div className="flex items-center justify-between gap-2 pt-1">
          <button
            type="button"
            // Resets this menu's groups only; the search is its own control.
            onClick={() => {
              if (!active) return;
              setPending(
                Object.fromEntries(groups.map((group) => [group.key, { value: "", from: group.value }])),
              );
              onReset();
            }}
            aria-disabled={active === 0 || undefined}
            className="min-h-target rounded-xs px-2 text-sm font-semibold text-umich-blue underline underline-offset-2 hover:text-umich-blue-600 focus-visible:outline-none focus-visible:shadow-focus aria-disabled:cursor-not-allowed aria-disabled:text-fg-muted aria-disabled:no-underline"
          >
            Clear all
          </button>
          <button
            type="button"
            onClick={close}
            className="min-h-target rounded-xs border border-border-strong bg-surface px-4 text-sm font-semibold text-fg hover:bg-surface-muted focus-visible:outline-none focus-visible:shadow-focus"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * "Level: Level A, Level AA" for each group that is narrowing the table, in
 * group order.
 */
export function activeFilterItems(groups: readonly FilterGroup[]): string[] {
  return groups
    .filter((group) => group.value)
    .map((group) => {
      const labels = splitFilter(group.value).map(
        (value) => group.options.find((candidate) => candidate.value === value)?.label ?? value,
      );
      return `${group.label}: ${labels.join(", ")}`;
    });
}

/**
 * What the table is filtered by, written out, with the way to undo it. It
 * sits under the bar whenever anything narrows the table, so the state is
 * never shown only by the Filter button's fill.
 */
export function ActiveFilters({ items, onClear }: { items: readonly string[]; onClear: () => void }) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border px-4 py-1 text-sm">
      <p className="text-fg-muted">
        <span className="font-semibold text-fg">Filtered by</span> {items.join(" · ")}
      </p>
      <button
        type="button"
        onClick={onClear}
        className="min-h-target rounded-xs px-1 font-semibold text-umich-blue underline underline-offset-2 hover:text-umich-blue-600 focus-visible:outline-none focus-visible:shadow-focus"
      >
        Clear filters
      </button>
    </div>
  );
}
