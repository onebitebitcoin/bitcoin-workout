/** 업로드 폼 video_filter 값. ''(빈 값) = 효과 없음(필드 미전송). */
export type VideoFilterValue = '' | 'cartoon'

/** 효과 선택 UI 옵션 순서 — StepMedia 드롭다운과 i18n 키(filter.options.*)가 공유. */
export const VIDEO_FILTER_OPTIONS = [
  { value: '' as const, key: 'none' },
  { value: 'cartoon' as const, key: 'cartoon' },
]
