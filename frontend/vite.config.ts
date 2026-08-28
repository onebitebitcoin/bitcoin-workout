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
      includeAssets: ['favicon.svg', 'favicon-192.png', 'apple-touch-icon.png'],
      manifest: {
        id: '/',
        name: 'Bitcoiners',
        short_name: 'Bitcoiners',
        description:
          '비트코이너는 뭐하고 사나 — 비트코인 공부, 라이트닝 결제, 운동, 노드 운영을 60초 영상으로 기록하고 공유하는 커뮤니티',
        theme_color: '#0D0D0D',
        background_color: '#0D0D0D',
        display: 'standalone',
        orientation: 'portrait',
        scope: '/',
        start_url: '/',
        icons: [
          {
            src: '/favicon-192.png',
            sizes: '192x192',
            type: 'image/png',
          },
          {
            src: '/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
          },
          {
            src: '/icon-512.png',
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
