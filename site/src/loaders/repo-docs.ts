/**
 * Loads the user guides from the repo's `docs/` folder into Starlight's
 * `docs` collection, so `docs/` stays the single source: the same files read
 * correctly on GitHub and on the site, and nothing is copied.
 *
 * Starlight's own `docsLoader()` only reads `src/content/docs/`, and the
 * guides have no frontmatter (GitHub would render it as a table), so this
 * loader:
 *
 * - takes each page's title from its first `# ` heading and removes that
 *   heading from the body, because Starlight prints the title as the H1;
 * - rewrites links between guides to site routes, and links to other repo
 *   files (`../src/...`, `internal/...`) to GitHub, so none break;
 * - wraps each table in a scroll area that takes keyboard focus and is named
 *   after the heading above it. At 320 px a wide table scrolls sideways,
 *   which SC 1.4.10 Reflow (Level AA) allows for data tables, but only a
 *   focusable area can be scrolled from the keyboard (SC 2.1.1 Keyboard,
 *   Level A); the name tells a screen reader what it has landed on;
 * - drops a hand-written "## On this page" list, because Starlight already
 *   shows one from the headings and two lists of the same links is one too
 *   many (COGA: no duplicate controls for one function). GitHub readers
 *   still get the hand-written list.
 *
 * `docs/internal/`, `docs/ux/`, the pointer stubs and the contributor style
 * guide are left out on purpose: they are for people who build Axcess.
 */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Loader } from "astro/loaders";

const REPO = "https://github.com/lsa-mis/axcess";
// The site's base: /axcess live, /axcess/staging for the testers' copy
// (astro.config.mjs reads the same variable).
const BASE = process.env.AXCESS_SITE_BASE ?? "/axcess";
const LIVE = "https://lsa-mis.github.io/axcess/";

/** File name (no extension) -> route id under the site's base. */
export const GUIDES: Record<string, string> = {
  README: "docs",
  "desktop-app": "docs/desktop-app",
  "reading-your-report": "docs/reading-your-report",
  troubleshooting: "docs/troubleshooting",
  hosting: "docs/hosting",
  "spa-search-scans": "docs/spa-search-scans",
  glossary: "docs/glossary",
  "coverage-tracker": "docs/coverage-tracker",
};

/**
 * One sentence per guide, for search results and link previews (the page's
 * meta description). The guides have no frontmatter to hold it (see above),
 * so it lives here, beside the list of guides. Without it every guide showed
 * the site's own description, so eight different search results read the
 * same and nobody could tell which guide answers their question. Plain
 * language, in the terms table's words (docs/plain-language.md), and true to
 * what each guide covers: update the sentence when a guide's contents change.
 * A guide without one stops the build, so a new guide cannot fall back to
 * the site's description unnoticed.
 */
export const DESCRIPTIONS: Record<string, string> = {
  README:
    "Every Axcess guide in one list: reading a report, fixing common problems, scanning search-driven sites, hosting Axcess for a team, and the glossary.",
  "desktop-app":
    "The Axcess desktop app for Mac, Windows and Linux: where it keeps your reports, how updates arrive, and how to build an installer yourself.",
  "reading-your-report":
    "How to read an Axcess report: the summary, the Issues table, the evidence for each occurrence, recording decisions, exports, and comparing reports after a fix.",
  troubleshooting:
    "Fixes for common problems: a scan that stops at one page, scans that are too big, too small or slow, the sign-in window, the local AI checks, and starting over.",
  hosting:
    "How to run Axcess on an always-on computer for a small team, on your own network or over Tailscale, behind a shared access token.",
  "spa-search-scans":
    "How Axcess scans sites whose pages appear only after a search or a click: Click-Through, its limits, the controls it skips, and configured searches.",
  glossary:
    "What the words in Axcess and its reports mean, in plain language: issue, occurrence, page state, Mostly sure, Not sure and more.",
  "coverage-tracker":
    "Which WCAG 2.2 A and AA criteria Axcess checks and how, how each check collects evidence, and what is planned next.",
};

const LINK = /(\]\()([^)\s]+)(\))/g;

/** Rewrite one Markdown link target found in `docs/<file>.md`. */
export function rewriteTarget(target: string): string {
  // Links to the published site from a guide become site paths, so they
  // stay on whichever copy (local preview or live) the reader is using.
  if (target.startsWith(LIVE)) return `${BASE}/${target.slice(LIVE.length)}`;
  if (/^(https?:|mailto:|#)/.test(target)) return target;
  const [file, hash = ""] = target.split("#");
  // Diagrams: the site serves its own copies (site/public/diagrams/, see
  // CONTRIBUTING.md), so pages never load images from another site.
  if (file.startsWith("images/diagrams/")) return `${BASE}/diagrams/${path.posix.basename(file)}`;
  const anchor = hash ? `#${hash}` : "";
  const name = path.posix.basename(file, ".md");
  const inDocsRoot = path.posix.normalize(path.posix.join("docs", file)).split("/").length === 2;
  if (file.endsWith(".md") && inDocsRoot && name in GUIDES) {
    return `${BASE}/${GUIDES[name]}/${anchor}`;
  }
  // Anything else lives in the repo, not on the site: point at GitHub.
  const repoPath = path.posix.normalize(path.posix.join("docs", file));
  const kind = repoPath.endsWith("/") || !path.posix.extname(repoPath) ? "tree" : "blob";
  return `${REPO}/${kind}/main/${repoPath}${anchor}`;
}

export function splitTitle(markdown: string): { title: string; body: string } {
  const match = markdown.match(/^#\s+(.+)\n/m);
  if (!match || match.index === undefined) throw new Error("guide has no '# ' title");
  const body = markdown.slice(0, match.index) + markdown.slice(match.index + match[0].length);
  return { title: match[1].trim(), body: body.trimStart() };
}

export function wrapTables(html: string): string {
  let out = "";
  let last = 0;
  let heading = "";
  const re = /<h([2-4])[^>]*>([\s\S]*?)<\/h\1>|<table>([\s\S]*?)<\/table>/g;
  for (let m = re.exec(html); m; m = re.exec(html)) {
    if (m[2] !== undefined) {
      heading = m[2].replace(/<[^>]+>/g, "").trim();
      continue;
    }
    const name = (heading ? `Table: ${heading}` : "Table").replace(/"/g, "&quot;");
    out += html.slice(last, m.index);
    out += `<div class="ax-table-scroll" role="region" tabindex="0" aria-label="${name}">${m[0]}</div>`;
    last = m.index + m[0].length;
  }
  return out + html.slice(last);
}

export function dropContentsList(markdown: string): string {
  return markdown.replace(/^## On this page\n[\s\S]*?(?=^## )/m, "");
}

export function repoDocsLoader(): Loader {
  return {
    name: "axcess-repo-docs",
    async load({ config, store, parseData, renderMarkdown, generateDigest, watcher, logger }) {
      const docsDir = fileURLToPath(new URL("../docs/", config.root));

      async function loadOne(name: string) {
        const file = path.join(docsDir, `${name}.md`);
        const raw = await fs.readFile(file, "utf-8");
        const { title, body } = splitTitle(raw);
        const rewritten = dropContentsList(body).replace(LINK, (_m, open, target, close) => open + rewriteTarget(target) + close);
        const id = GUIDES[name];
        const description = DESCRIPTIONS[name];
        if (!description) throw new Error(`docs/${name}.md has no description in DESCRIPTIONS`);
        const data = await parseData({
          id,
          data: { title, description, editUrl: `${REPO}/edit/main/docs/${name}.md` },
        });
        store.set({
          id,
          data,
          body: rewritten,
          filePath: path.relative(fileURLToPath(config.root), file),
          digest: generateDigest(raw),
          rendered: await renderMarkdown(rewritten).then((r) => ({ ...r, html: wrapTables(r.html) })),
        });
      }

      store.clear();
      for (const name of Object.keys(GUIDES)) await loadOne(name);
      logger.info(`loaded ${Object.keys(GUIDES).length} guides from docs/`);

      watcher?.add(docsDir);
      watcher?.on("change", async (changed) => {
        const name = path.basename(changed, ".md");
        if (path.dirname(changed) === path.resolve(docsDir) && name in GUIDES) await loadOne(name);
      });
    },
  };
}
