import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.js',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [['html'], ['github']] : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium',       use: { ...devices['Desktop Chrome']  } },
    { name: 'firefox',        use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit',         use: { ...devices['Desktop Safari']  } },
    { name: 'Mobile Chrome',  use: { ...devices['Pixel 5']         } },
    { name: 'Mobile Safari',  use: { ...devices['iPhone 12']       } },
    { name: 'iPhone SE 375',  use: { ...devices['iPhone SE']       } },
  ],
});
