import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// No VITE_ API URL anywhere in this file, deliberately. Vite inlines
// import.meta.env at build time, which would bake an environment into the
// image and destroy build-once-deploy-many. The container reads its API base
// from /config.js at runtime instead (see ADR-0002).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: false, target: "es2022" },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    css: false,
  },
});
