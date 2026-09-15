import { cn } from "../lib/cn";

/**
 * The Axcess mark with its crawl ring split away from the inner 'a'.
 *
 * `AppShell`'s `BrandMark` draws this same geometry as one static group. Here
 * the open scan path and the node riding its leading edge live in their own
 * <g> so they can turn on their own while the 'a' stays upright — a spinning
 * letterform reads as a glyph tumbling, not as work in progress. It also keeps
 * the metaphor honest: the ring is the crawl, so the crawl is what moves.
 *
 * `transform-box: view-box` is what makes `origin-center` resolve to the
 * viewBox centre (16,16), which is the arc's own centre. Without it the origin
 * falls back to the group's tight bounding box and the ring wobbles off-axis.
 *
 * Decorative: the visible label beside it already says the same thing.
 */
function SpinningMark({ className }: { className?: string }) {
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
      <g className="origin-center animate-spin-ring [transform-box:view-box] motion-reduce:animate-none">
        <path d="M 20.31 4.16 A 12.6 12.6 0 1 0 26.45 8.95" />
        <circle cx="20.31" cy="4.16" r="3.2" fill="currentColor" stroke="none" />
      </g>
      <path d="M 17.438 21.016 C 16.989 21.141 16.515 21.208 16.026 21.208 C 13.135 21.208 10.792 18.865 10.792 15.974 C 10.792 13.083 13.135 10.74 16.026 10.74 C 18.917 10.74 21.26 13.083 21.26 15.974 C 21.26 17.37 21.26 18.97 21.26 21.016" />
    </svg>
  );
}

/**
 * Waiting state: the spinning mark over a short label, on the bare surface.
 *
 * No card, no border, no progress bar. A determinate-looking bar on an
 * indeterminate wait is a lie, and a box around two centred elements only
 * draws an edge around empty space.
 *
 * `role="status"` announces the label politely when this mounts, so a screen
 * reader hears the wait without it stealing focus. Pass a `label` that names
 * the specific wait when you have one ("Loading report"); the default is the
 * generic case.
 *
 * Centres itself inside whatever box it is given. For a whole-viewport wait,
 * pass `className="min-h-screen"`.
 */
export default function Loading({
  label = "Loading",
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex flex-col items-center justify-center gap-4 p-8 text-center",
        className,
      )}
    >
      <SpinningMark className="h-20 w-20 text-umich-blue" />
      <p className="text-sm font-medium text-fg-muted">{label}</p>
    </div>
  );
}
