import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: 'http://localhost:4173',
    headless: true,
  },
  webServer: {
    // Vite preview serves the production build — same bundle Django/TwistedWeb serves
    command: 'pnpm preview --port 4173',
    port: 4173,
    reuseExistingServer: false,
    timeout: 10_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});
