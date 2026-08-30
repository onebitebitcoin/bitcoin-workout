import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { MediaItem } from './StepMedia'
import type { VideoFilterValue } from '../../utils/videoFilter'
import { SIZE_TEXT_CLASS, POSITION_FLEX_CLASS, type SubtitleSize, type SubtitlePosition } from './subtitlePreview'


interface Props {
  items: MediaItem[]
  subtitleSource: string
  subtitleLines: string[]
  subtitleSize: SubtitleSize
  subtitlePosition: SubtitlePosition
  videoFilter?: VideoFilterValue
  filteredPreviewUrl?: string | null
}

/** 미디어를 9:16 박스에 순서대로 보여주고 자막을 오버레이하는 근사 미리보기(업로드/요약 없음).
 *  videoFilter가 선택돼 있으면 첫 미디어는 필터 적용된 정지 프레임(filteredPreviewUrl)으로 대체 —
 *  실제 필터 합성은 업로드 후 서버에서 처리되므로 영상 전체를 프론트에서 재현하지 않는다. */
export default function MediaPreviewBox({
  items, subtitleSource, subtitleLines, subtitleSize, subtitlePosition,
  videoFilter, filteredPreviewUrl,
}: Props) {
  const { t } = useTranslation('upload')
  const [active, setActive] = useState(0)
  const current = items[Math.min(active, items.length - 1)]
  const hasSubtitle = subtitleSource !== 'none' && subtitleLines.length > 0
  const previewText = hasSubtitle ? subtitleLines[0] : ''
  const showFilteredFrame = active === 0 && !!videoFilter && !!filteredPreviewUrl

  if (!current) return null

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="w-full max-w-[200px] rounded-card overflow-hidden bg-black" style={{ aspectRatio: '9/16' }}>
        <div className="relative w-full h-full">
          {showFilteredFrame ? (
            <img src={filteredPreviewUrl ?? undefined} className="w-full h-full object-contain" alt="" />
          ) : current.kind === 'video' ? (
            <video src={current.previewUrl} className="w-full h-full object-contain" muted playsInline controls />
          ) : (
            <img src={current.previewUrl} className="w-full h-full object-contain" alt="" />
          )}
          {hasSubtitle && (
            <div className={`absolute inset-0 flex flex-col items-center px-2 ${POSITION_FLEX_CLASS[subtitlePosition]}`}>
              <div className="px-2 py-1 rounded max-w-full text-center" style={{ backgroundColor: 'rgba(0,0,0,0.8)' }}>
                <span className={`text-white font-medium break-words ${SIZE_TEXT_CLASS[subtitleSize]}`}>{previewText}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {showFilteredFrame && (
        <p className="text-label text-theme-muted text-center max-w-[200px]">{t('preview.filterNote')}</p>
      )}

      {items.length > 1 && (
        <div className="flex gap-2 justify-center flex-wrap">
          {items.map((m, i) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setActive(i)}
              className={`relative w-9 h-14 rounded-card overflow-hidden border-2 ${i === active ? 'border-accent' : 'border-transparent'}`}
            >
              {m.kind === 'video' ? (
                <video src={m.previewUrl} className="w-full h-full object-cover" muted playsInline />
              ) : (
                <img src={m.previewUrl} className="w-full h-full object-cover" alt="" />
              )}
              <span className="absolute bottom-0 right-0 bg-black/70 text-white text-label px-1 rounded-tl">{i + 1}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
