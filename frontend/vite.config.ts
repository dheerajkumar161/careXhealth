import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API is proxied so the httpOnly session cookie stays same-origin (no CORS / token storage in the browser).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
  preview: {
    port: 4173,
    proxy: { "/api": { target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
