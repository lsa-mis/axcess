/**
 * Gives the first use of each abbreviation on a page its full form, as an
 * <abbr title="..."> (WCAG technique H28 for SC 3.1.4 Abbreviations, Level
 * AAA). Run on every page's main content by src/middleware.ts.
 *
 * Why one list for the whole site: the guides come from docs/*.md, which
 * are also read on GitHub, and with the product pages they hold about 70
 * abbreviations (CSV, DOM, WSL, HMAC...). Expanding each by hand in the
 * source would bury the developer docs in parentheses; one list keeps the
 * expansions consistent and in one place. A Markdown plugin was tried
 * first, but Astro 7's default Markdown engine runs plugins only with an
 * extra package installed, and it would not reach the Astro pages. Only
 * the first use on a page is marked, so a page does not fill with dotted
 * underlines. Text in code, keyboard keys and an existing <abbr> is left
 * alone, so commands and file names never change; tags pass through
 * untouched.
 *
 * Known limit: a title shows on hover, and screen readers read it only in
 * some settings, so a keyboard or touch reader may not see it. Where a term
 * matters to the reader, the docs still spell it out in the text ("Windows
 * Subsystem for Linux (WSL)") or link to the glossary.
 */

/** Abbreviation -> its full form, in plain words. Add new ones here. */
export const ABBREVIATIONS: Record<string, string> = {
  ACR: "Accessibility Conformance Report",
  ACT: "Accessibility Conformance Testing (a W3C format for test rules)",
  ADA: "Americans with Disabilities Act",
  AI: "artificial intelligence",
  API: "application programming interface",
  ARIA: "Accessible Rich Internet Applications (attributes that describe page parts to assistive technology)",
  ASAR: "Atom Shell Archive (the file that holds an Electron app's code)",
  CLI: "command-line interface",
  CPU: "central processing unit (the computer's processor)",
  CSS: "Cascading Style Sheets",
  CSV: "comma-separated values (a spreadsheet text file)",
  DEB: "Debian package (a Linux install file)",
  DMG: "Apple disk image (a macOS install file)",
  DOM: "Document Object Model (the page code a browser builds)",
  FAQ: "frequently asked questions",
  GPU: "graphics processing unit",
  HMAC: "hash-based message authentication code",
  HTML: "HyperText Markup Language (the language web pages are written in)",
  HTTP: "Hypertext Transfer Protocol",
  HTTPS: "Hypertext Transfer Protocol Secure",
  ICNS: "Apple icon image file",
  IP: "Internet Protocol",
  IT: "information technology",
  ITS: "Information and Technology Services",
  JAWS: "Job Access With Speech (a screen reader)",
  JSON: "JavaScript Object Notation (a data file format)",
  JTI: "JSON Web Token ID (a sign-in token's unique number)",
  KMS: "key management service",
  LAN: "local area network",
  LLM: "large language model (an AI model that reads text)",
  LSA: "College of Literature, Science, and the Arts",
  MFA: "multi-factor authentication",
  MIT: "Massachusetts Institute of Technology (the MIT License)",
  NSIS: "Nullsoft Scriptable Install System (the Windows installer maker)",
  NVDA: "NonVisual Desktop Access (a screen reader)",
  OCR: "optical character recognition (reading text in images)",
  OS: "operating system",
  PNG: "Portable Network Graphics (an image file)",
  RPM: "Red Hat package manager file (a Linux install file)",
  SHA: "Secure Hash Algorithm",
  SPA: "single-page application",
  SSH: "Secure Shell",
  SSL: "Secure Sockets Layer",
  SVG: "Scalable Vector Graphics",
  UI: "user interface",
  URL: "web address (Uniform Resource Locator)",
  USB: "Universal Serial Bus",
  VLM: "vision language model (an AI model that looks at images)",
  W3C: "World Wide Web Consortium",
  WAL: "write-ahead log",
  WCAG: "Web Content Accessibility Guidelines",
  WSL: "Windows Subsystem for Linux",
  XLSX: "Excel workbook file",
  YAML: "YAML Ain't Markup Language (a settings file format)",
};

const SKIP = new Set(["code", "pre", "kbd", "samp", "abbr", "script", "style", "svg", "title"]);
const TERM = new RegExp(`\\b(${Object.keys(ABBREVIATIONS).join("|")})\\b`, "g");

/** The guide's HTML with the first use of each listed abbreviation wrapped. */
export function abbreviate(html: string): string {
  const seen = new Set<string>();
  let skip = 0;
  return html
    .split(/(<[^>]+>)/)
    .map((part) => {
      if (part.startsWith("<")) {
        const tag = /^<(\/?)([a-zA-Z0-9]+)/.exec(part);
        if (tag && SKIP.has(tag[2].toLowerCase()) && !part.endsWith("/>")) skip += tag[1] ? -1 : 1;
        return part;
      }
      if (skip > 0) return part;
      return part.replace(TERM, (term: string) => {
        if (seen.has(term)) return term;
        seen.add(term);
        return `<abbr title="${ABBREVIATIONS[term].replace(/"/g, "&quot;")}">${term}</abbr>`;
      });
    })
    .join("");
}
