import { useEffect, useRef, useState } from 'react'
import { Mic, MicOff, X, ChevronRight, ChevronDown, Loader2, VolumeX, Volume2, AlertCircle, Video, Type } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { srtToTextLines, applyTextLinesToSrt } from '../../utils/subtitles'
import type { SubtitleLanguage } from '../../api/types'

export type SubtitleSource = 'none' | 'video' | 'record' | 'text'
type VideoAudioStatus = 'idle' | 'analyzing' | 'has_audio' | 'no_audio' | 'error'
type SubtitleSize = 'small' | 'large'
type SubtitlePosition = 'top' | 'center' | 'bottom'

interface Props {
  hasVideo: boolean
  subtitleSource: SubtitleSource
  setSubtitleSource: (s: SubtitleSource) => void
  videoAudioStatus: VideoAudioStatus
  subtitleText: string
  setSubtitleText: (v: string) => void
  subtitlePlainText: string
  subtitleExtracting: boolean
  onExtractFromAudio: () => void
  onClearSubtitle: () => void
  subtitleRawText: string
  setSubtitleRawText: (v: string) => void
  recording: boolean
  recordedSeconds: number
  recordingDone: boolean
  progressPct: number
  maxSeconds: number
  startRecording: () => void
  stopRecording: () => void
  onRetake: () => void
  subtitleSize: SubtitleSize
  subtitlePosition: SubtitlePosition
  onSubtitleSizeChange: (v: SubtitleSize) => void
  onSubtitlePositionChange: (v: SubtitlePosition) => void
  subtitleLanguage: SubtitleLanguage
  onSubtitleLanguageChange: (v: SubtitleLanguage) => void
  muteOriginalAudio: boolean
  setMuteOriginalAudio: (v: boolean) => void
  error: string
  onNext: () => void
}

const SIZE_TEXT_CLASS: Record<SubtitleSize, string> = {
  small: 'text-[9px]', large: 'text-sm', // design-token-exempt: 영상에 구워질 자막 크기의 미리보기다. UI 스케일이 아니라 burn 결과에 맞춘 값이라 바꾸면 미리보기가 실제와 달라진다.
}
const POSITION_FLEX_CLASS: Record<SubtitlePosition, string> = {
  top: 'justify-start pt-3', center: 'justify-center', bottom: 'justify-end pb-3',
}

export default function StepSubtitle(props: Props) {
  const {
    hasVideo, subtitleSource, setSubtitleSource,
    videoAudioStatus, subtitleText, setSubtitleText, subtitlePlainText, subtitleExtracting,
    onExtractFromAudio, onClearSubtitle,
    subtitleRawText, setSubtitleRawText,
    recording, recordedSeconds, recordingDone, progressPct, maxSeconds,
    startRecording, stopRecording, onRetake,
    subtitleSize, subtitlePosition, onSubtitleSizeChange, onSubtitlePositionChange,
    subtitleLanguage, onSubtitleLanguageChange,
    muteOriginalAudio, setMuteOriginalAudio,
    error, onNext,
  } = props
  const { t } = useTranslation('upload')
  const prevSrtRef = useRef(subtitleText)
  const [editLines, setEditLines] = useState(() => srtToTextLines(subtitleText).join('\n'))
  const [showStyleDetail, setShowStyleDetail] = useState(false)

  useEffect(() => {
    if (prevSrtRef.current !== subtitleText) {
      prevSrtRef.current = subtitleText
      setEditLines(srtToTextLines(subtitleText).join('\n'))
    }
  }, [subtitleText])

  function handleEditChange(val: string) {
    setEditLines(val)
    const lines = val.split('\n').map((l) => l.trim()).filter(Boolean)
    const newSrt = applyTextLinesToSrt(subtitleText, lines)
    prevSrtRef.current = newSrt
    setSubtitleText(newSrt)
  }

  const timeStr = `${String(Math.floor(recordedSeconds / 60)).padStart(2, '0')}:${String(recordedSeconds % 60).padStart(2, '0')}`
  const hasExtracted = subtitlePlainText.trim() !== ''
  const hasTextSubtitle = subtitleSource === 'text' && subtitleRawText.trim() !== ''
  const showStyle = (subtitleSource === 'video' || subtitleSource === 'record') ? hasExtracted : hasTextSubtitle

  const SIZE_LABELS: Record<SubtitleSize, string> = {
    small: t('caption.subtitleSizeSmall'), large: t('caption.subtitleSizeLarge'),
  }
  const POSITION_LABELS: Record<SubtitlePosition, string> = {
    top: t('caption.subtitlePositionTop'), center: t('caption.subtitlePositionCenter'), bottom: t('caption.subtitlePositionBottom'),
  }
  const LANGUAGE_OPTIONS: { value: SubtitleLanguage; label: string }[] = [
    { value: 'ko', label: t('caption.subtitleLanguageKo') },
    { value: 'en', label: t('caption.subtitleLanguageEn') },
    { value: 'auto', label: t('caption.subtitleLanguageAuto') },
  ]
  const previewText = (hasTextSubtitle ? subtitleRawText.split('\n')[0] : srtToTextLines(subtitleText).find((l) => l.trim())) || t('caption.subtitlePreview')

  const SOURCES: { value: SubtitleSource; label: string; icon: typeof Video; show: boolean }[] = [
    { value: 'video', label: t('subtitle.sourceVideo'), icon: Video, show: hasVideo },
    { value: 'record', label: t('subtitle.sourceRecord'), icon: Mic, show: true },
    { value: 'text', label: t('subtitle.sourceText'), icon: Type, show: true },
  ]

  return (
    <div className="flex flex-1 flex-col px-6 pt-4 gap-4 overflow-y-auto">
      <div>
        <p className="text-body font-semibold text-theme-primary">{t('subtitle.title')} <span className="text-label font-normal text-theme-muted">{t('subtitle.optional')}</span></p>
        <p className="text-label text-theme-muted mt-1">{t('subtitle.hint')}</p>
      </div>

      {/* 소스 선택 탭 */}
      <div className="flex gap-2">
        {SOURCES.filter((s) => s.show).map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            type="button"
            onClick={() => setSubtitleSource(value)}
            className={`flex flex-1 items-center justify-center gap-2 rounded-card py-3 text-label font-medium transition-colors ${
              subtitleSource === value ? 'bg-accent text-accent-fg' : 'bg-theme-surface text-theme-muted'
            }`}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {/* 영상 음성 추출 */}
      {subtitleSource === 'video' && (
        <div className="rounded-card bg-theme-surface p-4 flex flex-col gap-3">
          {videoAudioStatus === 'analyzing' && (
            <div className="flex items-center gap-2"><Loader2 size={14} className="animate-spin text-accent" /><span className="text-label text-theme-muted">{t('record.analyzing')}</span></div>
          )}
          {subtitleExtracting && videoAudioStatus !== 'analyzing' && (
            <div className="flex items-center gap-2"><Loader2 size={14} className="animate-spin text-accent" /><span className="text-label text-theme-muted">{t('record.extracting')}</span></div>
          )}
          {videoAudioStatus === 'has_audio' && !subtitleExtracting && hasExtracted && (
            <>
              <div className="flex items-center justify-between">
                <p className="text-label text-theme-muted">{t('record.extractedLabel')}</p>
                <button onClick={onClearSubtitle} className="flex items-center gap-1 text-label text-theme-muted hover:text-danger"><X size={11} /> {t('record.removeSubtitle')}</button>
              </div>
              <textarea value={editLines} onChange={(e) => handleEditChange(e.target.value)} rows={4} className="w-full resize-none rounded-card bg-theme-surface2 px-3 py-2 text-body text-theme-primary outline-none focus:ring-2 focus:ring-accent" />
            </>
          )}
          {videoAudioStatus === 'no_audio' && (
            <div className="flex items-start gap-2"><VolumeX size={14} className="text-theme-muted mt-1" /><p className="text-label text-theme-muted">{t('record.noAudio')}</p></div>
          )}
          {videoAudioStatus === 'error' && (
            <div className="flex items-start gap-2"><AlertCircle size={14} className="text-theme-muted mt-1" /><p className="text-label text-theme-muted">{t('record.extractFailed')}</p></div>
          )}
        </div>
      )}

      {/* 녹음 */}
      {subtitleSource === 'record' && (
        <div className="rounded-card bg-theme-surface p-4 flex flex-col gap-4">
          <p className="text-label text-theme-muted leading-relaxed">{t('record.recordingHint', { maxSeconds })}</p>
          <div className="flex flex-col items-center gap-3">
            {recordingDone ? (
              <div className="flex flex-col items-center gap-2">
                <div className="flex h-16 w-16 items-center justify-center rounded-pill bg-accent/20"><Mic size={26} strokeWidth={1.5} className="text-accent" /></div>
                <span className="text-label text-accent font-medium">{t('record.recordingDone', { time: timeStr })}</span>
                <button onClick={onRetake} className="flex items-center gap-1 text-label text-theme-muted"><X size={12} /> {t('record.retake')}</button>
              </div>
            ) : !recording ? (
              <button onClick={startRecording} className="flex h-16 w-16 items-center justify-center rounded-pill bg-accent"><Mic size={26} strokeWidth={1.5} className="text-black" /></button>
            ) : (
              <div className="flex flex-col items-center gap-2">
                <button onClick={stopRecording} className="flex h-16 w-16 items-center justify-center rounded-pill bg-danger"><MicOff size={26} strokeWidth={1.5} className="text-black" /></button>
                <span className="text-body font-mono text-danger">{timeStr}</span>
              </div>
            )}
            <div className="w-full h-1.5 rounded-pill bg-theme-surface2 overflow-hidden"><div className="h-full rounded-pill bg-danger transition-all duration-1000" style={{ width: `${progressPct}%` }} /></div>
          </div>
          {recordingDone && !subtitleExtracting && !hasExtracted && (
            <button onClick={onExtractFromAudio} className="flex items-center justify-center gap-2 rounded-card bg-accent/20 border border-accent/30 px-3 py-3 text-body text-accent font-medium"><Mic size={14} /> {t('record.extractFromAudio')}</button>
          )}
          {subtitleExtracting && (
            <div className="flex items-center gap-2"><Loader2 size={14} className="animate-spin text-accent" /><span className="text-label text-theme-muted">{t('record.extracting')}</span></div>
          )}
          {recordingDone && hasExtracted && (
            <>
              <p className="text-label text-theme-muted">{t('record.recordedSubtitleLabel')}</p>
              <textarea value={editLines} onChange={(e) => handleEditChange(e.target.value)} rows={3} className="w-full resize-none rounded-card bg-theme-surface2 px-3 py-2 text-body text-theme-primary outline-none focus:ring-2 focus:ring-accent" />
            </>
          )}
        </div>
      )}

      {/* 직접 입력 — 카드 안에 카드를 두지 않는다. 안내문은 placeholder 로 합치고
          글자 수는 입력칸 안쪽 여백에 얹어 컨테이너를 하나로 유지한다. */}
      {subtitleSource === 'text' && (
        <div className="relative">
          <textarea
            value={subtitleRawText}
            onChange={(e) => setSubtitleRawText(e.target.value.slice(0, 500))}
            maxLength={500}
            rows={4}
            placeholder={t('subtitle.textPlaceholder')}
            className="block w-full resize-none rounded-card bg-theme-surface px-4 py-3 pb-8 text-body text-theme-primary placeholder-theme-muted outline-none focus:ring-2 focus:ring-accent"
          />
          <span className="pointer-events-none absolute bottom-3 right-4 text-label text-theme-muted">{subtitleRawText.length}/500</span>
        </div>
      )}

      {/* 원본 음성 토글 (영상 있을 때) */}
      {hasVideo && (
        <button onClick={() => setMuteOriginalAudio(!muteOriginalAudio)} className="flex items-center justify-between rounded-card bg-theme-surface px-4 py-3">
          <div className="flex items-center gap-2 text-label text-theme-muted">
            {muteOriginalAudio ? <VolumeX size={13} className="text-theme-muted" /> : <Volume2 size={13} className="text-accent" />}
            <span>{muteOriginalAudio ? t('record.muteOriginal') : t('record.keepOriginal')}</span>
          </div>
          <div className={`relative inline-flex h-5 w-9 items-center rounded-pill transition-colors duration-200 ${muteOriginalAudio ? 'bg-theme-surface2' : 'bg-accent'}`}>
            <span className={`inline-block h-3.5 w-3.5 transform rounded-pill bg-white shadow transition-transform duration-200 ${muteOriginalAudio ? 'translate-x-1' : 'translate-x-[18px]'}`} />
          </div>
        </button>
      )}

      {/* 고급 설정 (자막 스타일) — 링크로 펼침 */}
      {showStyle && (
        <div>
          <button type="button" onClick={() => setShowStyleDetail((v) => !v)} className="flex items-center gap-1 text-label text-theme-muted underline underline-offset-2">
            {t('caption.subtitleStyle')}
            <ChevronDown size={13} className={`transition-transform ${showStyleDetail ? 'rotate-180' : ''}`} />
          </button>
          {showStyleDetail && (
          <div className="space-y-3 mt-3">
          <div className="flex items-center gap-3">
            <span className="text-label text-theme-muted w-10 flex-shrink-0">{t('caption.subtitleSize')}</span>
            <div className="flex gap-2">
              {(['small', 'large'] as SubtitleSize[]).map((s) => (
                <button key={s} type="button" onClick={() => onSubtitleSizeChange(s)} className={`rounded-card px-3 py-2 text-label font-medium ${subtitleSize === s ? 'bg-accent text-accent-fg' : 'bg-theme-surface2 text-theme-muted'}`}>{SIZE_LABELS[s]}</button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-label text-theme-muted w-10 flex-shrink-0">{t('caption.subtitlePosition')}</span>
            <div className="flex gap-2">
              {(['top', 'center', 'bottom'] as SubtitlePosition[]).map((p) => (
                <button key={p} type="button" onClick={() => onSubtitlePositionChange(p)} className={`rounded-card px-3 py-2 text-label font-medium ${subtitlePosition === p ? 'bg-accent text-accent-fg' : 'bg-theme-surface2 text-theme-muted'}`}>{POSITION_LABELS[p]}</button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-label text-theme-muted w-10 flex-shrink-0">{t('caption.subtitleLanguage')}</span>
            <div className="flex gap-2">
              {LANGUAGE_OPTIONS.map(({ value, label }) => (
                <button key={value} type="button" onClick={() => onSubtitleLanguageChange(value)} className={`rounded-card px-2 py-2 text-label font-medium ${subtitleLanguage === value ? 'bg-accent text-accent-fg' : 'bg-theme-surface2 text-theme-muted'}`}>{label}</button>
              ))}
            </div>
          </div>
          <div className="rounded-card overflow-hidden bg-black" style={{ aspectRatio: '9/16', maxHeight: '180px' }}>
            <div className={`relative w-full h-full flex flex-col items-center px-2 ${POSITION_FLEX_CLASS[subtitlePosition]}`}>
              <div className="px-2 py-1 rounded max-w-full text-center" style={{ backgroundColor: 'rgba(0,0,0,0.8)' }}>
                <span className={`text-white font-medium break-words ${SIZE_TEXT_CLASS[subtitleSize]}`}>{previewText}</span>
              </div>
            </div>
          </div>
          </div>
          )}
        </div>
      )}

      {error && <p className="text-body text-danger">{error}</p>}

      <div className="mt-auto flex flex-col items-center gap-3 pb-2">
        <button onClick={onNext} disabled={recording || subtitleExtracting} className="w-full flex items-center justify-center gap-2 rounded-card bg-accent py-3 font-semibold text-accent-fg disabled:opacity-40">
          {t('record.next')} <ChevronRight size={18} />
        </button>
        <button onClick={() => { setSubtitleSource('none'); onNext() }} className="text-body text-theme-muted underline underline-offset-2 py-1">
          {t('record.skip')}
        </button>
      </div>
    </div>
  )
}
