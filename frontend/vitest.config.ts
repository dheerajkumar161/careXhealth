import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";

// Kept separate from vite.config.ts: vitest ships its own vite typings, which conflict with the app's vite plugins.
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: { environment: "jsdom", include: ["src/**/*.test.ts?(x)"] },
});
