/** Shared constants for the public site. */

export const REPO = "https://github.com/lsa-mis/axcess";
export const RELEASES = `${REPO}/releases`;
// The only stable download address: release files carry the version in their
// names, so there is no fixed file link (docs/desktop-app.md). The download
// links start here and public/download.js swaps in the file for each system.
export const LATEST_RELEASE = `${RELEASES}/latest`;
export const ISSUES = `${REPO}/issues`;
export const DOCS_ON_GITHUB = `${REPO}/tree/main/docs`;

/** Prefix a site path with the base (`/axcess`). */
export function url(path: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  return `${base}${path}`;
}

/** Header links. Every page is also in the sidebar (astro.config.mjs). */
export const MAIN_NAV = [
  { label: "Documentation", href: "/docs/" },
  { label: "What it checks", href: "/coverage/" },
  { label: "Privacy", href: "/privacy/" },
] as const;

/** Product pages that are Astro pages rather than guides from docs/. */
export const PRODUCT_PAGES = [
  { href: "/", title: "Home" },
  { href: "/get-started/", title: "Get started" },
  { href: "/sign-in-scan/", title: "Scan a site behind a sign-in" },
  { href: "/how-it-works/", title: "How Axcess works" },
  { href: "/coverage/", title: "What Axcess checks" },
  { href: "/who-its-for/", title: "Who Axcess is for" },
  { href: "/privacy/", title: "Privacy and trust" },
  { href: "/faq/", title: "Questions" },
  { href: "/about/", title: "About Axcess" },
] as const;

/** Said wherever results are described (docs/plain-language.md rule 12). */
export const HONESTY =
  "Axcess gives you evidence to review. Its results can't prove WCAG conformance, legal compliance, or that a whole site is accessible, and they don't replace testing with people who use assistive technology.";
