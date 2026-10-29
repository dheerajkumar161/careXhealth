import { defineConfig } from "@playwright/test";

// End-to-end smoke tests against a throw-away backend (seeded DB, rule engine, no LLM) + the Vite dev server.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1, // one shared seeded database
  use: { baseURL: "http://127.0.0.1:5173", trace: "retain-on-failure" },
  webServer: [
    {
      command: process.env.E2E_BACKEND_CMD ?? "cd ../backend && python scripts/e2e_server.py",
      url: "http://127.0.0.1:8000/api/ready",
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
    },
    { command: "npm run dev -- --host 127.0.0.1", url: "http://127.0.0.1:5173", timeout: 60_000, reuseExistingServer: !process.env.CI },
  ],
});
