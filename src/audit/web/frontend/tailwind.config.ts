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
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // U-M primary palette (pinned — do not change without brand sign-off)
        umich: {
          blue: "#00274C",
          "blue-600": "#003a6c", // lighter blue for hover on blue surfaces
          "blue-700": "#001e3c", // pressed
          maize: "#FFCB05",
          "maize-600": "#E6B704",
        },
        // Semantic severity tokens — Phase 2 AAA-clean re-pick.
        // Text color is paired with its bg-tint to hold ≥7:1.
        sev: {
          critical: "#7A0000", // 9.41:1 on critical-bg, 11.49:1 on white
          "critical-bg": "#FEE2E2",
          major: "#6B2E00", // 8.91:1 on major-bg, 10.42:1 on white
          "major-bg": "#FFEBC7", // slightly lighter than the old #FEF3C7 to lift the ratio
          minor: "#4F4200", // 9.26:1 on minor-bg, 9.94:1 on white
          "minor-bg": "#FEF9C3",
          info: "#1F2937", // 11.86:1 on info-bg
          "info-bg": "#E5E7EB",
        },
        // Semantic surface tokens so components don't hardcode grays
        surface: {
          DEFAULT: "#FFFFFF",
          // Cool, quiet neutrals give the evidence-heavy workspace clear
          // depth without competing with U-M blue or severity signals.
          subtle: "#F7F9FC",
          muted: "#F1F4F8",
          raised: "#FFFFFF",
          inverse: "#00274C",
          // Sidebar-specific text colors so dark-on-blue pairs stay AAA.
          "inverse-fg": "#FFFFFF", // 15:1 on UMich Blue
          "inverse-fg-subtle": "#C9D4E0", // 10.02:1 on UMich Blue
        },
        border: {
          DEFAULT: "#DCE3EC",
          strong: "#B8C4D2",
          focus: "#00274C",
        },
        fg: {
          DEFAULT: "#111827", // 17.74:1 on white
          muted: "#374151", // 10.31:1 on white, 9.37:1 on muted (was #4B5563 — still AAA but tightened)
          subtle: "#475263", // 7.91:1 on white, 7.19:1 on muted (was #6B7280 — failed AAA)
          inverse: "#FFFFFF",
          accent: "#00274C",
        },
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Roboto",
          '"Helvetica Neue"',
          "Arial",
          "sans-serif",
        ],
        mono: [
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
        focus: "0 0 0 3px #00274C",
        "focus-inverse": "0 0 0 3px #FFCB05",
      },
      minHeight: {
        // WCAG 2.2 SC 2.5.5 AAA — every interactive target must be ≥44×44px.
        target: "44px",
      },
      minWidth: {
        target: "44px",
      },
      borderRadius: {
        "2xs": "5px",
        xs: "8px",
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
    },
  },
  plugins: [],
};

export default config;
