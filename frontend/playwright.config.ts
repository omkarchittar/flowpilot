import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  expect: { timeout: 20000 },
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:3101",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1050 },
      },
    },
  ],
  webServer: [
    {
      command: "../backend/.venv/bin/python tests/serve_backend.py",
      url: "http://127.0.0.1:18081/health/ready",
      reuseExistingServer: false,
      timeout: 60000,
      gracefulShutdown: { signal: "SIGTERM", timeout: 10000 },
    },
    {
      command: "npm run serve:e2e",
      url: "http://127.0.0.1:3101/login",
      reuseExistingServer: false,
      timeout: 120000,
      gracefulShutdown: { signal: "SIGTERM", timeout: 10000 },
    },
  ],
});
