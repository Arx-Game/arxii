/**
 * Playwright config for running e2e tests against the Django-served frontend
 * (production build served by Evennia's TwistedWeb on :4001).
 *
 * Unlike the default playwright.config.ts (which starts `vite preview` with no
 * backend), this config expects the Evennia server to already be running
 * (`just start` from the repo root). The tests hit real API endpoints:
 * allauth signup, CSRF, /api/status/, /api/user/, etc.
 *
 * Usage:  just fe-e2e  (or: cd frontend && npx playwright test --config e2e.backend.config.ts)
 */
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  // CI (.github/workflows/real-test.yml, #4247) keeps a screenshot and a trace of
  // every test as run artifacts; locally nothing extra is written.
  outputDir: 'test-results',
  reporter: process.env.CI
    ? [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]]
    : 'list',
  use: {
    baseURL: 'http://localhost:4001',
    headless: true,
    screenshot: process.env.CI ? 'on' : 'off',
    trace: process.env.CI ? 'on' : 'off',
  },
  // No webServer block — the Django/Evennia server must be started manually
  // via `just start`. This prevents Playwright from trying to spin up a
  // Vite preview server that would shadow the real backend.
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});
