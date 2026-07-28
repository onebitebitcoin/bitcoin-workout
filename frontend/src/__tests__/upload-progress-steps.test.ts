import { describe, it, expect } from 'vitest'
import { UPLOAD_STEP_CONFIG } from '../lib/constants'

/**
 * 업로드 진행률 단계 구간의 불변식.
 *
 * 진행률은 `Math.max(p, cfg.start)`로만 올라가고(역주행 방지) 틱은 `p < cfg.ceiling`일 때만
 * 증가한다. 그래서 뒤에 오는 단계의 ceiling이 앞 단계보다 낮으면 진행률이 멈춘 것처럼 보인다.
 * 백엔드 순서는 filter → compress(필터 없거나 실패 시)이므로 compress가 filter보다 뒤 구간이어야 한다.
 */
describe('UPLOAD_STEP_CONFIG 진행률 구간', () => {
  it('모든 단계가 start < ceiling', () => {
    for (const [step, cfg] of Object.entries(UPLOAD_STEP_CONFIG)) {
      expect(cfg.start, `${step}.start`).toBeLessThan(cfg.ceiling)
    }
  })

  it('필터 실패 폴백(filter → compress)에서 진행률이 멈추지 않는다', () => {
    // filter가 ceiling까지 올라간 뒤 compress로 넘어가므로, compress.ceiling이 더 커야
    // 가장 느린 재인코딩 구간에서 진행률이 계속 움직인다.
    expect(UPLOAD_STEP_CONFIG.compress.ceiling).toBeGreaterThan(UPLOAD_STEP_CONFIG.filter.ceiling)
  })

  it('필터 없이 곧장 compress로 가도 구간이 이어진다', () => {
    // audio_merge ceiling에서 compress start로 큰 점프가 생기지 않아야 한다.
    expect(UPLOAD_STEP_CONFIG.compress.start).toBeLessThanOrEqual(UPLOAD_STEP_CONFIG.audio_merge.ceiling)
  })

  it('렌더 단계가 끝나면 db_save 이후로 이어진다', () => {
    for (const step of ['filter', 'compress'] as const) {
      expect(UPLOAD_STEP_CONFIG.db_save.start, `db_save.start vs ${step}`).toBeGreaterThanOrEqual(
        UPLOAD_STEP_CONFIG[step].ceiling,
      )
    }
  })
})
