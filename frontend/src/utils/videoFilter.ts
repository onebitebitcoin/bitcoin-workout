export type VideoFilterValue = 'cartoon' | 'heat' | 'cartoon_heat' | undefined

/** 카툰·운동열 스위치 상태를 업로드 폼에 보낼 video_filter 값으로 합성한다. */
export function combineVideoFilter(cartoonFilter: boolean, heatFilter: boolean): VideoFilterValue {
  if (cartoonFilter && heatFilter) return 'cartoon_heat'
  if (heatFilter) return 'heat'
  if (cartoonFilter) return 'cartoon'
  return undefined
}
