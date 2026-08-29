import { defineConfig, devices } from '@playwright/test'

// 일반 개발 포트(5173/8000)와 겹치지 않는 E2E 전용 포트
const FRONTEND_PORT = Number(process.env.E2E_FRONTEND_PORT ?? 5273)
const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8173)

export default defineConfig({
  testDir: './e2e',
  // prod-*.spec.ts 는 https://story.onebitebitcoin.com 운영 사이트에 직접 붙어 계정을 만들고
  // 영상을 업로드한다. 반드시 playwright.production.config.ts 로만 실행한다.
  testIgnore: ['**/media-recorder-merge.spec.ts', '**/prod-*.spec.ts'],
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [['html', { outputFolder: 'playwright-report', open: 'never' }], ['list']],
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    // 기본 UI는 한국어 기준으로 검증한다 (i18n LanguageDetector가 navigator 언어를 따르므로 고정)
    locale: 'ko-KR',
    screenshot: 'on',
    video: 'off',
    trace: 'off',
  },
  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'] },
    },
    // {
    //   name: 'android',
    //   use: { ...devices['Pixel 5'], hasTouch: true, isMobile: true },
    // },
    {
      name: 'iphone',
      use: {
        ...devices['iPhone 14'],
        // WebKit: Safari engine; tests safe-area CSS, input behaviour, etc.
        hasTouch: true,
        isMobile: true,
      },
    },
  ],
  // E2E 전용 포트를 쓴다. 기본 개발 포트(5173/8000)를 쓰면 다른 프로젝트의 서버가
  // 이미 떠 있을 때 reuseExistingServer 가 그걸 그대로 잡아, 엉뚱한 앱을 상대로
  // 테스트가 조용히 통과하거나 실패한다. reuseExistingServer:false 라서 포트가
  // 막혀 있으면 조용히 넘어가지 않고 즉시 에러로 알린다.
  webServer: [
    {
      command: `cd ../backend && .venv/bin/uvicorn app.main:app --port ${BACKEND_PORT}`,
      port: BACKEND_PORT,
      timeout: 30000,
      reuseExistingServer: false,
    },
    {
      command: `npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      port: FRONTEND_PORT,
      timeout: 30000,
      reuseExistingServer: false,
      env: { VITE_API_PROXY_TARGET: `http://localhost:${BACKEND_PORT}` },
    },
  ],
})
