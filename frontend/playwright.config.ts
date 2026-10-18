import { defineConfig, devices } from '@playwright/test'

// Browser smoke tests run against an already-started local backend and frontend.
// No test creates or alters financial records. Only the local demo login is used.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 8_000 },
  use: { baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], channel: process.env.E2E_BROWSER_CHANNEL || undefined } }],
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
})
