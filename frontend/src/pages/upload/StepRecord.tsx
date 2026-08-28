import { useEffect, useRef, useState } from 'react'
import { Mic, MicOff, X, ChevronRight, Loader2, VolumeX, AlertCircle, Volume2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { srtToTextLines, applyTextLinesToSrt } from '../../utils/subtitles'

type VideoAudioStatus = 'idle' | 'analyzing' | 'has_audio' | 'no_audio' | 'error'

interface SegmentDetail {
  text: string
  no_speech_prob: number
  avg_logprob: number
  compression_ratio: number
  start: number
  end: number
}

interface Props {
  previewUrl: string | null
  recording: boolean
  recordedSeconds: number
  recordingDone: boolean
  progressPct: number
  error: string
  maxSeconds: number
  videoAudioStatus: VideoAudioStatus
  subtitleText: string
  setSubtitleText: (v: string) => void
  subtitlePlainText: string
  subtitleExtracting: boolean
  onExtractFromAudio: () => void
  onClearSubtitle: () => void
  startRecording: () => void
  stopRecording: () => void
  onRetake: () => void
  onNext: () => void
  muteOriginalAudio: boolean
  setMuteOriginalAudio: (v: boolean) => void
  devMode?: boolean
  subtitleDebugMetrics?: Record<string, unknown> | null
}

export default function StepRecord({
  previewUrl, recording, recordedSeconds, recordingDone,
  progressPct, error, maxSeconds,
  devMode = false, subtitleDebugMetrics = null,
  videoAudioStatus,
  subtitleText, setSubtitleText, subtitlePlainText, subtitleExtracting,
  onExtractFromAudio, onClearSubtitle,
  startRecording, stopRecording, onRetake, onNext,
  muteOriginalAudio, setMuteOriginalAudio,
}: Props) {
  const { t } = useTranslation('upload')
  const prevSrtRef = useRef(subtitleText)
  const [editLines, setEditLines] = useState(() => srtToTextLines(subtitleText).join('\n'))
  const [showRecording, setShowRecording] = useState(false)

  // Auto-reveal recording section if user is already recording or done
  useEffect(() => {
    if (recording || recordingDone) setShowRecording(true)
  }, [recording, recordingDone])

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

  function handleClearSubtitle() {
    prevSrtRef.current = ''
    setSubtitleText('')
    setEditLines('')
    onClearSubtitle()
  }

  const timeStr = `${String(Math.floor(recordedSeconds / 60)).padStart(2, '0')}:${String(recordedSeconds % 60).padStart(2, '0')}`
  const hasSubtitle = subtitlePlainText.trim() !== ''
  const analysisComplete = videoAudioStatus !== 'idle' && videoAudioStatus !== 'analyzing'
  const canProceed = analysisComplete && !recording && !subtitleExtracting

  return (
    <div className="flex flex-1 flex-col px-6 pt-4 gap-4 overflow-y-auto">
      {previewUrl && (
        <video
          src={previewUrl}
          className="h-36 w-full rounded-card object-cover flex-shrink-0"
          muted autoPlay loop playsInline
        />
      )}

      {/* 영상 오디오 분석 결과 */}
      <div className="rounded-card bg-theme-surface p-4 flex flex-col gap-3">
        <p className="text-body font-semibold text-theme-primary">
          {t('record.subtitle')} <span className="text-label font-normal text-theme-muted">{t('record.subtitleOptional')}</span>
        </p>

        {videoAudioStatus === 'analyzing' && (
          <div className="flex items-center gap-2 py-1">
            <Loader2 size={14} className="animate-spin text-accent" />
            <span className="text-label text-theme-muted">{t('record.analyzing')}</span>
          </div>
        )}

        {videoAudioStatus === 'has_audio' && (
          subtitleExtracting ? (
            <div className="flex items-center gap-2 py-1">
              <Loader2 size={14} className="animate-spin text-accent" />
              <span className="text-label text-theme-muted">{t('record.extracting')}</span>
            </div>
          ) : hasSubtitle ? (
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <p className="text-label text-theme-muted">{t('record.extractedLabel')}</p>
                <button
                  onClick={handleClearSubtitle}
                  className="flex items-center gap-1 text-label text-theme-muted hover:text-danger transition-colors"
                >
                  <X size={11} /> {t('record.removeSubtitle')}
                </button>
              </div>
              <textarea
                value={editLines}
                onChange={(e) => handleEditChange(e.target.value)}
                rows={4}
                className="w-full resize-none rounded-card bg-theme-surface2 px-3 py-2 text-body text-theme-primary placeholder-theme-muted outline-none focus:ring-2 focus:ring-accent"
              />
              <button
                onClick={() => setMuteOriginalAudio(!muteOriginalAudio)}
                className="flex items-center justify-between w-full pt-1"
              >
                <div className="flex items-center gap-2 text-label text-theme-muted">
                  {muteOriginalAudio
                    ? <VolumeX size={13} className="text-theme-muted" />
                    : <Volume2 size={13} className="text-accent" />}
                  <span>{muteOriginalAudio ? t('record.muteOriginal') : t('record.keepOriginal')}</span>
                </div>
                <div className={`relative inline-flex h-5 w-9 items-center rounded-pill transition-colors duration-200 ${muteOriginalAudio ? 'bg-theme-surface2' : 'bg-accent'}`}>
                  <span className={`inline-block h-3.5 w-3.5 transform rounded-pill bg-white shadow transition-transform duration-200 ${muteOriginalAudio ? 'translate-x-1' : 'translate-x-[18px]'}`} />
                </div>
              </button>
            </div>
          ) : (
            <p className="text-label text-theme-muted py-1">{t('record.noSubtitle')}</p>
          )
        )}

        {videoAudioStatus === 'no_audio' && (
          <div className="flex items-start gap-2">
            <VolumeX size={14} className="text-theme-muted mt-1 flex-shrink-0" />
            <p className="text-label text-theme-muted leading-relaxed">
              {t('record.noAudio')}
            </p>
          </div>
        )}

        {videoAudioStatus === 'error' && (
          <div className="flex items-start gap-2">
            <AlertCircle size={14} className="text-theme-muted mt-1 flex-shrink-0" />
            <p className="text-label text-theme-muted leading-relaxed">{t('record.extractFailed')}</p>
          </div>
        )}
      </div>

      {/* 녹음 섹션 — 분석 완료 후에만 표시 */}
      {analysisComplete && (
        showRecording ? (
          <div className="rounded-card bg-theme-surface p-4 flex flex-col gap-4">
            <div>
              <p className="font-semibold text-theme-primary">{t('record.shareExperience')}</p>
              <p className="text-label text-theme-muted mt-1 leading-relaxed">
                {t('record.recordingHint', { maxSeconds })}
              </p>
            </div>

            <div className="flex flex-col items-center gap-3">
              {recordingDone ? (
                <div className="flex flex-col items-center gap-2">
                  <div className="flex h-16 w-16 items-center justify-center rounded-pill bg-accent/20">
                    <Mic size={26} strokeWidth={1.5} className="text-accent" />
                  </div>
                  <span className="text-label text-accent font-medium">{t('record.recordingDone', { time: timeStr })}</span>
                  <button onClick={onRetake} className="flex items-center gap-1 text-label text-theme-muted">
                    <X size={12} /> {t('record.retake')}
                  </button>
                </div>
              ) : !recording ? (
                <button
                  onClick={startRecording}
                  className="flex h-16 w-16 items-center justify-center rounded-pill bg-accent"
                >
                  <Mic size={26} strokeWidth={1.5} className="text-black" />
                </button>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <button
                    onClick={stopRecording}
                    className="flex h-16 w-16 items-center justify-center rounded-pill bg-danger"
                  >
                    <MicOff size={26} strokeWidth={1.5} className="text-black" />
                  </button>
                  <span className="text-body font-mono text-danger">{timeStr}</span>
                </div>
              )}

              <div className="w-full h-1.5 rounded-pill bg-theme-surface2 overflow-hidden">
                <div
                  className="h-full rounded-pill bg-danger transition-all duration-1000"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              {recording && (
                <p className="text-label text-theme-muted">{t('record.secondsLeft', { count: maxSeconds - recordedSeconds })}</p>
              )}
            </div>

            {recordingDone && !subtitleExtracting && !hasSubtitle && (
              <button
                onClick={onExtractFromAudio}
                className="flex items-center justify-center gap-2 rounded-card bg-accent/20 border border-accent/30 px-3 py-3 text-body text-accent font-medium hover:bg-accent/30 transition-colors"
              >
                <Mic size={14} />
                {t('record.extractFromAudio')}
              </button>
            )}

            {recordingDone && subtitleExtracting && (
              <div className="flex items-center gap-2 py-1">
                <Loader2 size={14} className="animate-spin text-accent" />
                <span className="text-label text-theme-muted">{t('record.extracting')}</span>
              </div>
            )}

            {recordingDone && hasSubtitle && (
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <p className="text-label text-theme-muted">{t('record.recordedSubtitleLabel')}</p>
                  <button
                    onClick={handleClearSubtitle}
                    className="flex items-center gap-1 text-label text-theme-muted hover:text-danger transition-colors"
                  >
                    <X size={11} /> {t('record.removeSubtitle')}
                  </button>
                </div>
                <textarea
                  value={editLines}
                  onChange={(e) => handleEditChange(e.target.value)}
                  rows={3}
                  className="w-full resize-none rounded-card bg-theme-surface2 px-3 py-2 text-body text-theme-primary placeholder-theme-muted outline-none focus:ring-2 focus:ring-accent"
                />
              </div>
            )}
          </div>
        ) : (
          <button
            onClick={() => setShowRecording(true)}
            className="flex items-center gap-3 rounded-card bg-theme-surface px-4 py-3 w-full text-left"
          >
            <div className="flex h-10 w-10 items-center justify-center rounded-pill bg-accent/20 flex-shrink-0">
              <Mic size={18} strokeWidth={1.5} className="text-accent" />
            </div>
            <div>
              <p className="text-body font-medium text-theme-primary">{t('record.shareExperience')}</p>
              <p className="text-label text-theme-muted mt-1">{t('record.recordingHintShort')}</p>
            </div>
          </button>
        )
      )}

      {error && <p className="text-body text-danger">{error}</p>}

      {devMode && subtitleDebugMetrics && (
        <div className="rounded-card bg-theme-surface border border-theme-surface2 p-3">
          <div className="flex items-center justify-between mb-2">
            <p className="text-eyebrow text-theme-muted">{t('record.devPanel')}</p>
            <button
              onClick={() => navigator.clipboard.writeText(JSON.stringify(subtitleDebugMetrics, null, 2))}
              className="text-label text-theme-muted hover:text-accent transition-colors px-2 py-1 rounded border border-theme-surface2 hover:border-accent"
            >
              {t('record.devCopy')}
            </button>
          </div>
          <div className="space-y-1 text-label font-mono text-theme-muted">
            {(['model', 'language', 'source', 'duration_sec', 'transcribe_seconds',
               'segments_total', 'avg_no_speech_prob', 'segments_kept', 'segments_filtered',
               'silence_ratio', 'silence_ranges_detected'] as const).map((key) => {
              const val = subtitleDebugMetrics[key]
              if (val === undefined || val === null) return null
              return (
                <div key={key} className="flex justify-between gap-2">
                  <span className="text-theme-muted">{key}</span>
                  <span className="text-theme-primary">{String(val)}</span>
                </div>
              )
            })}
          </div>
          {Array.isArray(subtitleDebugMetrics.segments_detail) && (subtitleDebugMetrics.segments_detail as SegmentDetail[]).length > 0 && (
            <div className="mt-2 border-t border-theme-surface2 pt-2 space-y-2">
              <p className="text-eyebrow text-theme-muted">{t('record.devSegments')}</p>
              {(subtitleDebugMetrics.segments_detail as SegmentDetail[]).map((seg, i) => {
                const dur = seg.end - seg.start
                const cps = dur > 0 ? seg.text.length / dur : 0
                const filtered = seg.no_speech_prob >= 0.45 || seg.avg_logprob < -0.75 || seg.compression_ratio > 2.4 || (dur > 0 && cps < 2.0)
                return (
                  <div key={i} className={`text-label font-mono rounded p-2 ${filtered ? 'bg-danger/10 text-danger' : 'bg-success/10 text-success'}`}>
                    <div className="flex justify-between gap-1 mb-1">
                      <span>{seg.start}s–{seg.end}s</span>
                      <span>nsp={seg.no_speech_prob} lp={seg.avg_logprob} cr={seg.compression_ratio} cps={cps.toFixed(1)}</span>
                    </div>
                    <div className="text-theme-primary truncate">{seg.text || '(empty)'}</div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      <div className="mt-auto flex flex-col items-center gap-3 pb-2">
        <button
          onClick={onNext}
          disabled={!canProceed}
          className="w-full flex items-center justify-center gap-2 rounded-card bg-accent py-3 font-semibold text-accent-fg disabled:opacity-40"
        >
          {t('record.next')} <ChevronRight size={18} />
        </button>
        {!recording && (
          <button onClick={onNext} className="text-body text-theme-muted underline underline-offset-2 py-1">
            {t('record.skip')}
          </button>
        )}
      </div>
    </div>
  )
}
