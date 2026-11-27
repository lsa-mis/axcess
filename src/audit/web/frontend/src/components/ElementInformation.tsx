import { type ReactNode, useLayoutEffect, useRef, useState } from "react";
import { Check, ChevronDown, ChevronUp, Copy } from "lucide-react";
import type { ElementPlace } from "../api/types";
import { cn } from "../lib/cn";
import { readableLocator, type ElementDescription, type Target } from "../lib/highlightTargets";
import { Button } from "./ui";

/**
 * Element information: what the numbered box in the page inspector is on,
 * as a short table with the same labels in the same places for every
 * flagged element, so Previous element and Next element change only the
 * values. It sits in the inspector's "Element information" caret.
 *
 * History. This table was under the inspector's toolbar until 2026-11-10,
 * when the developer removed it (commit 318205c), against the
 * recommendation to keep it; the element locator row and "Copy element
 * locator" had gone the same day with every locator on screen (commit
 * 5d03aa3). On 2026-11-27 the developer asked for it back, locator and
 * Copy included, inside a closed caret ("Regan's Element Information"), so
 * a reader who needs it, a developer finding the element in the code, can
 * open it and everyone else is not shown page-code details. That reverses
 * both 2026-11-10 decisions for the inspector only; other screens still
 * show the element's code, not its locator (ElementCode, components/ui.tsx).
 *
 * Its own component, not part of routes/Inspector.tsx where it lived
 * before: the inspector is the only user, but it is already over 2,500
 * lines, and this table has its own state (the locator's Show all and
 * Copy). No shared component fits: ElementCode shows code, not facts.
 */
export default function ElementInformation({
  element,
  target,
  sharedCount,
  boxNote,
}: {
  element: ElementDescription;
  /** The occurrence's target the box is on, for its locator or place. */
  target: Target | undefined;
  /** How many occurrences share the element the reader is on. */
  sharedCount: number;
  /** Where the box is, in words, when it is not simply around the element. */
  boxNote: string | null;
}) {
  // An image or an AI review finding is found by its place among elements of
  // its kind; its selector (``a[ord=6]``) is not one a browser can use.
  const place: ElementPlace | null = target?.image?.locator
    ? {
        selector: target.image.locator.kind === "source" ? "picture > source" : target.image.locator.kind,
        index: target.image.locator.index,
        total: target.image.locator.total,
      }
    : (target?.place ?? null);
  const address = target?.image?.locator?.candidate ?? null;
  // readableLocator returns a selector unchanged and turns a Rule check
  // (Alfa) record into its XPath, so a changed string is an XPath. An AI
  // review selector such as ``a[ord=6]`` counts the analyzer's own list of
  // links, which no browser can use: it is not shown as a locator at all.
  const locator = readableLocator(target?.selector ?? null);
  const isXPath = locator !== null && locator !== target?.selector;
  const shownLocator = locator && !/\[ord=\d+\]/.test(locator) ? locator : null;
  // Whether the locator is shown in full. It stays as the reader set it
  // while they step, so every element's row keeps the same shape.
  const [locatorOpen, setLocatorOpen] = useState(false);

  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] content-start gap-x-3 gap-y-1 text-sm sm:gap-x-4">
      <ElementFact term="What it is">{element.kind}</ElementFact>
      <ElementFact term="Text or label">
        {element.text ? `“${element.text}”` : <span className="text-fg-muted">None found</span>}
      </ElementFact>
      <ElementFact term="Size">
        <span className="tabular-nums">
          {pixels(element.width)} wide, {pixels(element.height)} tall
        </span>
        {element.where === null && (element.width === 0 || element.height === 0) && (
          <span className="block text-xs text-fg-muted">
            It has no visible size in this saved copy, so the box marks where it sits.
          </span>
        )}
      </ElementFact>
      {boxNote && <ElementFact term="Where the box is">{boxNote}</ElementFact>}
      {sharedCount > 1 && <ElementFact term="Issue occurrences">{sharedCount} on this element</ElementFact>}
      {place ? (
        <>
          <ElementFact term="Where it is in the page code" stack>
            Number {place.index + 1} of the {place.total}{" "}
            <code translate="no" className="font-mono text-xs">
              {place.selector}
            </code>{" "}
            {place.total === 1 ? "element" : "elements"}
          </ElementFact>
          {address && (
            <ElementFact term="Image address">
              <code translate="no" className="font-mono text-xs">
                {address}
              </code>
            </ElementFact>
          )}
        </>
      ) : (
        shownLocator && (
          <ElementFact term={isXPath ? "Element locator (XPath)" : "Element locator (CSS selector)"} stack>
            <LocatorValue
              key={shownLocator}
              id="inspect-locator"
              value={shownLocator}
              open={locatorOpen}
              onOpenChange={setLocatorOpen}
            />
          </ElementFact>
        )
      )}
    </dl>
  );
}

/** "1 pixel", "924 pixels". */
function pixels(n: number): string {
  return `${n} ${n === 1 ? "pixel" : "pixels"}`;
}

/**
 * One labelled fact about the flagged element: the label, then its value,
 * lined up with the rows above and below. A long label (`stack`) sits above
 * its value until the screen is wide, so the value keeps its room on a
 * narrow screen (SC 1.4.10 Reflow, Level AA).
 */
function ElementFact({ term, stack = false, children }: { term: string; stack?: boolean; children: ReactNode }) {
  return (
    <div
      className={cn(
        "col-span-2",
        stack ? "lg:grid lg:grid-cols-subgrid lg:items-baseline" : "grid grid-cols-subgrid items-baseline",
      )}
    >
      <dt className="text-xs font-semibold text-fg-muted">{term}</dt>
      <dd className="min-w-0 [overflow-wrap:anywhere]">{children}</dd>
    </div>
  );
}

/**
 * An element locator, and under it the two controls for it: "Copy element
 * locator" and, when the locator is cut, "Show all". Restored unchanged
 * from commit 5d03aa3, where its full rationale was; in short:
 *
 * The locator is on one line, cut at its start, so its end, the part that
 * names the element, stays in view; "Show all" puts each step on its own
 * line. The cut is visual only: the text in the page is the whole locator,
 * and a screen reader reads all of it. The controls sit under the locator,
 * next to what they act on (W3C COGA, "Making Content Usable",
 * https://www.w3.org/TR/coga-usable/, paraphrased: keep related things
 * together), Copy first so it stays in one place whether or not Show all is
 * there. Both are 44 px targets (SC 2.5.5 Target Size (Enhanced), Level
 * AAA).
 *
 * The copy button's words never change; the result is said in a status
 * under the controls (SC 4.1.3 Status Messages, Level AA). Each copy gets a
 * new key, so a second "Copied" is announced like the first. When the
 * browser blocks copying (plain http on a network address), the whole
 * locator is shown and selected, so Ctrl+C or Command+C copies it.
 */
function LocatorValue({
  id,
  value,
  open,
  onOpenChange,
}: {
  id: string;
  value: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const codeRef = useRef<HTMLElement>(null);
  const probeRef = useRef<HTMLSpanElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const copyRef = useRef<HTMLButtonElement>(null);
  const [cut, setCut] = useState(false);
  // Whether the locator is wider than its line, measured on a hidden copy of
  // it on one line (the probe), so the answer holds while it is shown in
  // full too.
  useLayoutEffect(() => {
    const code = codeRef.current;
    const probe = probeRef.current;
    if (!code || !probe) return;
    const measure = () => {
      const isCut = probe.getBoundingClientRect().width > code.clientWidth + 0.5;
      // The toggle is about to go: move its focus on rather than lose it.
      if (!isCut && !open && document.activeElement === toggleRef.current) copyRef.current?.focus();
      setCut(isCut);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(code);
    observer.observe(probe);
    return () => observer.disconnect();
  }, [open]);

  const attempts = useRef(0);
  const [copied, setCopied] = useState<{ attempt: number; ok: boolean } | null>(null);
  const selectLocator = () => {
    const code = codeRef.current;
    if (code) window.getSelection()?.selectAllChildren(code);
  };
  // Selected once the whole locator is on screen, not on a guess at when that is.
  const selectWhenOpen = useRef(false);
  useLayoutEffect(() => {
    if (!open || !selectWhenOpen.current) return;
    selectWhenOpen.current = false;
    selectLocator();
  });
  const copy = async () => {
    attempts.current += 1;
    const attempt = attempts.current;
    try {
      await navigator.clipboard.writeText(value);
      setCopied({ attempt, ok: true });
    } catch {
      setCopied({ attempt, ok: false });
      if (open) selectLocator();
      else {
        selectWhenOpen.current = true;
        onOpenChange(true);
      }
    }
  };

  // Split before each " > ", so the steps join back into the exact locator.
  // The split is for display only: textContent and copy stay exact.
  const steps = value.split(/(?= > )/);
  const last = steps.length - 1;
  const stepSpans = (block: boolean) =>
    steps.map((step, index) => (
      <span
        key={index}
        className={cn(block && "block pl-4 -indent-4", index === last && steps.length > 1 && "font-semibold")}
      >
        {step}
      </span>
    ));
  return (
    <div className="relative">
      {/* Out of the flow and clipped to nothing, so it never widens the page. */}
      <span aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-0 overflow-hidden">
        <span ref={probeRef} className="invisible inline-block whitespace-nowrap font-mono text-xs">
          {stepSpans(false)}
        </span>
      </span>
      <code
        id={id}
        ref={codeRef}
        translate="no"
        className={cn(
          "block min-w-0 font-mono text-xs text-fg",
          !open && "overflow-hidden text-ellipsis whitespace-nowrap text-left [direction:rtl]",
        )}
      >
        <span dir="ltr" className={open ? "block" : undefined}>
          {stepSpans(open)}
        </span>
      </code>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <Button ref={copyRef} type="button" variant="secondary" size="sm" className="min-h-target" onClick={copy}>
          <Copy className="h-3.5 w-3.5" aria-hidden />
          Copy element locator
        </Button>
        {(cut || open) && (
          <Button
            ref={toggleRef}
            type="button"
            variant="ghost"
            size="sm"
            className="min-h-target"
            aria-expanded={open}
            aria-controls={id}
            onClick={() => {
              // Closing a locator that fits removes this button: focus Copy first.
              if (open && !cut) copyRef.current?.focus();
              onOpenChange(!open);
            }}
          >
            {open ? <ChevronUp className="h-3.5 w-3.5" aria-hidden /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden />}
            {open ? "Show less of the element locator" : "Show all of the element locator"}
          </Button>
        )}
      </div>
      <p role="status" className="mt-1 max-w-measure text-xs text-fg empty:sr-only">
        {copied &&
          (copied.ok ? (
            <span key={copied.attempt} className="inline-flex items-center gap-1">
              <Check className="h-3.5 w-3.5" aria-hidden />
              Copied
            </span>
          ) : (
            <span key={copied.attempt}>
              Not copied. Your browser did not allow it. The element locator is now shown in full and selected.
              Press Ctrl+C, or Command+C on a Mac, to copy it.
            </span>
          ))}
      </p>
    </div>
  );
}
