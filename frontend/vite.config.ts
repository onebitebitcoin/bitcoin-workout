import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const appVersion = readFileSync(resolve(__dirname, '../VERSION'), 'utf-8').trim()

// dev 프록시가 바라볼 백엔드. E2E는 전용 포트로 띄우므로 환경변수로 갈아끼운다.
const API_PROXY_TARGET = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    setupFiles: ['./src/__tests__/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['src/store/**/*.ts'],
      exclude: ['src/__tests__/**'],
      thresholds: {
        lines: 85,
        functions: 85,
        branches: 75,
        statements: 85,
      },
    },
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'favicon-192.png', 'apple-touch-icon.png', 'icon-192.png', 'maskable-512.png'],
      manifest: {
        id: '/',
        name: 'Orange Story',
        short_name: 'Orange Story',
        description:
          '나의 비트코인 기록 — 비트코인 공부, 라이트닝 결제, 운동, 노드 운영을 60초 영상으로 기록하고 공유하는 서비스',
        theme_color: '#0A0A0A',
        background_color: '#0A0A0A',
        display: 'standalone',
        orientation: 'portrait',
        scope: '/',
        start_url: '/',
        // 설치 아이콘은 어두운 타일(icon-*.png)을 쓴다. favicon-192.png 는 배경이
        // 투명한 마크라 런처가 흰 판을 깔아 밝게 보였다 — 탭 아이콘 자리에만 둔다.
        icons: [
          {
            src: '/icon-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any',
          },
          {
            src: '/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any',
          },
          // maskable 은 별도 파일이어야 한다. OS 가 제 모양대로 잘라내므로
          // 안전영역(중앙 지름 80%) 안에 마크를 줄여 넣은 판을 따로 쓴다.
          // any 용 타일을 그대로 주면 잎 끝이 원형 마스크 밖으로 나가 잘린다.
          {
            src: '/maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        navigateFallback: 'index.html',
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/.*\/api\//,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              networkTimeoutSeconds: 10,
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: /\.mp4$/,
            handler: 'NetworkOnly',
          },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
    proxy: {
      '/api': {
        target: API_PROXY_TARGET,
        changeOrigin: true,
      },
      '/admin': {
        target: API_PROXY_TARGET,
        changeOrigin: true,
        bypass(req) {
          // HTML 요청(브라우저 페이지 네비게이션)은 SPA에서 처리
          if (req.headers.accept?.includes('text/html')) return req.url
        },
      },
    },
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
  },
})
