// @ts-check
// The Axcess public site: product pages and the user documentation, built as
// static HTML by Astro + Starlight and published to GitHub Pages.
//
// Every page can be read and navigated without JavaScript. Search and the
// light or dark switch need it. The overrides in src/overrides/ and the rules
// in src/styles/theme.css keep that promise; tests/public_site/ checks it with
// scripts turned off.
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

const REPO = "https://github.com/lsa-mis/axcess";

export default defineConfig({
  site: "https://lsa-mis.github.io",
  base: "/axcess",
  trailingSlash: "always",
  integrations: [
    starlight({
      title: "Axcess",
      description:
        "A free accessibility scanner that runs on your computer. It tests the pages behind your sign-in, opens menus and dialogs, and keeps the evidence on your machine.",
      favicon: "/favicon.svg",
      // No "Built with Starlight" line: the footer already names who built
      // Axcess, and a second credit is noise (COGA, one idea per chunk).
      credits: false,
      social: [{ icon: "github", label: "Axcess on GitHub", href: REPO }],
      editLink: { baseUrl: `${REPO}/edit/main/` },
      customCss: ["./src/styles/fonts.css", "./src/styles/theme.css"],
      // Code in the guides: GitHub's high-contrast themes, because the
      // default themes' token colours fall below 7:1 (SC 1.4.6 Contrast
      // (Enhanced), Level AAA, which the site meets everywhere else). Long
      // lines wrap instead of scrolling, so there is no scroll area the
      // keyboard can't reach (SC 2.1.1 Keyboard, Level A) and nothing to
      // scroll sideways at 320 px or when zoomed in (SC 1.4.10 Reflow).
      expressiveCode: {
        themes: ["github-dark-high-contrast", "github-light-high-contrast"],
        // Even those themes have a few colours (comments) under 7:1; this
        // lightens or darkens any token colour until it reaches 7:1.
        minSyntaxHighlightingColorContrast: 7,
        defaultProps: { wrap: true, preserveIndent: true },
      },
      components: {
        Header: "./src/overrides/Header.astro",
        SiteTitle: "./src/overrides/SiteTitle.astro",
        Search: "./src/overrides/Search.astro",
        Footer: "./src/overrides/Footer.astro",
        ThemeProvider: "./src/overrides/ThemeProvider.astro",
        Hero: "./src/overrides/Hero.astro",
      },
      // One list for every page, product and documentation alike, grouped by
      // what the reader is trying to do (COGA "Making Content Usable":
      // related content grouped). Labels follow docs/plain-language.md.
      sidebar: [
        {
          label: "Start here",
          items: [
            { label: "Download and install", link: "/get-started/" },
            { label: "How Axcess works", link: "/how-it-works/" },
            { label: "Using the desktop app", link: "/docs/desktop-app/" },
          ],
        },
        {
          label: "Use Axcess",
          items: [
            { label: "Reading your report", link: "/docs/reading-your-report/" },
            { label: "Scanning search-driven sites", link: "/docs/spa-search-scans/" },
            { label: "Troubleshooting", link: "/docs/troubleshooting/" },
          ],
        },
        {
          label: "Run it for a team",
          items: [{ label: "Hosting Axcess", link: "/docs/hosting/" }],
        },
        {
          label: "What it checks",
          items: [
            { label: "What Axcess checks", link: "/coverage/" },
            { label: "Coverage and feature tracker", link: "/docs/coverage-tracker/" },
          ],
        },
        {
          label: "Reference",
          items: [
            { label: "Questions", link: "/faq/" },
            { label: "Glossary", link: "/docs/glossary/" },
            { label: "All documentation", link: "/docs/" },
            { label: "All pages", link: "/all-pages/" },
          ],
        },
        {
          label: "About Axcess",
          items: [
            { label: "Who it's for", link: "/who-its-for/" },
            { label: "Privacy and trust", link: "/privacy/" },
            { label: "About", link: "/about/" },
          ],
        },
      ],
    }),
  ],
});
