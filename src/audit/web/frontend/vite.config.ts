import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server runs on 5173; proxy /api and /blobs to FastAPI on :8765 so the
// SPA talks to the real backend without CORS. Production build is served
// by FastAPI directly from dist/ under /app/.
//
// Using the function form (instead of a bare object) lets us branch on
// `command` without reaching for `process.env`, which would require
// @types/node — unnecessary for a browser-only bundle.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  // Bundle served from /app/ in production; Vite dev server stays at /.
  base: command === "build" ? "/app/" : "/",
  server: {
    port: 5173,
    // Let a Cloudflare quick tunnel (cloudflared tunnel --url http://localhost:5173)
    // reach the dev server; Vite rejects unknown Host headers otherwise.
    allowedHosts: [".trycloudflare.com"],
    proxy: {
      // `changeOrigin: false` keeps the browser's Host header on the
      // forwarded request. Vite's string shorthand rewrites Host to the
      // target, and the backend's login-scan guard requires the request's
      // Origin and Host to name the same local authority — with the rewrite
      // every POST /api/local-login-scans from the dev server was a 403.
      "/api": { target: "http://127.0.0.1:8765", changeOrigin: false },
      "/blobs": { target: "http://127.0.0.1:8765", changeOrigin: false },
      // Export downloads only. A page load of an app route under /scans
      // (a reload on /scans/new, a pasted link) must reach Vite's index,
      // not the backend, which has no such page and answers 404.
      "/scans": {
        target: "http://127.0.0.1:8765",
        changeOrigin: false,
        bypass: (req) => (req.headers.accept?.includes("text/html") ? req.url : undefined),
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        // Split the parts that change on their own schedule from the parts
        // that change whenever the app does. Everything used to land in one
        // 348 kB entry chunk, so editing a route invalidated React in every
        // reader's cache and the browser could not start fetching the
        // framework and the app shell at the same time.
        //
        // The react ecosystem stays in one chunk. Splitting the data layer
        // out from react produced a circular chunk dependency, because
        // Rollup hoists the modules they share; a cycle between chunks can
        // leave a module uninitialized at import time, which is a worse
        // problem than a slightly larger vendor file.
        //
        // The icon set is a genuinely separate leaf, so it splits cleanly.
        // Matched on the resolved module path rather than a list of bare
        // specifiers, because the app imports `react-dom/client`, which a
        // bare "react-dom" entry does not catch: react-dom then stayed in
        // the entry chunk, which was most of what needed splitting out.
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("lucide-react")) return "vendor-icons";
          if (/[\\/]node_modules[\\/](react|react-dom|react-router|scheduler|@tanstack)[\\/]/.test(id)) {
            return "vendor";
          }
          return undefined;
        },
      },
    },
  },
}));
