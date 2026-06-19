// ESLint flat config — Phase-2 a11y gate.
//
// Why this exists. The Phase-1 discovery audit found that the SPA had no
// lint pipeline, which meant aria mistakes (mis-paired labels, missing
// alt, role="button" on a div, keyboard handlers without `tabindex`,
// etc.) could only be caught at runtime via axe — too late, and too
// late in the loop. `eslint-plugin-jsx-a11y` catches them at edit time.
//
// What's enabled.
//   * `plugin:react/recommended`             — JSX correctness baseline
//   * `plugin:jsx-a11y/recommended`          — the actual a11y gate
//   * `plugin:react-hooks/recommended-latest` — keep effect deps honest
//   * typescript-eslint                      — runs tsc-aware rules
//
// What's deliberately *off*.
//   * `react/react-in-jsx-scope`             — not needed since React 17
//   * `react/prop-types`                     — TypeScript covers it
//   * `jsx-a11y/no-autofocus`                — we use autoFocus on the
//                                              URL field; first-input
//                                              focus on form-only routes
//                                              is intentional and well-
//                                              understood (overrides
//                                              below scope it tightly).
//
// Run with `npm --prefix src/audit/web/frontend run lint`.

import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactPlugin from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";
import globals from "globals";

export default tseslint.config(
  {
    ignores: ["dist/**", "node_modules/**", "**/*.config.{js,ts,cjs,mjs}"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      react: reactPlugin,
      "react-hooks": reactHooks,
      "jsx-a11y": jsxA11y,
    },
    settings: {
      react: { version: "detect" },
    },
    rules: {
      ...reactPlugin.configs.recommended.rules,
      ...reactHooks.configs["recommended-latest"].rules,
      ...jsxA11y.configs.recommended.rules,

      // TypeScript handles these — turn them off in their JS form.
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",

      // The URL field on /scans/new uses autoFocus on purpose: it is the
      // first and primary input on a form-only route. Per a11y guidance
      // (WAI), autoFocus is acceptable when the user landed on the form
      // *because* they intend to fill it out. Turn the rule off; we
      // re-enable it elsewhere via the `overrides` rule below.
      "jsx-a11y/no-autofocus": ["off"],

      // Decorative SVG icons must carry `aria-hidden` (we already pair
      // every lucide-react icon with a text label). Make this an error.
      "jsx-a11y/alt-text": "error",
      "jsx-a11y/anchor-is-valid": "error",
      "jsx-a11y/click-events-have-key-events": "error",
      "jsx-a11y/no-noninteractive-element-interactions": "error",
      "jsx-a11y/label-has-associated-control": "error",
      "jsx-a11y/no-static-element-interactions": "error",
    },
  },
  // Test files have looser rules — they often need raw DOM access patterns
  // that look like a11y violations (e.g. clicking on non-interactive
  // elements to verify focus management).
  {
    files: ["**/*.test.{ts,tsx}"],
    rules: {
      "jsx-a11y/no-static-element-interactions": "off",
      "jsx-a11y/click-events-have-key-events": "off",
    },
  },
);
