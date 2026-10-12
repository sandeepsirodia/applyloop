import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev server proxies /api and /screens and /ghosted to the Python backend (applyloop ui --port 8765),
// so the React app talks to the real API with no CORS setup needed, in dev or in the built production app
// (which the Python server serves directly from web/dist).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "./src") } },
  // Builds straight into the Python package itself (not a sibling directory), so the built frontend
  // travels with the package under *any* install method (editable, a plain `pip install .`, a wheel) --
  // not only when run from a source checkout where `web/` happens to sit next to `applyloop/`.
  build: { outDir: "../applyloop/web_dist", emptyOutDir: true },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/screens": "http://127.0.0.1:8765",
      "/ghosted": "http://127.0.0.1:8765",
    },
  },
});
