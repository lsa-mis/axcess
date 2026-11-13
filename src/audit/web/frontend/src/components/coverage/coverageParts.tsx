import { ExternalLink } from "lucide-react";
import type { ReactNode } from "react";
import type { CheckMethod } from "../../api/types";
import { cn } from "../../lib/cn";
import { CHECK_METHOD_LABEL } from "../../lib/terms";

/**
 * Small parts shared by the two Coverage views (routes/Coverage.tsx).
 *
 * How a criterion is checked is shown three ways at once: a colour (a top edge
 * or a dot), a symbol, and the words. Colour alone would fail SC 1.4.1 Use of
 * Color (Level A); the symbol keeps the five kinds apart in a dense grid and
 * in greyscale; the words are what a screen reader reads. Each colour is a
 * theme token that keeps at least 3:1 against the card in both themes (SC
 * 1.4.11 Non-text Contrast, Level AA): ok green, UMich blue, the "major" amber,
 * and two greys.
 */
export const METHOD_ORDER: CheckMethod[] = ["automated", "partial", "ai-assisted", "manual", "not_needed"];

export const METHOD_GLYPH: Record<CheckMethod, string> = {
  automated: "●",
  partial: "◐",
  "ai-assisted": "◇",
  manual: "○",
  not_needed: "⊘",
};

export const METHOD_TEXT: Record<CheckMethod, string> = {
  automated: "text-ok",
  partial: "text-umich-blue",
  "ai-assisted": "text-sev-major",
  manual: "text-fg-subtle",
  not_needed: "text-border-strong",
};

/** The top edge of a tile or square, in the method's colour. */
export const METHOD_EDGE: Record<CheckMethod, string> = {
  automated: "shadow-[inset_0_4px_0_rgb(var(--c-ok))]",
  partial: "shadow-[inset_0_4px_0_rgb(var(--c-umich-blue))]",
  "ai-assisted": "shadow-[inset_0_4px_0_rgb(var(--c-sev-major))]",
  manual: "shadow-[inset_0_4px_0_rgb(var(--c-fg-subtle))]",
  not_needed: "shadow-[inset_0_4px_0_rgb(var(--c-border-strong))]",
};

/** The method's symbol, hidden from screen readers, which read the words beside it. */
export function MethodMark({ method, className }: { method: CheckMethod; className?: string }) {
  return (
    <span aria-hidden className={cn("text-sm leading-none", METHOD_TEXT[method], className)}>
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
