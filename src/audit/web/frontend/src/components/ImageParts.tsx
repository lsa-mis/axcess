import { useState } from "react";
import { Check, Copy, Sparkles, X } from "lucide-react";
import { blobUrl } from "../api/client";
import type { AltVerdict, ReportImage } from "../api/types";
import { useAiSetup } from "../hooks/useAiSetup";
import { setPreference, usePreferences } from "../hooks/usePreferences";
import { useModalDialog } from "../hooks/useModalDialog";
import { cn } from "../lib/cn";
import { copyText } from "../lib/clipboard";
import { ALT_VERDICT_LABEL, ALT_VERDICT_SOURCE_LABEL } from "../lib/terms";
import { AltTag, Button, LinkButton } from "./ui";

/**
 * The parts the Images tab (routes/Images.tsx) and one image's page
 * (routes/ImageDetail.tsx) share, so an image's name, verdict, suggestion
 * and viewer look and work the same on both (SC 3.2.4 Consistent
 * Identification, Level AA). Moved out of routes/Images.tsx on 2026-11-16,
 * when the image's own page was added.
 */

/** The tab's name, and the crumb an image's page carries back to it. */
export const IMAGES_VIEW = "Images";

/**
 * The column and the card that list an image's pages: the same words as the
 * Documents tab's (PAGES_COLUMN there), one name for one thing (W3C COGA,
 * "Making Content Usable", https://www.w3.org/TR/coga-usable/).
 */
export const IMAGE_PAGES_COLUMN = "Pages it appears on";

/** The image's own page. */
export function imagePath(scanId: number, imageId: number): string {
  return `/scans/${scanId}/images/${imageId}`;
}

/** Verdict chip colours. The words carry the meaning; colour only repeats it. */
export const VERDICT_CHIP: Record<AltVerdict, string> = {
  needs_alt: "border-sev-critical/40 bg-sev-critical-bg text-sev-critical",
  needs_better: "border-sev-major/40 bg-sev-major-bg text-sev-major",
  not_checked: "border-dashed border-border-strong bg-surface-muted text-fg-muted",
  good: "border-ok/40 bg-ok-bg text-ok",
};

/**
 * What the Images tab and an image's page say when the local AI check is
 * off, with the way to turn it on (the developer's request, 2026-11-16).
 *
 * In the desktop app, a link to Settings > AI features (``/settings/ai``),
 * where AI features are turned on; once they are on, the check uses the
 * vision model chosen there and the "Suggest alt text" buttons come back
 * (server.py, ``_alt_checker_factory_for``). Its words say what it does:
 * "Turn on local AI" while AI features are off, "Set up local AI" while
 * they are on but no model is set up, and "Change AI features" when they are
 * set up but the check still cannot run, so the link never offers to turn
 * on what is already on (AGENTS.md, Interface language rule 5). A link, not
 * a button: it goes to another page (WAI-ARIA APG, Link pattern;
 * LinkButton, ui.tsx). It is shown once, here, not in every row's
 * "Suggested alt text" cell, so the table has one way to do it (W3C COGA,
 * "Making Content Usable", https://www.w3.org/TR/coga-usable/).
 *
 * On a shared server there is no such page: its AI is set up by whoever
 * runs it (useAiSetup is undefined), so the text says who can turn it on
 * instead of offering a link that leads nowhere.
 *
 * "Don’t show again" beside the link hides the message (the developer's
 * request, 2026-11-16), for someone who does not want AI features. It is a
 * setting of this browser, like the others in Settings, and Settings >
 * Workspace > "Message that the local AI check is off" shows it again, so
 * the choice can be undone (W3C COGA, "Making Content Usable": let people
 * undo). Hidden, the fact itself stays: the table's cells, and the image's
 * page, still say "Local AI check is off" (AGENTS.md, Interface language
 * rule 4). The button's visible words are the developer's; screen-reader
 * text says what it hides (WCAG technique C7). Focus goes to the table's
 * region after the message goes, so it is not lost (SC 2.4.3 Focus Order,
 * Level A); ``onHidden`` says where.
 */
export function AltCheckOff({ onHidden }: { onHidden?: () => void } = {}) {
  const aiSetup = useAiSetup();
  const { aiOffNotice } = usePreferences();
  const link = !aiSetup
    ? null
    : !aiSetup.preferences.enabled
      ? { label: "Turn on local AI", note: "" }
      : !aiSetup.current
        ? { label: "Set up local AI", note: " AI features are on, but no AI model is set up yet." }
        : {
            label: "Change AI features",
            note: " AI features are on, but the check cannot use the chosen model.",
          };
  if (aiOffNotice === "off") {
    return <span className="text-xs text-fg-subtle">Local AI check is off</span>;
  }
  return (
    <div className="flex flex-col items-start gap-2">
      <p className="max-w-measure text-sm text-fg-muted">
        The local AI check is off, so no alt text can be suggested here.
        {link ? link.note : " The person who runs Axcess can turn it on."}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {link && (
          <LinkButton to="/settings/ai" variant="secondary">
            {link.label}
          </LinkButton>
        )}
        {/* The regular secondary button, the same as the link beside it
            (the developer's request, 2026-11-16): a ghost button read as
            text, not as something to press (W3C COGA, "Making Content
            Usable": make controls look like controls). */}
        <Button
          type="button"
          variant="secondary"
          onClick={() => {
            setPreference("aiOffNotice", "off");
            onHidden?.();
          }}
        >
          Don&rsquo;t show again
          <span className="sr-only">: the message that the local AI check is off</span>
        </Button>
      </div>
    </div>
  );
}

/** The image's file name, the row's name: "banner.png". */
export function imageName(image: ReportImage): string {
  try {
    const path = new URL(image.image_url).pathname;
    const last = decodeURIComponent(path.split("/").filter(Boolean).pop() ?? "");
    if (last) return last.length > 60 ? `${last.slice(0, 57)}…` : last;
  } catch {
    // An inline SVG has no address of its own; fall through.
  }
  return image.has_svg_text ? "Inline SVG" : "Image";
}

/**
 * The verdict as the Images table and the image's page show it: the chip,
 * the reason, then what decided it, each in words (SC 1.4.1 Use of Color,
 * Level A: the chip's colour only repeats its words).
 */
export function VerdictSummary({ image }: { image: ReportImage }) {
  return (
    <>
      <span
        className={cn(
          "inline-flex items-center rounded-xs border px-2 py-0.5 text-xs font-semibold",
          VERDICT_CHIP[image.verdict],
        )}
      >
        {ALT_VERDICT_LABEL[image.verdict]}
      </span>
      <span className="mt-1 block text-xs text-fg-muted">{image.verdict_reason}</span>
      {image.verdict_source && (
        <span className="mt-0.5 block text-xs text-fg-subtle">
          {ALT_VERDICT_SOURCE_LABEL[image.verdict_source]}
        </span>
      )}
    </>
  );
}

/**
 * The image small, for a table row or the image's page: the saved picture, or
 * "SVG" for text drawn in the page code, which has no picture of its own.
 * Decorative (alt=""): the name beside it says which image it is.
 */
export function ImageThumb({ image, className }: { image: ReportImage; className?: string }) {
  if (image.has_svg_text || !image.content_hash) {
    return (
      <span
        className={cn(
          "flex h-12 w-[72px] items-center justify-center rounded-xs border border-border bg-surface-muted font-mono text-2xs font-semibold text-fg-muted",
          className,
        )}
      >
        SVG
      </span>
    );
  }
  return (
    <img
      src={blobUrl(image.content_hash)}
      alt=""
      loading="lazy"
      decoding="async"
      width={72}
      height={48}
      className={cn("h-12 w-[72px] rounded-xs border border-border bg-white object-contain", className)}
    />
  );
}

/** The image's address, for "Open the image" on its page; null for an inline SVG. */
export function imageAddress(image: ReportImage): string | null {
  return /^https?:\/\//i.test(image.image_url) ? image.image_url : null;
}

/** The alt text a cell or fact shows, with how many there are when it differs between pages. */
export function CurrentAlt({ image }: { image: ReportImage }) {
  return (
    <>
      <AltTag value={image.alt_text} wrap />
      {image.alt_text_variants > 1 && (
        <span className="mt-1 block text-xs text-fg-muted">Differs between pages: this is the worst one.</span>
      )}
    </>
  );
}

/**
 * The image at full size, in a native modal ``<dialog>`` (useModalDialog), the
 * same pattern as the issue guidance dialog: the browser traps focus inside,
 * Escape closes it, and focus goes back to the button that opened it (WAI-ARIA
 * APG, Dialog (Modal) pattern, https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/).
 * A click on the dimmed area around it also closes it, as people expect of an
 * image viewer; the close button is the way that works for everyone.
 *
 * The close button says "Close image viewer" in visible words, not an X with
 * an aria-label (the repo's control-text rule). The picture itself has
 * alt="": the dialog's heading names it, and its current alt text and the
 * text read from it are written out below, so a screen reader user gets the
 * same facts without the picture claiming one of them as its description.
 */
export function ImageViewer({ image, onClose }: { image: ReportImage | null; onClose: () => void }) {
  const ref = useModalDialog(image != null);
  const name = image ? imageName(image) : "";
  return (
    // The click handler only catches clicks on the dimmed backdrop, a mouse
    // extra. Keyboard users close the dialog with Escape (native to a modal
    // <dialog>) or the close button, so no key listener is needed here.
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions -- Keep: backdrop click; Escape and the close button cover keyboard
    <dialog
      ref={ref}
      aria-labelledby="image-viewer-title"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      className="max-h-[92vh] w-[min(94vw,60rem)] overflow-y-auto rounded-xs border border-border bg-surface-raised p-0 text-fg shadow-raised backdrop:bg-black/60"
    >
      {image && (
        <>
          <div className="sticky top-0 z-[1] flex flex-wrap items-start justify-between gap-3 border-b border-border bg-surface px-5 py-3">
            <h2 id="image-viewer-title" className="min-w-0 break-all text-lg font-semibold">
              {name}
            </h2>
            <Button type="button" variant="secondary" onClick={onClose}>
              <X className="h-4 w-4" aria-hidden />
              Close image viewer
            </Button>
          </div>
          <div className="px-5 py-4">
            <img
              src={blobUrl(image.content_hash)}
              alt=""
              className="mx-auto max-h-[65vh] max-w-full rounded-xs border border-border bg-white object-contain"
            />
            <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[max-content_minmax(0,1fr)]">
              <dt className="font-semibold text-fg-muted">Current alt text</dt>
              <dd className="min-w-0">
                <AltTag value={image.alt_text} wrap />
              </dd>
              <dt className="font-semibold text-fg-muted">Text in the image</dt>
              <dd className="min-w-0 break-words">{image.image_text ?? "None found"}</dd>
              <dt className="font-semibold text-fg-muted">Alt text verdict</dt>
              <dd>
                {ALT_VERDICT_LABEL[image.verdict]}. {image.verdict_reason}
              </dd>
            </dl>
          </div>
        </>
      )}
    </dialog>
  );
}

/**
 * A suggested alt text, ready to paste: the text in a box of its own with
 * "Copy alt text" under it, then the caution about where it came from (the
 * developer's request, 2026-11-13).
 *
 * The box is a plain bordered panel, so the suggestion reads as the thing to
 * take. The caution sits below it as a separate note in the accent
 * colour, with a sparkle icon and in bold, so it is clearly seen and
 * cannot be mistaken for part of the alt text, nor for a verdict (the
 * verdict chips use the critical, major and ok colours). A dashed accent
 * border and italic text, not the information colours first tried: in the
 * dark theme those were nearly the box's own grey (2026-11-13 check). Its words carry
 * the meaning; the icon and colour only repeat it (SC 1.4.1 Use of Color,
 * Level A).
 *
 * The copy button follows the page code viewer's (components/DomSource.tsx):
 * its words change to "Copied" for two seconds and it is a polite live
 * region, so the result is heard. The repo has no shared copy button; this
 * is the second one, and a third should move both into components/ui.tsx.
 * Its name ends with the image's file name in screen-reader-only text, so
 * each row's button says which alt text it copies (WCAG technique C7). It
 * copies through lib/clipboard.ts, which also works on plain http. If the
 * browser still refuses, it says so and the text can be selected by hand.
 */
export function SuggestionBox({ text, name }: { text: string; name: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const copy = async () => {
    if (await copyText(text)) {
      setState("copied");
      window.setTimeout(() => setState("idle"), 2000);
    } else {
      setState("failed");
    }
  };
  return (
    <div className="space-y-2">
      <div className="rounded-xs border border-border-strong bg-surface p-2.5">
        <p className="break-words text-sm leading-6 text-fg">{text}</p>
        <Button size="sm" className="mt-2 min-h-target" onClick={() => void copy()} aria-live="polite">
          {state === "copied" ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
          {state === "copied" ? "Copied" : "Copy alt text"}
          <span className="sr-only"> for {name}</span>
        </Button>
        {state === "failed" && (
          <p className="mt-1 text-xs text-sev-critical">
            Your browser did not allow copying. Select the text and copy it instead.
          </p>
        )}
      </div>
      <p className="flex items-start gap-1.5 rounded-xs border border-dashed border-umich-blue/70 bg-umich-blue/10 px-2 py-1.5 text-xs font-semibold italic leading-5 text-fg-accent">
        <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        Written by the local AI model. Check it before you use it.
      </p>
    </div>
  );
}
