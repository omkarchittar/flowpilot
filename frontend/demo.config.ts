import { defineConfig } from "@playwright/test";
import base from "./playwright.config";
export default defineConfig({
  ...base,
  testDir: "./demos",
  timeout: 120000,
  reporter: "list",
  use: { ...base.use, viewport: { width: 1280, height: 850 } },
  projects: [{ name: "demo" }],
});
