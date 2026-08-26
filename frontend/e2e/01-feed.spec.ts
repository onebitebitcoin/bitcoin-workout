import { test, expect } from '@playwright/test'
import { registerAndLogin } from './helpers'

test.describe('피드 페이지', () => {
  test('피드 페이지 기본 렌더링', async ({ page }) => {
    await registerAndLogin(page)
    await page.screenshot({ path: 'e2e/screenshots/01-feed-empty.png', fullPage: true })

    const emptyMsg = page.locator('text=아직 업로드된 영상이 없어요')
    const hasVideos = page.locator('video')
    const isEmpty = await emptyMsg.isVisible().catch(() => false)

    if (isEmpty) {
      await expect(emptyMsg).toBeVisible()
    } else {
      await expect(hasVideos.first()).toBeVisible()
    }
  })

  test('BottomNav 5탭 표시', async ({ page }) => {
    await registerAndLogin(page)
    await page.screenshot({ path: 'e2e/screenshots/02-bottomnav.png', fullPage: true })

    // 피드, 챌린지, 알림, 프로필 NavLink(a 태그)
    await expect(page.getByRole('link', { name: '피드' })).toBeVisible()
    await expect(page.getByRole('link', { name: '챌린지' })).toBeVisible()
    await expect(page.getByRole('link', { name: '알림' })).toBeVisible()
    await expect(page.getByRole('link', { name: '프로필' })).toBeVisible()
    // 업로드는 FAB 버튼 (link 아님)
    await expect(page.getByRole('button', { name: '오늘 하루 올리기' })).toBeVisible()
  })
})
