import { defineCollection } from "astro:content";
import { i18nLoader } from "@astrojs/starlight/loaders";
import { docsSchema, i18nSchema } from "@astrojs/starlight/schema";
import { repoDocsLoader } from "./loaders/repo-docs";

// The user guides come straight from the repo's docs/ folder (see the
// loader). Product pages are Astro pages in src/pages/ instead, because they
// are built from components and product data rather than prose.
export const collections = {
  docs: defineCollection({ loader: repoDocsLoader(), schema: docsSchema() }),
  // Plain-language replacements for a few of Starlight's own interface words
  // (src/content/i18n/en.json). The sidebar is named "Pages" so it does not
  // share the name "Main" with the header's navigation: two landmarks with
  // one name are hard to tell apart in a screen reader's landmark list.
  i18n: defineCollection({ loader: i18nLoader(), schema: i18nSchema() }),
};
