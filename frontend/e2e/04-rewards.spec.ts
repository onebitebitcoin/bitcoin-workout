import { test, expect } from '@playwright/test'
import { registerAndLogin } from './helpers'

test.describe('프로필/설정/어드민', () => {
  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page)
  })

  test('프로필 페이지 — 스트릭 카드 표시', async ({ page }) => {
    await page.goto('/profile')
    await page.screenshot({ path: 'e2e/screenshots/10-profile.png', fullPage: true })

    await expect(page.locator('text=일 연속').first()).toBeVisible({ timeout: 8000 })
  })

  test('설정 페이지 — 로그아웃 버튼', async ({ page }) => {
    // 로그아웃 버튼은 프로필 → 설정 페이지로 이동됨
    await page.goto('/settings')
    await page.screenshot({ path: 'e2e/screenshots/09-settings.png', fullPage: true })

    await expect(page.getByRole('button', { name: '로그아웃' })).toBeVisible()
  })

  test('어드민 페이지 — 비관리자 접근 제한', async ({ page }) => {
    await page.goto('/admin')
    await page.screenshot({ path: 'e2e/screenshots/11-admin.png', fullPage: true })

    // 일반 유저는 관리자 전용 메시지가 표시됨
    await expect(page.locator('text=관리자만 접근할 수 있습니다')).toBeVisible()
  })
})
