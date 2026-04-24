import type { Config } from "tailwindcss";

/**
 * University of Michigan brand tokens.
 *
 * The two primaries (Maize #FFCB05, Blue #00274C) are non-negotiable;
 * tints and neutrals below are chosen to keep text/background pairings
 * above WCAG AA contrast. Maize-on-white fails contrast (~1.7:1), so it
 * is reserved for accents, highlights, and chart fills — never for body
 * text. Structural foreground uses Blue + neutral grays.
 */
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // U-M primary palette
        umich: {
          blue: "#00274C",
          "blue-600": "#003a6c", // lighter blue for hover on blue surfaces
          "blue-700": "#001e3c", // pressed
          maize: "#FFCB05",
          "maize-600": "#E6B704",
        },
        // Semantic severity tokens (stay a11y-clean: color is NEVER the only signal)
        sev: {
          critical: "#8B0000",
          "critical-bg": "#FEE2E2",
          major: "#B15A00",
          "major-bg": "#FEF3C7",
          minor: "#7A6700",
          "minor-bg": "#FEF9C3",
          info: "#1F2937",
          "info-bg": "#E5E7EB",
        },
        // Semantic surface tokens so components don't hardcode grays
        surface: {
          DEFAULT: "#FFFFFF",
          subtle: "#F9FAFB",
          muted: "#F3F4F6",
          raised: "#FFFFFF",
          inverse: "#00274C",
        },
        border: {
          DEFAULT: "#E5E7EB",
          strong: "#D1D5DB",
          focus: "#00274C",
        },
        fg: {
          DEFAULT: "#111827",
          muted: "#4B5563",
          subtle: "#6B7280",
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
        card: "0 1px 2px rgba(17, 24, 39, 0.06), 0 1px 1px rgba(17, 24, 39, 0.04)",
        raised:
          "0 4px 12px rgba(17, 24, 39, 0.08), 0 2px 4px rgba(17, 24, 39, 0.04)",
        focus: "0 0 0 3px rgba(255, 203, 5, 0.55)",
      },
      borderRadius: {
        "2xs": "3px",
        xs: "4px",
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
    },
  },
  plugins: [],
};

export default config;
