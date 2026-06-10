import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local-first single page app. No backend: the data layer persists to
// localStorage (see src/data/store.ts), so `vite preview` of the built
// bundle is a complete offline deployment.
export default defineConfig({
  plugins: [react()],
  server: { port: 4316 },
  test: {
    environment: "jsdom",
    globals: false,
  },
});
