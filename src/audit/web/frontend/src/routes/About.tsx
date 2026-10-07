import { ExternalLink, Info } from "lucide-react";
import BrandMark from "../components/BrandMark";
import { isDesktopApp } from "../hooks/useSwipeNavigation";
import { CLICK_THROUGH } from "../lib/labels";

/**
 * One outbound resource. ``display`` is the short address printed on the
 * card, so a reader can see where a link goes before following it; the
 * ``href`` is the full URL.
 */
interface Resource {
  title: string;
  description: string;
  href: string;
  display: string;
}

const SITE = "https://lsa-mis.github.io/axcess";
const REPO = "https://github.com/lsa-mis/axcess";

const RESOURCES: Resource[] = [
  {
    title: "Axcess website",
    description: "Overview of the product, who it's for, and how an audit runs from scan to report.",
    href: `${SITE}/`,
    display: "lsa-mis.github.io/axcess",
  },
  {
    title: "How it works",
    description: "The crawl, the detection layers, and how findings become issue groups.",
    href: `${SITE}/how-it-works/`,
    display: "/axcess/how-it-works",
  },
  {
    title: "Product roadmap",
    description:
      "What Axcess checks for each WCAG 2.2 criterion today, what's planned, and what you still check yourself.",
    href: `${REPO}/blob/main/docs/coverage-tracker.md`,
    display: "docs/coverage-tracker.md",
  },
  {
    title: "Documentation",
    description: "Setup, desktop app, hosting, architecture, and every detection method in detail.",
    href: `${REPO}/tree/main/docs`,
    display: "github.com/lsa-mis/axcess/docs",
  },
  {
    title: "Privacy and data",
    description:
      "What's stored on this computer, what's never uploaded, and how protected scans are handled.",
    href: `${SITE}/privacy/`,
    display: "/axcess/privacy",
  },
  {
    title: "GitHub repository",
    description: "Source code, issues, and release notes. Contributions welcome.",
    href: REPO,
    display: "github.com/lsa-mis/axcess",
  },
  {
    title: "Download desktop builds",
    description: "The latest macOS and Windows preview builds.",
    href: `${SITE}/get-started/`,
    display: "/axcess/get-started",
  },
  {
    title: "FAQ",
    description: `Common questions, plus a glossary of terms like ${CLICK_THROUGH} and ACT rule.`,
    href: `${SITE}/faq/`,
    display: "/axcess/faq",
  },
];

/**
 * What Axcess is, what its results mean, and where to read more.
 *
 * Every link here leaves the app, so each card says so in its accessible
 * name and none of them carries anything about the current scan: they are
 * static public pages, opened only when someone clicks one.
 */
export default function AboutRoute() {
  const build = `${isDesktopApp() ? "Desktop preview" : "Preview"} ${__APP_VERSION__}`;
  return (
    <div className="space-y-8">
      <header className="flex items-start gap-4">
        <BrandMark className="mt-0.5 h-14 w-14 text-umich-blue" />
        <div className="min-w-0 max-w-4xl">
          <h1 className="text-2xl font-semibold leading-tight tracking-[-0.025em] text-fg sm:text-[1.75rem]">
            About Axcess
          </h1>
          <p className="mt-2 text-lg text-fg">
            A local-first accessibility evidence workbench for expert web audits.
          </p>
          <p className="mt-3 max-w-measure text-sm leading-6 text-fg-muted">
            Scan a public or login-protected website, watch each test run, review a clear
            issue table, and export a report backed by source-level evidence. Each result
            keeps the detection method that found it (axe-core, Siteimprove Alfa, keyboard,
            responsive and focus probes, image-of-text OCR, {CLICK_THROUGH}), so no
            engine&rsquo;s verdict is hidden inside another&rsquo;s.
          </p>
          <ul className="mt-4 flex flex-wrap gap-2" aria-label="At a glance">
            {["WCAG 2.2 A/AA evidence", "Local by default", "MIT license", build].map(
              (fact) => (
                <li
                  key={fact}
                  className="rounded-full border border-border bg-surface px-3 py-1 text-xs font-semibold text-fg"
                >
                  {fact}
                </li>
              ),
            )}
          </ul>
        </div>
      </header>

      <div
        role="note"
        className="flex items-start gap-3 rounded-xs border border-l-4 border-border border-l-umich-blue bg-surface px-5 py-4 text-sm leading-6 text-fg"
      >
        <Info className="mt-1 h-4 w-4 shrink-0 text-fg-muted" aria-hidden />
        <p className="max-w-measure">
          <strong>Evidence, not a verdict.</strong> Automated and AI-assisted results do not
          prove WCAG conformance, legal compliance, or the accessibility of a whole website.
          They are evidence for an expert to review.
        </p>
      </div>

      <section aria-labelledby="about-learn-more">
        <h2 id="about-learn-more" className="mb-4 text-lg font-semibold text-fg">
          Learn more
        </h2>
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
          {RESOURCES.map((resource) => (
            <li key={resource.href}>
              <ResourceCard resource={resource} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

/**
 * The whole card is the click target, but the link itself is only the title:
 * its ``after:`` overlay stretches the hit area over the card, so the
 * accessible name stays the short title rather than the title, description
 * and address run together.
 */
function ResourceCard({ resource }: { resource: Resource }) {
  return (
    <div className="relative flex h-full flex-col rounded-xs border border-border bg-surface p-4 shadow-card transition-[border-color,box-shadow] focus-within:ring-2 focus-within:ring-umich-blue hover:border-umich-blue/40 hover:shadow-[0_4px_16px_rgba(0,39,76,0.10)]">
      <h3 className="flex items-start justify-between gap-3 text-sm font-semibold text-fg">
        <a
          href={resource.href}
          target="_blank"
          rel="noopener noreferrer"
          className="no-underline outline-none after:absolute after:inset-0 after:content-[''] hover:underline hover:underline-offset-2"
        >
          {resource.title}
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
        <ExternalLink className="h-4 w-4 shrink-0 text-fg-muted" aria-hidden />
      </h3>
      <p className="mt-2 flex-1 text-sm leading-6 text-fg-muted">{resource.description}</p>
      <p className="mt-3 truncate font-mono text-xs text-fg-muted">{resource.display}</p>
    </div>
  );
}
