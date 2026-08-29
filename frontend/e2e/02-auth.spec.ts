import { test, expect } from '@playwright/test'
import { registerAndLogin } from './helpers'

test.describe('인증 플로우', () => {
  test('로그인 페이지 렌더링', async ({ page }) => {
    await page.goto('/login')
    await page.screenshot({ path: 'e2e/screenshots/03-login.png', fullPage: true })

    await expect(page.locator('input[type="email"]')).not.toBeVisible()  // email form hidden by default
    await expect(page.getByLabel('Orange Story 로고')).toBeVisible()
    await expect(page.locator('text=이메일로 로그인')).toBeVisible()
  })

  test('회원가입 폼 토글', async ({ page }) => {
    await page.goto('/login')

    // 이메일 모드 전환 후 회원가입 모드
    await page.click('text=이메일로 로그인')
    await page.locator('text=계정이 없어요').click()
    await page.screenshot({ path: 'e2e/screenshots/04-register-form.png', fullPage: true })

    await expect(page.locator('input[placeholder="닉네임"]')).toBeVisible()
    await expect(page.locator('button[type="submit"]:has-text("회원가입")')).toBeVisible()
  })

  test('회원가입 → 피드 이동', async ({ page }) => {
    await registerAndLogin(page)
    await page.screenshot({ path: 'e2e/screenshots/05-after-register.png', fullPage: true })

    expect(page.url()).toMatch(/\/$/)
  })

  test('비로그인 시 / 접근하면 로그인 페이지로 이동', async ({ page }) => {
    await page.goto('/')
    await page.screenshot({ path: 'e2e/screenshots/06-upload-auth-gate.png', fullPage: true })

    expect(page.url()).toMatch(/login/)
  })
})
