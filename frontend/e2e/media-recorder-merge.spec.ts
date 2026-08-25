import { test, expect } from '@playwright/test'

const PROD_URL = 'https://stack-health-production.up.railway.app'
const TEST_VIDEO = '/tmp/test_1sec.mp4'

test.use({
  launchOptions: {
    args: [
      '--use-fake-device-for-media-stream',
      '--use-fake-ui-for-media-stream',
    ],
  },
  permissions: ['microphone'],
})

test('MediaRecorder 오디오 병합 — 1초 영상 + 5초 녹음 → 5초 출력', async ({ page, context }) => {
  await context.grantPermissions(['microphone'])

  // 1. 로그인
  await page.goto(`${PROD_URL}/login`)
  await page.getByRole('button', { name: '이메일로 로그인' }).click()
  await page.getByRole('textbox', { name: '이메일' }).fill('test@test.com')
  await page.getByRole('textbox', { name: '비밀번호' }).fill('00000000')
  await page.getByRole('button', { name: '로그인' }).click()
  await page.waitForURL(`${PROD_URL}/`)

  // 2. 업로드 페이지
  await page.getByRole('button', { name: '운동 영상 올리기' }).click()
  await page.waitForURL(`${PROD_URL}/upload`)

  // 3. Step 0: 영상 파일 주입
  await page.locator('input[type="file"]').setInputFiles(TEST_VIDEO)
  await page.waitForSelector('text=운동 종류를 선택하세요')

  // 4. Step 1: 태그 → 다음
  await page.getByRole('button', { name: '홈트' }).click()
  await page.getByRole('button', { name: /다음/ }).click()

  // 5. Step 2: 챌린지 → 다음
  await page.waitForSelector('text=챌린지 선택')
  await page.getByRole('button', { name: /다음/ }).click()

  // 6. Step 3: 5초 녹음
  await page.waitForSelector('text=음성 녹음')
  await page.getByRole('button', { name: '녹음 시작' }).click()
  await page.waitForTimeout(5200)

  // 녹음 중지 (빨간 버튼 — CSS 선택자 대신 evaluate로 클릭)
  const stopped = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'))
    const stopBtn = btns.find(b => b.classList.contains('bg-red-600'))
    if (stopBtn) { stopBtn.click(); return true }
    return false
  })
  console.log('Stop button found:', stopped)
  await page.waitForTimeout(600)

  // 7. Step 4: 설명 페이지 확인
  await page.waitForSelector('text=설명을 추가하세요')

  // merge-audio 응답을 기다리는 Promise를 먼저 설정
  const mergeResponsePromise = page.waitForResponse(
    res => res.url().includes('/videos/merge-audio') && res.ok(),
    { timeout: 60000 },
  )

  // 업로드 시작
  await page.getByRole('button', { name: '업로드 시작' }).click()

  // merge-audio 응답 수신 대기
  const mergeResponse = await mergeResponsePromise
  const mergeJson = await mergeResponse.json()
  console.log('merge-audio 응답:', JSON.stringify(mergeJson))

  const durationSec: number = mergeJson?.data?.duration_sec
  console.log('duration_sec:', durationSec)

  // 업로드 완료 대기
  await page.waitForSelector('text=/업로드 완료|공유/', { timeout: 60000 })
  await page.screenshot({ path: 'e2e/screenshots/mediarecorder-merge-result.png' })

  // 검증
  expect(durationSec, 'merge-audio 응답 duration_sec이 5여야 함').toBe(5)
})
