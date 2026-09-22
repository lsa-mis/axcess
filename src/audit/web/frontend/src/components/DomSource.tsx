import { useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Check, ChevronDown, ChevronUp, Copy } from "lucide-react";
import { cn } from "../lib/cn";
import { Button } from "./ui";

type TokenKind = "punct" | "tag" | "attr" | "value" | "text" | "comment" | "doctype";
type Token = { kind: TokenKind; text: string };
type Line = { depth: number; tokens: Token[]; marked: boolean };

const VOID = new Set([
  "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr",
]);
const RAW_TEXT = new Set(["script", "style", "pre", "textarea"]);
const MAX_LINES = 80_000;
const MAX_DEPTH = 400;
const INLINE_TEXT_MAX = 100;

function collapse(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/**
 * Turn a serialized document into one line per node, indented by nesting.
 *
 * A captured DOM is one enormous line, which is unreadable as a whole and
 * useless for orientation: the reader wants to see *where* a flagged element
 * sits. So the document is re-walked and printed the way a person would write
 * it — one tag per line, attributes on the tag, short text inline, raw text
 * (`<script>`, `<style>`, `<pre>`) as it is. Nothing is executed and nothing
 * is fetched: the parse is `DOMParser`'s inert document, and every token is
 * rendered as text.
 *
 * Every line inside a flagged element (found by `locate`) is `marked`, so the
 * whole element reads as one block rather than a single highlighted run of
 * characters.
 */
export function formatDom(
  html: string,
  locate: (doc: Document) => Element[],
): { lines: Line[]; marked: number; markStarts: number[]; truncated: boolean } {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const flagged = new Set(locate(doc));
  const lines: Line[] = [];
  let truncated = false;
  let firstMarkedCount = 0;
  /** The line each flagged element's block starts on, in document order. */
  const markStarts: number[] = [];

  const push = (depth: number, tokens: Token[], marked: boolean) => {
    if (lines.length >= MAX_LINES) {
      truncated = true;
      return false;
    }
    lines.push({ depth, tokens, marked });
    return true;
  };

  const openTag = (el: Element): Token[] => {
    const tokens: Token[] = [{ kind: "punct", text: "<" }, { kind: "tag", text: el.localName }];
    for (const attr of el.attributes) {
      tokens.push({ kind: "punct", text: " " }, { kind: "attr", text: attr.name });
      if (attr.value !== "") {
        tokens.push(
          { kind: "punct", text: '="' },
          { kind: "value", text: attr.value.replace(/"/g, "&quot;") },
          { kind: "punct", text: '"' },
        );
      }
    }
    tokens.push({ kind: "punct", text: ">" });
    return tokens;
  };
  const closeTag = (el: Element): Token[] => [
    { kind: "punct", text: "</" },
    { kind: "tag", text: el.localName },
    { kind: "punct", text: ">" },
  ];

  const walk = (node: Node, depth: number, inMark: boolean): boolean => {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = collapse(node.textContent ?? "");
      if (!text) return true;
      return push(depth, [{ kind: "text", text }], inMark);
    }
    if (node.nodeType === Node.COMMENT_NODE) {
      return push(depth, [{ kind: "comment", text: `<!-- ${collapse(node.textContent ?? "")} -->` }], inMark);
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return true;
    const el = node as Element;
    const marked = inMark || flagged.has(el);
    if (marked && !inMark) {
      firstMarkedCount += 1;
      markStarts.push(lines.length);
    }

    if (depth > MAX_DEPTH) {
      // Deeper than any sane document: print the rest as one line rather
      // than recurse further.
      return push(depth, [{ kind: "text", text: el.outerHTML }], marked);
    }
    const name = el.localName;
    if (VOID.has(name)) return push(depth, openTag(el), marked);

    if (RAW_TEXT.has(name)) {
      if (!push(depth, openTag(el), marked)) return false;
      const raw = el.textContent ?? "";
      if (raw.trim()) {
        for (const rawLine of raw.replace(/\r\n?/g, "\n").split("\n")) {
          if (!push(depth + 1, [{ kind: "text", text: rawLine }], marked)) return false;
        }
      }
      return push(depth, closeTag(el), marked);
    }

    const children = [...el.childNodes].filter(
      (child) => child.nodeType !== Node.TEXT_NODE || collapse(child.textContent ?? ""),
    );
    if (
      children.length === 1 &&
      children[0].nodeType === Node.TEXT_NODE &&
      collapse(children[0].textContent ?? "").length <= INLINE_TEXT_MAX
    ) {
      return push(
        depth,
        [...openTag(el), { kind: "text", text: collapse(children[0].textContent ?? "") }, ...closeTag(el)],
        marked,
      );
    }
    if (children.length === 0) {
      return push(depth, [...openTag(el), ...closeTag(el)], marked);
    }
    if (!push(depth, openTag(el), marked)) return false;
    for (const child of children) {
      if (!walk(child, depth + 1, marked)) return false;
    }
    return push(depth, closeTag(el), marked);
  };

  if (doc.doctype) {
    push(0, [{ kind: "doctype", text: `<!DOCTYPE ${doc.doctype.name}>` }], false);
  }
  walk(doc.documentElement, 0, false);
  return { lines, marked: firstMarkedCount, markStarts, truncated };
}

/**
 * The Loaded DOM tab's source view: pretty-printed, coloured by token,
 * numbered, and virtualized so a two-megabyte capture scrolls like a text
 * editor instead of freezing the page. Flagged elements are whole marked
 * blocks with a jump button, since the point of opening the source is to
 * see the flagged markup in its context.
 */
export default function DomSource({
  html,
  locate,
  onMarked,
  className,
}: {
  html: string;
  locate: (doc: Document) => Element[];
  /** How many flagged elements were found in this capture. */
  onMarked?: (count: number) => void;
  className?: string;
}) {
  const formatted = useMemo(() => formatDom(html, locate), [html, locate]);
  const { lines, marked, markStarts, truncated } = formatted;
  useEffect(() => onMarked?.(marked), [marked, onMarked]);
  // Which flagged element the reader is on, for Previous / Next. Starts on
  // the first and is reset when the capture changes.
  const [current, setCurrent] = useState(0);
  useEffect(() => setCurrent(0), [html]);

  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: lines.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 22,
    overscan: 40,
  });
  const items = virtualizer.getVirtualItems();
  const firstMarked = markStarts[0] ?? -1;
  const gutter = String(lines.length).length;

  const goTo = (index: number) => {
    const bounded = Math.max(0, Math.min(markStarts.length - 1, index));
    setCurrent(bounded);
    virtualizer.scrollToIndex(markStarts[bounded], { align: "center" });
  };
  // Land on the flagged markup as soon as the source is shown: nobody should
  // have to scroll a 40,000-line document to find one element.
  useEffect(() => {
    if (firstMarked >= 0) virtualizer.scrollToIndex(firstMarked, { align: "center" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstMarked, html]);

  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(html);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className={cn("flex min-w-0 flex-col gap-2", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-2xs text-fg-muted">
          {lines.length.toLocaleString()} lines
          {truncated ? " (display capped; the capture continues past this point)" : ""}
        </span>
        <span className="ml-auto flex flex-wrap gap-2">
          {markStarts.length > 0 && (
            // Previous / Next step through the flagged elements in document
            // order; the count between them says where you are. One element
            // still gets a single "Jump" so the control matches the job.
            <span
              role="group"
              aria-label="Flagged elements"
              className="inline-flex items-center gap-1 rounded-xs border border-border bg-surface pl-2"
            >
              <span role="status" aria-atomic="true" className="text-2xs font-semibold text-fg-muted">
                {markStarts.length === 1
                  ? "1 flagged element"
                  : `Flagged element ${current + 1} of ${markStarts.length}`}
              </span>
              {markStarts.length > 1 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="min-h-target"
                  aria-label="Previous flagged element"
                  disabled={current === 0}
                  onClick={() => goTo(current - 1)}
                >
                  <ChevronUp className="h-4 w-4" aria-hidden />
                </Button>
              )}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="min-h-target"
                aria-label={markStarts.length > 1 ? "Next flagged element" : "Jump to flagged element"}
                disabled={markStarts.length > 1 && current === markStarts.length - 1}
                onClick={() => goTo(markStarts.length > 1 ? current + 1 : 0)}
              >
                <ChevronDown className="h-4 w-4" aria-hidden />
              </Button>
            </span>
          )}
          <Button type="button" size="sm" className="min-h-target" onClick={copy} aria-live="polite">
            {copied ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
            {copied ? "Copied" : "Copy source"}
          </Button>
        </span>
      </div>
      <div
        ref={scrollRef}
        role="region"
        aria-label="Loaded DOM source"
        // Keyboard users need focus on the overflow region to scroll it.
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={0}
        className="max-h-[70vh] overflow-auto rounded-2xs border border-border bg-surface-muted font-mono text-2xs leading-relaxed text-fg focus-visible:shadow-focus"
      >
        <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
          {items.map((item) => {
            const line = lines[item.index];
            return (
              <div
                key={item.key}
                ref={virtualizer.measureElement}
                data-index={item.index}
                className={cn(
                  "absolute left-0 flex w-full items-start",
                  line.marked && "bg-umich-maize/25 shadow-[inset_3px_0_0_theme(colors.umich.maize)]",
                  line.marked &&
                    item.index >= (markStarts[current] ?? -1) &&
                    item.index < (markStarts[current + 1] ?? Number.POSITIVE_INFINITY) &&
                    "shadow-[inset_3px_0_0_theme(colors.umich.blue)]",
                )}
                style={{ transform: `translateY(${item.start}px)` }}
              >
                <span
                  aria-hidden
                  className="shrink-0 select-none pr-3 text-right text-fg-subtle"
                  style={{ width: `${gutter + 2}ch` }}
                >
                  {item.index + 1}
                </span>
                <span
                  className="min-w-0 flex-1 whitespace-pre-wrap break-all pr-3"
                  style={{ paddingLeft: `${line.depth * 1.5}ch` }}
                >
                  {line.tokens.map((token, index) => (
                    <span key={index} className={`tok-${token.kind}`}>
                      {token.text}
                    </span>
                  ))}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
