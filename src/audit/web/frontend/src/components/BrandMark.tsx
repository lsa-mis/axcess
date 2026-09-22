import { cn } from "../lib/cn";

/**
 * Brand mark: the A11y Crawler logo — an open scan path with a node riding its
 * leading edge. The outer ring is a crawl that has not closed yet, the dot is
 * the page it is on, and the inner form is the scan drawn as a rounded 'a' for
 * Axcess.
 *
 * Drawn in currentColor with no tile behind it, so it takes the colour of
 * whatever surface it sits on: UMich blue on the light sidebar, white on the
 * blue mobile bar. Stroke geometry is the original's, unaltered.
 *
 * Decorative: it always sits beside the word "Axcess", so naming it here would
 * only make a screen reader say it twice.
 */
export default function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={cn("shrink-0", className)}
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M 20.31 4.16 A 12.6 12.6 0 1 0 26.45 8.95" />
      <path d="M 17.438 21.016 C 16.989 21.141 16.515 21.208 16.026 21.208 C 13.135 21.208 10.792 18.865 10.792 15.974 C 10.792 13.083 13.135 10.74 16.026 10.74 C 18.917 10.74 21.26 13.083 21.26 15.974 C 21.26 17.37 21.26 18.97 21.26 21.016"/>
      <circle cx="20.31" cy="4.16" r="3.2" fill="currentColor" stroke="none" />
    </svg>
  );
}

