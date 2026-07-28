export const LN_POLL_INTERVAL_MS = 2_000
export const LN_LOGIN_EXPIRE_MS = 120_000

export const MERGE_POLL_INTERVAL_MS = 3_000

// 업로드 파이프라인 단계별 진행률 구간. 실제 백엔드 단계 순서(worker/tasks/full_pipeline_multi.py의
// status_callback 호출 순서)와 일치시켜야 한다:
//   compose → audio_merge → filter(있으면) → compress(필터 없거나 실패 시만)
//   → db_save → thumbnail → subtitle → db_save
// 폴링이 실제 pipeline_step을 그대로 반영하므로 건너뛴 단계는 자연히 표시되지 않는다
// (이 맵에 없는 단계가 와도 안전).
//
// filter와 compress는 상호배타가 아니다(필터 실패 시 compress로 폴백) — 그래서 compress가
// filter보다 뒤 구간이어야 한다. 진행률은 Math.max로만 올라가고(역주행 방지) 틱은
// `p < ceiling`일 때만 증가하므로, compress.ceiling이 filter.ceiling보다 낮으면 폴백
// 구간(가장 느린 재인코딩) 내내 진행률이 멈춘 것처럼 보인다.
// 세 경로 모두 확인: 필터없음 audio_merge(82)→compress(82~92) / 필터성공 filter(82~88)→db_save(92)
// / 필터실패 filter(82~88)→compress(88~92).
export const UPLOAD_STEP_CONFIG: Record<string, { start: number; ceiling: number; interval: number }> = {
  compose:     { start: 72, ceiling: 80, interval: 3000 },
  audio_merge: { start: 80, ceiling: 82, interval: 1500 },
  filter:      { start: 82, ceiling: 88, interval: 3000 },
  compress:    { start: 82, ceiling: 92, interval: 1500 },
  db_save:     { start: 92, ceiling: 94, interval: 1500 },
  thumbnail:   { start: 94, ceiling: 96, interval: 1500 },
  subtitle:    { start: 96, ceiling: 98, interval: 1500 },
}
