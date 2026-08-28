import { useRef, type ChangeEvent } from 'react'
import type { RefObject, MutableRefObject } from 'react'
import { ImagePlus, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { srtToTextLines } from '../../utils/subtitles'
import type { SubtitleLanguage } from '../../api/types'

type SubtitleSize = 'small' | 'medium' | 'large'
type SubtitlePosition = 'top' | 'center' | 'bottom'

interface Props {
  proofImageRef: RefObject<HTMLInputElement>
  proofPreviewUrl: string | null
  setProofPreviewUrl: (v: string | null) => void
  proofFileRef: MutableRefObject<File | null>
  caption: string
  setCaption: (v: string) => void
  subtitleText: string
  subtitleSize: SubtitleSize
  subtitlePosition: SubtitlePosition
  onSubtitleSizeChange: (v: SubtitleSize) => void
  onSubtitlePositionChange: (v: SubtitlePosition) => void
  subtitleLanguage: SubtitleLanguage
  onSubtitleLanguageChange: (v: SubtitleLanguage) => void
  error: string
  uploading: boolean
  onUpload: () => void
}

const SIZE_TEXT_CLASS: Record<SubtitleSize, string> = {
  small: 'text-[9px]', medium: 'text-xs', large: 'text-sm', // design-token-exempt: 영상에 구워질 자막 크기의 미리보기다. UI 스케일이 아니라 burn 결과에 맞춘 값이라 바꾸면 미리보기가 실제와 달라진다.
}

const POSITION_FLEX_CLASS: Record<SubtitlePosition, string> = {
  top: 'justify-start pt-3',
  center: 'justify-center',
  bottom: 'justify-end pb-3',
}

export default function StepCaption({
  proofImageRef, proofPreviewUrl, setProofPreviewUrl, proofFileRef,
  caption, setCaption, subtitleText,
  subtitleSize, subtitlePosition, onSubtitleSizeChange, onSubtitlePositionChange,
  subtitleLanguage, onSubtitleLanguageChange,
  error, uploading, onUpload,
}: Props) {
  const { t } = useTranslation('upload')
  const hasSubtitle = subtitleText.trim().length > 0
  const previewText = srtToTextLines(subtitleText).find(l => l.trim()) ?? t('caption.subtitlePreview')
  const captionRef = useRef<HTMLTextAreaElement>(null)

  const SIZE_LABELS: Record<SubtitleSize, string> = {
    small: t('caption.subtitleSizeSmall'),
    medium: t('caption.subtitleSizeMedium'),
    large: t('caption.subtitleSizeLarge'),
  }

  const POSITION_LABELS: Record<SubtitlePosition, string> = {
    top: t('caption.subtitlePositionTop'),
    center: t('caption.subtitlePositionCenter'),
    bottom: t('caption.subtitlePositionBottom'),
  }

  const LANGUAGE_OPTIONS: { value: SubtitleLanguage; label: string }[] = [
    { value: 'ko', label: t('caption.subtitleLanguageKo') },
    { value: 'en', label: t('caption.subtitleLanguageEn') },
    { value: 'auto', label: t('caption.subtitleLanguageAuto') },
  ]

  return (
    <div className="flex flex-1 flex-col px-6 pt-4 pb-6 overflow-y-auto gap-4">
      {/* 자막 언어 선택 */}
      <div className="rounded-card bg-theme-surface px-4 py-3 space-y-2">
        <p className="text-label font-medium text-theme-muted">{t('caption.subtitleLanguage')}</p>
        <div className="flex gap-2">
          {LANGUAGE_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              onClick={() => onSubtitleLanguageChange(value)}
              className={`flex-1 rounded-card px-2 py-2 text-label font-medium transition-colors ${
                subtitleLanguage === value
                  ? 'bg-accent text-accent-fg'
                  : 'bg-theme-surface2 text-theme-muted hover:text-theme-primary'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* 자막 스타일 (추출된 경우만) */}
      {hasSubtitle && (
        <div className="rounded-card bg-theme-surface px-4 py-3 space-y-3">
          <p className="text-body font-semibold text-theme-primary">{t('record.subtitle')}</p>
          <div className="flex items-center gap-3">
            <span className="text-label text-theme-muted w-10 flex-shrink-0">{t('caption.subtitleSize')}</span>
            <div className="flex gap-2">
              {(['small', 'medium', 'large'] as SubtitleSize[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => onSubtitleSizeChange(s)}
                  className={`rounded-card px-3 py-2 text-label font-medium transition-colors ${
                    subtitleSize === s
                      ? 'bg-accent text-accent-fg'
                      : 'bg-theme-surface2 text-theme-muted hover:text-theme-primary'
                  }`}
                >
                  {SIZE_LABELS[s]}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-label text-theme-muted w-10 flex-shrink-0">{t('caption.subtitlePosition')}</span>
            <div className="flex gap-2">
              {(['top', 'center', 'bottom'] as SubtitlePosition[]).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => onSubtitlePositionChange(p)}
                  className={`rounded-card px-3 py-2 text-label font-medium transition-colors ${
                    subtitlePosition === p
                      ? 'bg-accent text-accent-fg'
                      : 'bg-theme-surface2 text-theme-muted hover:text-theme-primary'
                  }`}
                >
                  {POSITION_LABELS[p]}
                </button>
              ))}
            </div>
          </div>
          <div className="rounded-card overflow-hidden bg-black" style={{ aspectRatio: '9/16', maxHeight: '180px' }}>
            <div className={`relative w-full h-full flex flex-col items-center ${POSITION_FLEX_CLASS[subtitlePosition]}`}>
              <div className="px-2 py-1 rounded" style={{ backgroundColor: 'rgba(0,0,0,0.8)' }}>
                <span className={`text-white font-medium ${SIZE_TEXT_CLASS[subtitleSize]}`}>{previewText}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 설명 */}
      <div className="flex flex-col gap-1">
        <p className="text-body font-semibold text-theme-primary mb-1">
          {t('caption.captionLabel')} <span className="text-label font-normal text-theme-muted">{t('caption.captionOptional')}</span>
        </p>
        <textarea
          ref={captionRef}
          value={caption}
          onChange={(e) => setCaption(e.target.value.slice(0, 140))}
          maxLength={140}
          placeholder={t('caption.captionPlaceholder')}
          rows={4}
          className="resize-none rounded-card bg-theme-surface px-4 py-3 text-theme-primary placeholder-theme-muted outline-none focus:ring-2 focus:ring-accent"
        />
        <p className="text-right text-label text-theme-muted">{caption.length}/140</p>
      </div>

      {/* 인증 사진 */}
      <div className="flex flex-col gap-1">
        <p className="text-body font-semibold text-theme-primary">
          {t('caption.proofPhoto')} <span className="text-label font-normal text-theme-muted">{t('caption.proofPhotoOptional')}</span>
        </p>
        <p className="text-label text-theme-muted leading-relaxed mb-2">
          {t('caption.proofPhotoHint')}
        </p>
        <input
          ref={proofImageRef}
          id="proof-image-input"
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            const f = e.target.files?.[0]
            if (!f) return
            proofFileRef.current = f
            setProofPreviewUrl(URL.createObjectURL(f))
          }}
        />
        {proofPreviewUrl ? (
          <div className="relative">
            <img src={proofPreviewUrl} alt={t('caption.proofPhotoPreviewAlt')} className="w-full rounded-card object-cover max-h-48" />
            <button
              onClick={() => {
                proofFileRef.current = null
                setProofPreviewUrl(null)
                if (proofImageRef.current) proofImageRef.current.value = ''
              }}
              className="absolute right-2 top-2 rounded-pill bg-black/60 p-2 text-white"
            >
              <X size={14} />
            </button>
          </div>
        ) : (
          <label
            htmlFor="proof-image-input"
            className="flex items-center justify-center gap-2 rounded-card border-2 border-dashed border-theme-border p-4 text-theme-muted hover:border-accent hover:text-accent transition-colors cursor-pointer"
          >
            <ImagePlus size={20} strokeWidth={1.5} />
            <span className="text-body">{t('caption.proofPhotoAdd')}</span>
          </label>
        )}
      </div>

      {error && <p className="text-body text-danger">{error}</p>}

      <button
        onClick={onUpload}
        disabled={uploading}
        className="w-full rounded-card bg-accent py-3 font-semibold text-accent-fg disabled:opacity-60"
      >
        {t('caption.uploadStart')}
      </button>
    </div>
  )
}
