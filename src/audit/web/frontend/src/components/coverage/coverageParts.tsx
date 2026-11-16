import { ExternalLink } from "lucide-react";
import type { ReactNode } from "react";
import type { CheckMethod } from "../../api/types";
import { cn } from "../../lib/cn";
import { CHECK_METHOD_LABEL } from "../../lib/terms";

/**
 * Small parts shared by the two Coverage views (routes/Coverage.tsx).
 *
 * How a criterion is checked is shown three ways at once: a fill, a symbol,
 * and the words. The fill is one blue in five lightness steps, near black
 * for "Axcess checks" down to near white for "No longer needed", the order
 * of how much Axcess does (styles.css, --c-method-*; the developer's request,
 * 2026-11-16). It replaced five hues on a thin top edge (green, blue, amber
 * and two greys), which read as one colour, and told the kinds apart by
 * colour alone. Lightness steps survive greyscale and every colour-vision
 * setting; the symbol (a filled circle, a half circle, a diamond, an empty
 * circle, a crossed circle) keeps them apart by shape too, so colour is
 * never the only sign (SC 1.4.1 Use of Color, Level A); the words are what a
 * screen reader reads. Every step's text is 7:1 or more on its own fill (SC
 * 1.4.6 Contrast (Enhanced), Level AAA).
 *
 * The filter cards over the grid show the same filled square as the grid,
 * so the legend looks like what it explains.
 */
export const METHOD_ORDER: CheckMethod[] = ["automated", "partial", "ai-assisted", "manual", "not_needed"];

export const METHOD_GLYPH: Record<CheckMethod, string> = {
  automated: "●",
  partial: "◐",
  "ai-assisted": "◇",
  manual: "○",
  not_needed: "⊘",
};

/**
 * The method's fill and the ink on it. Written out whole, so Tailwind sees
 * each class. The hover fill is the same, so a square does not change colour
 * under the pointer (the shared Button's hover would otherwise replace it).
 */
export const METHOD_FILL: Record<CheckMethod, string> = {
  automated:
    "bg-[rgb(var(--c-method-automated))] hover:bg-[rgb(var(--c-method-automated))] text-[rgb(var(--c-method-automated-ink))]",
  partial:
    "bg-[rgb(var(--c-method-partial))] hover:bg-[rgb(var(--c-method-partial))] text-[rgb(var(--c-method-partial-ink))]",
  "ai-assisted":
    "bg-[rgb(var(--c-method-ai))] hover:bg-[rgb(var(--c-method-ai))] text-[rgb(var(--c-method-ai-ink))]",
  manual:
    "bg-[rgb(var(--c-method-manual))] hover:bg-[rgb(var(--c-method-manual))] text-[rgb(var(--c-method-manual-ink))]",
  not_needed:
    "bg-[rgb(var(--c-method-not-needed))] hover:bg-[rgb(var(--c-method-not-needed))] text-[rgb(var(--c-method-not-needed-ink))]",
};

/**
 * The method's symbol on its fill, a small square: the grid's square in
 * little, for the filter cards and the criterion's chip. Hidden from screen
 * readers, which read the words beside it. Its border keeps the near-white
 * (or, dark theme, near-black) step visible against the card.
 */
export function MethodMark({ method, className }: { method: CheckMethod; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-2xs border border-border-strong text-xs leading-none",
        METHOD_FILL[method],
        className,
      )}
    >
      {METHOD_GLYPH[method]}
    </span>
  );
}

/** Symbol and words together, for a chip or a table cell. */
export function MethodLabel({ method }: { method: CheckMethod }) {
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <MethodMark method={method} />
      {CHECK_METHOD_LABEL[method]}
    </span>
  );
}

/**
 * An inline link to a page outside Axcess, opening in a new tab: the W3C's
 * WCAG pages, the APG, Deque's rule pages and the two studies. The same
 * pattern as the rule links on the Rule check pages (routes/A11yByRule.tsx):
 * an icon, and screen-reader text that says a new tab opens, so the change of
 * context is announced before it happens (SC 3.2.5 Change on Request, Level
 * AAA; WCAG technique G201). `detail` names the destination when the visible
 * words alone would not (SC 2.4.9 Link Purpose (Link Only), Level AAA).
 */
export function ExternalTextLink({
  href,
  children,
  detail,
  standalone = false,
  className,
}: {
  href: string;
  children: ReactNode;
  detail?: string;
  /**
   * A link on a line of its own gets a 44 px target (SC 2.5.5 Target Size,
   * Level AAA, as the rest of the app); only a link inside a sentence may be
   * smaller, the criterion's inline exception.
   */
  standalone?: boolean;
  className?: string;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "inline-flex items-center gap-1 text-umich-blue underline underline-offset-2",
        standalone && "min-h-target",
        className,
      )}
    >
      {children}
      <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
      <span className="sr-only">
        {detail ? `, ${detail}` : ""} (opens in a new tab)
      </span>
    </a>
  );
}

/** A share, 0-1, as a whole percent. Below one percent says so instead of "0%". */
export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value > 0 && value < 0.005) return "Under 1%";
  return `${Math.round(value * 100)}%`;
}

export const formatCount = (n: number) => n.toLocaleString("en-US");

/** Compare WCAG numbers as numbers: 1.4.10 after 1.4.5. */
export function compareSc(a: string, b: string): number {
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  for (let i = 0; i < 3; i += 1) {
    const diff = (left[i] ?? 0) - (right[i] ?? 0);
    if (diff) return diff;
  }
  return 0;
}
