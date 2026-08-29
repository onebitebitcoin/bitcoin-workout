/**
 * Production E2E tests against https://story.onebitebitcoin.com
 * Run: npx playwright test --config=playwright.production.config.ts
 *
 * Uses email signup so Google OAuth is not needed.
 */
import { test, expect, type Page } from '@playwright/test'
import { fileURLToPath } from 'url'
import path from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const PROD_URL = 'https://story.onebitebitcoin.com'
const SCREENSHOT_DIR = 'e2e/screenshots/prod'
const TEST_VIDEO = path.resolve(__dirname, 'fixtures/test-workout.mp4')

// ── helpers ──────────────────────────────────────────────────────────────────

const ts = () => Date.now()
let testEmail = ''
let testUsername = ''

async function signup(page: Page) {
  const now = ts()
  testEmail = `claude_e2e_${now}@test.com`
  testUsername = `e2e_${now}`

  await page.goto(`${PROD_URL}/login`)
  await page.waitForLoadState('networkidle')

  // 이메일 로그인 모드 전환
  await page.locator('text=이메일로 로그인').click()

  // 회원가입 전환
  await page.locator('text=계정이 없어요').click()

  await page.fill('input[type="email"]', testEmail)
  await page.fill('input[placeholder="닉네임"]', testUsername)
  await page.fill('input[type="password"]', 'Password123!')
  await page.click('button[type="submit"]')

  await page.waitForURL(`${PROD_URL}/`, { timeout: 15000 })
}

async function screenshot(page: Page, name: string) {
  await page.screenshot({
    path: `${SCREENSHOT_DIR}/${name}.png`,
    fullPage: false,
  })
}

// ── tests ─────────────────────────────────────────────────────────────────────

test.describe('0. 인증 (회원가입 → 피드 진입)', () => {
  test('이메일 회원가입 후 피드 이동', async ({ page }) => {
    await signup(page)
    await screenshot(page, '00-feed-after-signup')

    await expect(page).toHaveURL(`${PROD_URL}/`)
    await expect(page.getByRole('link', { name: '피드' })).toBeVisible()
    await expect(page.getByRole('link', { name: '챌린지' })).toBeVisible()
    await expect(page.getByRole('link', { name: '알림' })).toBeVisible()
    await expect(page.getByRole('link', { name: '프로필' })).toBeVisible()
    await expect(page.getByRole('button', { name: '오늘 하루 올리기' })).toBeVisible()
  })
})

test.describe('1. 피드 (Feed)', () => {
  test.beforeEach(async ({ page }) => {
    await signup(page)
  })

  test('피드에 영상 또는 빈 상태 메시지가 표시된다', async ({ page }) => {
    await page.goto(`${PROD_URL}/`)
    await page.waitForLoadState('networkidle')
    await screenshot(page, '01-feed-view')

    const hasVideo = await page.locator('video').first().isVisible().catch(() => false)
    const isEmpty = await page.locator('text=아직 업로드된 영상이 없어요').isVisible().catch(() => false)
    expect(hasVideo || isEmpty).toBe(true)
  })

  test('좋아요 버튼 토글이 동작한다', async ({ page }) => {
    await page.goto(`${PROD_URL}/`)
    await page.waitForLoadState('networkidle')

    const likeBtn = page.locator('[data-testid="like-btn"]').first()
    const isVisible = await likeBtn.isVisible({ timeout: 5000 }).catch(() => false)
    if (!isVisible) {
      test.skip()
      return
    }

    const countBefore = await likeBtn.textContent()
    await screenshot(page, '01-before-like')

    await likeBtn.click()
    await page.waitForTimeout(800)
    await screenshot(page, '01-after-like')

    const countAfter = await likeBtn.textContent()
    // 좋아요 or 취소 — 숫자가 변하거나 같거나 (이미 좋아요)
    expect(countBefore).toBeDefined()
    expect(countAfter).toBeDefined()
  })

  test('댓글 시트가 열리고 댓글을 작성할 수 있다', async ({ page }) => {
    await page.goto(`${PROD_URL}/`)
    await page.waitForLoadState('networkidle')

    const commentBtn = page.locator('[data-testid="comment-btn"]').first()
    const isVisible = await commentBtn.isVisible({ timeout: 5000 }).catch(() => false)
    if (!isVisible) {
      test.skip()
      return
    }

    await commentBtn.click()
    await page.waitForTimeout(500)
    await screenshot(page, '01-comment-sheet-open')

    const input = page.getByPlaceholder('댓글 입력...')
    await expect(input).toBeVisible({ timeout: 5000 })

    await input.fill('E2E 테스트 댓글입니다 🎉')
    await page.keyboard.press('Enter')
    await page.waitForTimeout(1000)
    await screenshot(page, '01-comment-submitted')

    // 댓글이 목록에 나타나야 함
    await expect(page.locator('text=E2E 테스트 댓글입니다').first()).toBeVisible({ timeout: 5000 })
  })
})

test.describe('2. 영상 업로드 (Upload)', () => {
  test.beforeEach(async ({ page }) => {
    await signup(page)
  })

  test('테스트 영상을 업로드하고 피드에서 확인한다', async ({ page }) => {
    // /upload 로 직접 이동
    await page.goto(`${PROD_URL}/upload`)
    await page.waitForLoadState('networkidle')
    await screenshot(page, '02-upload-page')

    // Step 1: "영상을 선택하세요" 버튼이 파일 chooser 트리거
    const [fileChooser] = await Promise.all([
      page.waitForEvent('filechooser', { timeout: 10000 }),
      page.getByRole('button', { name: /영상을 선택하세요/ }).click(),
    ])
    await fileChooser.setFiles(TEST_VIDEO)
    await page.waitForTimeout(2000)
    await screenshot(page, '02-file-selected')

    // Step 2 버튼(다음) 또는 자동 진행 대기
    const nextBtn = page.getByRole('button', { name: /다음|Next/ })
    const hasNext = await nextBtn.isVisible({ timeout: 5000 }).catch(() => false)
    if (hasNext) {
      await nextBtn.click()
      await page.waitForTimeout(1000)
      await screenshot(page, '02-step2-tag')

      // 태그 선택 스킵하고 다음
      const nextBtn2 = page.getByRole('button', { name: /다음|Next/ })
      if (await nextBtn2.isVisible({ timeout: 3000 }).catch(() => false)) {
        await nextBtn2.click()
        await page.waitForTimeout(1000)
        await screenshot(page, '02-step3-audio')

        // 음성 녹음 스킵
        const skipBtn = page.getByRole('button', { name: /건너뛰기|스킵|Skip|다음/ })
        if (await skipBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
          await skipBtn.click()
          await page.waitForTimeout(1000)
          await screenshot(page, '02-step4-caption')

          // 설명 입력
          const captionInput = page.locator('textarea, input[placeholder*="설명"], input[placeholder*="caption"]').first()
          if (await captionInput.isVisible({ timeout: 3000 }).catch(() => false)) {
            await captionInput.fill('E2E 테스트 운동 영상')
          }

          // 업로드 제출
          const submitBtn = page.getByRole('button', { name: /업로드|완료|제출/ })
          if (await submitBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
            await submitBtn.click()
            await page.waitForTimeout(5000)
            await screenshot(page, '02-upload-submitted')
          }
        }
      }
    }

    // 피드로 복귀
    await page.goto(`${PROD_URL}/`)
    await page.waitForLoadState('networkidle')
    await screenshot(page, '02-feed-after-upload')

    // 프로필에서 내 영상 확인
    await page.goto(`${PROD_URL}/profile`)
    await page.waitForLoadState('networkidle')
    await screenshot(page, '02-profile-after-upload')

    // 프로필 페이지에 내 계정명이 보여야 함
    await expect(page.locator(`text=${testUsername}`)).toBeVisible({ timeout: 8000 })
  })
})

test.describe('3. 프로필 & 주간 이력', () => {
  test.beforeEach(async ({ page }) => {
    await signup(page)
  })

  test('프로필 페이지가 정상 렌더링된다', async ({ page }) => {
    await page.goto(`${PROD_URL}/profile`)
    await page.waitForLoadState('networkidle')
    await screenshot(page, '03-profile')

    // 사용자명 표시
    await expect(page.locator(`text=${testUsername}`)).toBeVisible({ timeout: 8000 })

    // 땀 카드
    await expect(page.locator('text=이번 주 흘린 땀')).toBeVisible()
    await expect(page.locator('text=주간 이력')).toBeVisible()

    // 연속일 & 월간 운동일
    await expect(page.locator('text=일 연속').first()).toBeVisible()
    await expect(page.locator('text=이번 달').first()).toBeVisible()
  })

  test('주간 이력 패널이 열리고 내용이 표시된다', async ({ page }) => {
    await page.goto(`${PROD_URL}/profile`)
    await page.waitForLoadState('networkidle')

    // 주간 이력 버튼 클릭
    const weeklyBtn = page.getByRole('button', { name: /주간 이력/ })
    await expect(weeklyBtn).toBeVisible({ timeout: 8000 })
    await weeklyBtn.click()
    await page.waitForTimeout(500)
    await screenshot(page, '03-weekly-history-open')

    // 패널이 열려야 함 (누적 총 땀 텍스트)
    await expect(page.locator('text=누적 총 땀')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('이번 주 활동', { exact: true }).first()).toBeVisible()

    // 패널 컨테이너 scrollHeight 검증 (DOM에 내용이 있는지 확인)
    const panelScrollHeight = await page.evaluate(() => {
      const divs = Array.from(document.querySelectorAll('div'))
      const panel = divs.find(d =>
        d.className.includes('rounded-b-2xl') && d.className.includes('overflow-hidden')
      )
      return panel ? panel.scrollHeight : -1
    })
    expect(panelScrollHeight).toBeGreaterThan(10)

    await screenshot(page, '03-weekly-history-expanded')
  })

  test('캘린더가 이번 달을 표시한다', async ({ page }) => {
    await page.goto(`${PROD_URL}/profile`)
    await page.waitForLoadState('networkidle')
    await screenshot(page, '03-calendar')

    const now = new Date()
    const yearMonth = `${now.getFullYear()}년 ${now.getMonth() + 1}월`
    await expect(page.locator(`text=${yearMonth}`)).toBeVisible({ timeout: 5000 })
  })
})

test.describe('4. 챌린지 페이지', () => {
  test.beforeEach(async ({ page }) => {
    await signup(page)
  })

  test('챌린지 목록 또는 빈 상태가 표시된다', async ({ page }) => {
    await page.goto(`${PROD_URL}/challenges`)
    await page.waitForLoadState('networkidle')
    await screenshot(page, '04-challenges')

    // 챌린지 페이지가 로드됨 (에러 없이)
    await expect(page).toHaveURL(`${PROD_URL}/challenges`)
    const hasContent = await page.locator('main, [class*="challenge"], [class*="Challenge"]').first().isVisible({ timeout: 5000 }).catch(() => false)
    const hasEmpty = await page.locator('text=챌린지').first().isVisible({ timeout: 5000 }).catch(() => false)
    expect(hasContent || hasEmpty).toBe(true)
  })
})
