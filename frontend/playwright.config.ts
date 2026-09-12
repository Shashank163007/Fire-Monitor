import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1, timeout: 90000,
  expect: { timeout: 20000 }, reporter: [['list'], ['json', { outputFile: 'test-results/browser-results.json' }]],
  use: { ...devices['Desktop Chrome'], channel: 'chrome', baseURL: 'http://127.0.0.1:5173',
    viewport: { width: 1440, height: 1080 }, screenshot: 'only-on-failure', trace: 'retain-on-failure',
    launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] } },
  webServer: [
    { command: '..\\.venv\\Scripts\\python.exe -B -m uvicorn backend.app:app --app-dir .. --host 127.0.0.1 --port 8000',
      url: 'http://127.0.0.1:8000/api/v1/health', reuseExistingServer: false, timeout: 30000 },
    { command: 'npm run preview', url: 'http://127.0.0.1:5173', reuseExistingServer: false, timeout: 30000 },
  ],
})
