import { defineConfig, devices } from "@playwright/test";

// The smoke test runs its own mock-mode backend on 8001 and a second Vite on
// 5174, so it never touches a live console that may be open on 5173 / 8000.
const BACKEND = "http://127.0.0.1:8001";
const FRONTEND = "http://127.0.0.1:5174";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: FRONTEND, trace: "retain-on-failure" },
  // 1280 px is the narrowest window the console is designed for; the header must still fit on one row.
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } }],
  webServer: [
    {
      command: "uv run uvicorn backend.server:app --host 127.0.0.1 --port 8001",
      cwd: "..",
      url: `${BACKEND}/health`,
      // An empty cache of its own: mock mode replays the cache, and the shared one is warm.
      env: { JEV_MODE: "mock", ESCALATION_TIMEOUT_S: "0", SEED: "0", JEV_CACHE_PATH: "frontend/e2e/.cache/jev_cache.jsonl" },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "pnpm exec vite --port 5174 --strictPort",
      url: FRONTEND,
      env: { SHIELD_BACKEND: BACKEND },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
