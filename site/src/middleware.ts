/**
 * Marks the first use of each abbreviation in a page's main content with its
 * full form (lib/abbreviations.ts; SC 3.1.4 Abbreviations, Level AAA).
 *
 * Middleware, so one step covers the product pages (Astro) and the guides
 * (docs/*.md) alike, at build time and in the dev server. Only the text
 * inside <main> is changed: the header, sidebar and page contents list are
 * navigation, and a dotted underline there would be noise.
 */
import { defineMiddleware } from "astro:middleware";
import { abbreviate } from "./lib/abbreviations";

export const onRequest = defineMiddleware(async (_context, next) => {
  const response = await next();
  if (!(response.headers.get("content-type") ?? "").includes("text/html")) return response;
  const html = await response.text();
  const start = html.indexOf("<main");
  const end = html.lastIndexOf("</main>");
  const body = start < 0 || end < 0 ? html : html.slice(0, start) + abbreviate(html.slice(start, end)) + html.slice(end);
  return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
});
