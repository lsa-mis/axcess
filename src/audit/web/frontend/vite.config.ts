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
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/blobs": "http://127.0.0.1:8765",
      "/scans": "http://127.0.0.1:8765", // export downloads
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
}));
