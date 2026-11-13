import { ExternalLink } from "lucide-react";
import type { ScreenReaderCheck } from "../api/types";

/**
 * Step-by-step screen reader checks, one panel per computer: "Mac, with
 * VoiceOver" and "Windows, with NVDA". Shown in the issue guidance under the
 * card's own check sentence, which says what you should find.
 *
 * Why both panels are always visible, side by side where the dialog is wide
 * and stacked where it is narrow: a reader sees the steps for their own
 * computer without first finding and operating a control, and the guidance
 * prints and reads the same for everyone. Tabs (WAI-ARIA APG Tabs pattern)
 * were rejected: they hide one set of steps behind a control and add a
 * widget for a choice the reader can make by reading two headings. W3C COGA,
 * "Making Content Usable" (https://www.w3.org/TR/coga-usable/), paraphrased:
 * keep related content visible and grouped, one idea per chunk.
 *
 * Each computer is a heading and a native numbered list (<ol>), the same
 * list as the guidance's other steps, so a screen reader announces "list, 5
 * items" and a reader can move by heading (SC 1.3.1 Info and Relationships,
 * Level A; SC 2.4.6 Headings and Labels, Level AA). The panels wrap at
 * 20rem, so nothing scrolls sideways at 320 px (SC 1.4.10 Reflow, Level AA).
 *
 * Keys are <kbd> elements styled as in the keyboard shortcuts dialog
 * (ShortcutsDialog), so a key looks the same everywhere (SC 3.2.4 Consistent
 * Identification, Level AA). The key's name is real text ("Command + F5"),
 * so it reads the same aloud; the box is only a visual aid.
 *
 * The steps are plain text from rules/screen_reader_checks.yaml. A key is
 * written {Command} there; nothing from the YAML is rendered as HTML.
 */
export default function ScreenReaderSteps({
  check,
  headingLevel = 4,
}: {
  check: ScreenReaderCheck;
  /** The level of this block's own heading; each computer is one level below. */
  headingLevel?: 4 | 5;
}) {
  const Title = `h${headingLevel}` as "h4" | "h5";
  const Platform = `h${headingLevel + 1}` as "h5" | "h6";
  return (
    <div className="mt-5">
      <Title className="text-base font-semibold text-fg">{check.title}</Title>
      <div className="mt-3 flex flex-wrap gap-4">
        {check.platforms.map((platform) => (
          <section
            key={platform.id}
            aria-labelledby={`sr-check-${check.id}-${platform.id}`}
            className="min-w-0 flex-[1_1_20rem] rounded-xs border border-border bg-surface p-4"
          >
            <Platform id={`sr-check-${check.id}-${platform.id}`} className="text-base font-semibold text-fg">
              {platform.name}
            </Platform>
            {platform.intro && (
              <p className="mt-1 text-sm leading-6 text-fg-muted">
                <WithKeys text={platform.intro} />
              </p>
            )}
            {platform.link_url && (
              <p className="mt-1 text-sm leading-6">
                <a
                  href={platform.link_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  // On its own line, so the inline-link exception does not
                  // apply: 44 px tall like every standalone link (SC 2.5.5
                  // Target Size (Enhanced), Level AAA).
                  className="inline-flex min-h-target items-center gap-1 font-semibold text-umich-blue underline underline-offset-2"
                >
                  {platform.link_text ?? platform.link_url}
                  <ExternalLink className="h-3.5 w-3.5 shrink-0" aria-hidden />
                  <span className="sr-only">, opens in a new tab</span>
                </a>
              </p>
            )}
            <ol className="mt-3 list-decimal space-y-2 pl-6 text-base leading-7 text-fg">
              {platform.steps.map((step, i) => (
                <li key={i}>
                  <WithKeys text={step} />
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
    </div>
  );
}

/** Plain text with each {Key} shown as a key. */
function WithKeys({ text }: { text: string }) {
  const parts = text.split(/\{([^{}]+)\}/g);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <kbd
            key={i}
            className="whitespace-nowrap rounded-2xs border border-border-strong bg-surface-muted px-2 py-0.5 font-mono text-xs"
          >
            {part}
          </kbd>
        ) : (
          part
        ),
      )}
    </>
  );
}
