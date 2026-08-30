/**
 * 업로드 화면의 자막 미리보기 크기·위치 매핑. StepSubtitle과 MediaPreviewBox가
 * 각자 복제해 쓰던 것을 한 곳으로 모았다.
 *
 * 이 맵의 값은 UI 타입 스케일이 아니다. 서버가 영상에 구워 넣는(burn-in) 실제 자막
 * 크기를 화면에 근사시킨 값이라 scripts/check-design-tokens.mjs 규칙에서 제외된다.
 * 크기 두 값은 worker/tasks/subtitle.py의 FONT_SIZE_MAP({"small": 14, "large": 18})과
 * 짝이다 — 여기에 값을 늘리려면 그쪽 맵부터 늘려야 조용히 small로 강등되지 않는다.
 */

export type SubtitleSize = 'small' | 'large'
export type SubtitlePosition = 'top' | 'center' | 'bottom'

export const SIZE_TEXT_CLASS: Record<SubtitleSize, string> = {
  small: 'text-[9px]', large: 'text-sm', // design-token-exempt: 영상에 구워질 자막 크기의 미리보기다. UI 스케일이 아니라 burn 결과에 맞춘 값이라 바꾸면 미리보기가 실제와 달라진다.
}

export const POSITION_FLEX_CLASS: Record<SubtitlePosition, string> = {
  top: 'justify-start pt-3', center: 'justify-center', bottom: 'justify-end pb-3',
}
