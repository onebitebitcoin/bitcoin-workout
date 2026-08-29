import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/prod-*.spec.ts',
  fullyParallel: false,
  forbidOnly: false,
  retries: 1,
  workers: 1,
  reporter: [
    ['html', { outputFolder: 'playwright-report-prod', open: 'never' }],
    ['list'],
  ],
  use: {
    baseURL: 'https://story.onebitebitcoin.com',
    screenshot: 'on',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },
  projects: [
    {
      name: 'mobile-chrome',
      use: {
        ...devices['Pixel 7'],
        hasTouch: true,
        isMobile: true,
      },
    },
    {
      name: 'desktop-chrome',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
