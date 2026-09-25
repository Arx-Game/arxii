import { defineConfig } from '@playwright/test';

/**
 * Opt-in config for the real authenticated idle soak. It has no webServer and
 * never supplies fixture routes. The target must be the public/rehearsal path.
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: 'liveness-soak.spec.ts',
  timeout: 3_900_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: process.env.LIVENESS_SOAK_BASE_URL ?? 'http://127.0.0.1:4001',
    headless: true,
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
