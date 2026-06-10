import type { Config } from "tailwindcss";

// Design tokens for the tracker. Same accessibility contract as the
// parent project: body text pairs clear 7:1, focus ring clears 3:1 on
// every surface, interactive targets get a 44px floor via min-h-target.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#111827",
        "ink-muted": "#3f4756",
        "ink-subtle": "#4b5563",
        paper: "#ffffff",
        "paper-muted": "#f3f4f6",
        line: "#d1d5db",
        brand: "#00274c",
        "brand-accent": "#ffcb05",
        "sev-critical": "#7a0000",
        "sev-serious": "#6b2e00",
        "sev-moderate": "#4f4200",
        "sev-minor": "#1f2937",
        "tier-automated": "#0b5345",
        "tier-ai": "#4b1d8a",
        "tier-agentic": "#27587f",
        "tier-manual": "#a2005a",
        "tier-vlm": "#5b21b6"
      },
      minHeight: {
        target: "44px"
      },
      boxShadow: {
        focus: "0 0 0 3px #ffffff, 0 0 0 6px #003f75"
      }
    },
  },
  plugins: [],
} satisfies Config;
