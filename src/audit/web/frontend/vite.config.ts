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
  },
}));
