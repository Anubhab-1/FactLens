import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:4175",
    trace: "on-first-retry",
  },
  webServer: {
    command: "npx vite --port 4175",
    url: "http://localhost:4175",
    reuseExistingServer: true,
    timeout: 120000,
  },
  outputDir: "playwright-results",
});
