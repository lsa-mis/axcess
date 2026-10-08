import type { Config } from "tailwindcss";

/**
 * University of Michigan brand tokens — WCAG 2.2 AAA target.
 *
 * **Hard rules.**
 * 1. Every text token clears 7:1 contrast (WCAG SC 1.4.6) on every
 *    surface it can land on. Verify with `python audits/contrast_helper.py`.
 * 2. UMich Blue (#00274C) and Maize (#FFCB05) are pinned brand colors.
 *    Maize on white is ~1.7:1 — reserved for non-text accents on dark
 *    surfaces only.
 * 3. Color is never the only signal. Severity carries a text label;
 *    state carries an icon + label; the focus ring is a 3px outline,
 *    not just a color shift.
 *
 * **Severity colors were re-picked in Phase 2** to clear AAA on their
 * own tinted backgrounds. The previous `#B15A00` major / `#7A6700`
 * minor failed AA when placed on their bg tints (4.04:1 / 5.5:1). The
 * new dark-brown / dark-olive palette holds 8.9:1 / 9.3:1.
 *
 * **Focus ring** moved from translucent Maize to solid UMich Blue. The
 * old `rgba(255,203,5,0.55)` ring was ~1.7:1 against white — failed
 * SC 1.4.11. Solid Blue is 15:1 against white and the Maize fallback
 * (used on the dark sidebar) is 9.9:1 against UMich Blue.
 */
/** A colour token backed by a `--c-*` variable of space-separated RGB channels. */
const v = (name: string) => `rgb(var(--c-${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      // Every colour is a CSS variable (RGB channels), defined per theme and
      // contrast level in styles.css, so Settings can switch them at runtime
      // and `/opacity` modifiers keep working. The light values there are
      // the pinned ones documented above; change them there, not here.
      colors: {
        umich: {
          blue: v("umich-blue"),
          "blue-600": v("umich-blue-600"),
          "blue-700": v("umich-blue-700"),
          maize: v("umich-maize"),
          "maize-600": v("umich-maize-600"),
        },
        sev: {
          critical: v("sev-critical"),
          "critical-bg": v("sev-critical-bg"),
          major: v("sev-major"),
          "major-bg": v("sev-major-bg"),
          minor: v("sev-minor"),
          "minor-bg": v("sev-minor-bg"),
          info: v("sev-info"),
          "info-bg": v("sev-info-bg"),
        },
        ok: {
          DEFAULT: v("ok"),
          bg: v("ok-bg"),
        },
        surface: {
          DEFAULT: v("surface"),
          subtle: v("surface-subtle"),
          muted: v("surface-muted"),
          raised: v("surface-raised"),
          inverse: v("surface-inverse"),
          "inverse-fg": v("surface-inverse-fg"),
          "inverse-fg-subtle": v("surface-inverse-fg-subtle"),
        },
        border: {
          DEFAULT: v("border"),
          strong: v("border-strong"),
          focus: v("border-focus"),
        },
        fg: {
          DEFAULT: v("fg"),
          muted: v("fg-muted"),
          subtle: v("fg-subtle"),
          inverse: v("fg-inverse"),
          accent: v("fg-accent"),
        },
      },
      fontFamily: {
        // Atkinson Hyperlegible leads both stacks; see `src/fonts.css` for why
        // and for the offline constraint that makes it self-hosted. The system
        // stack stays behind it so the UI still renders if a font file 404s.
        // The stack itself is `--font-sans` in styles.css, so the Font
        // setting can swap it without touching a class.
        sans: ["var(--font-sans)"],
        // The "axcess" logo beside the brand mark, and nothing else (see
        // `src/fonts.css`). Not swapped by the Font setting: it is the logo.
        brand: ['"Comfortaa"', "var(--font-sans)"],
        mono: [
          '"Atkinson Hyperlegible Mono"',
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          '"Cascadia Code"',
          "monospace",
        ],
      },
      boxShadow: {
        card:
          "0 1px 2px rgba(0, 39, 76, 0.05), 0 6px 18px rgba(0, 39, 76, 0.045)",
        raised:
          "0 18px 42px rgba(0, 39, 76, 0.12), 0 4px 12px rgba(0, 39, 76, 0.08)",
        // Focus ring: solid UMich Blue (15:1 on white; SC 1.4.11 needs ≥3:1).
        // Use `shadow-focus-inverse` for elements on the dark sidebar.
        focus: "0 0 0 3px rgb(var(--c-umich-blue))",
        "focus-inverse": "0 0 0 3px rgb(var(--c-umich-maize))",
      },
      // The loading mark's crawl ring turns on its own axis. Spelled out here
      // rather than reusing Tailwind's `animate-spin` + an arbitrary
      // `[animation-duration:...]`, because `animate-spin` emits the
      // `animation` shorthand and would reset the duration depending on which
      // utility the sort happens to place last. 1.6s reads as patient rather
      // than urgent; the wait is usually a few seconds of backend boot.
      keyframes: {
        "spin-ring": {
          to: { transform: "rotate(360deg)" },
        },
        // The sort chip in a table header lands with a small pop when a
        // column is chosen, so the eye is drawn to what just changed. Used
        // behind `motion-safe:` only.
        "sort-pop": {
          from: { transform: "scale(0.7)", opacity: "0" },
          to: { transform: "scale(1)", opacity: "1" },
        },
      },
      animation: {
        "spin-ring": "spin-ring 1.6s linear infinite",
        "sort-pop": "sort-pop 180ms ease-out",
      },
      minHeight: {
        // WCAG 2.2 SC 2.5.5 AAA — every interactive target must be ≥44×44px.
        // Settings > Target size can raise `--target` to 52px.
        target: "var(--target, 44px)",
      },
      minWidth: {
        target: "var(--target, 44px)",
      },
      maxWidth: {
        // Running text no wider than about 75 characters a line: SC 1.4.8
        // Visual Presentation, Level AAA, asks for 80 or fewer. Put it on a
        // paragraph of help or explanation that would otherwise run the
        // width of a wide panel. Not on a whole area: a blanket cap on every
        // p, li and dd (the first fix) cut panels' coloured bands short and
        // squeezed values such as the Inspector's element locator. In em,
        // not ch: Atkinson Hyperlegible's zero is wide, so ch overshoots.
        measure: "35em",
      },
      borderRadius: {
        "2xs": "5px",
        xs: "8px",
      },
      // A 14px floor: no text in the app is smaller than `sm`. WCAG sets no
      // minimum size (SC 1.4.4 asks only that text survive 200% zoom), but
      // low-vision guidance converges on ~16px body text, and an
      // accessibility tool's readers are the people small text fails first.
      // `2xs` (was 11px, then 12px) and `xs` (was 12px, then 13px) held
      // about 240 uses of secondary text: hints, chips, captions, table
      // notes. Lifting the tokens raises every one at once rather than
      // editing each call site. The cost is that `2xs`, `xs` and `sm` are
      // now one size, so secondary text stands apart by colour and weight
      // (`text-fg-muted`, `font-semibold`), not by being smaller. Do not add
      // a smaller size back, and do not use an arbitrary one (text-[12px])
      // to get round the floor.
      //
      // Line height 1.5 (21px on 14px), not Tailwind's 1.25rem (1.43): SC
      // 1.4.8 Visual Presentation (Level AAA) asks for at least 1.5 within
      // paragraphs, and Siteimprove Alfa found 122 paragraphs of small text
      // below it (October 2026 AAA audit). Set on the tokens, so every hint,
      // caption and note gets it at once; the cost is one pixel per line.
      fontSize: {
        "2xs": ["0.875rem", { lineHeight: "1.3125rem" }], // 14px, was 12px
        xs: ["0.875rem", { lineHeight: "1.3125rem" }], // 14px, was 13px
        sm: ["0.875rem", { lineHeight: "1.3125rem" }], // 14px
      },
    },
  },
  plugins: [],
};

export default config;
