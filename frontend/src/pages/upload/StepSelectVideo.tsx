import type { ChangeEvent, RefObject } from 'react'
import { useTranslation } from 'react-i18next'
import LogoMark from '../../components/LogoMark'

interface Props {
  fileInputRef: RefObject<HTMLInputElement>
  error: string
  setError: (e: string) => void
  onFileChange: (e: ChangeEvent<HTMLInputElement>) => void
}

export default function StepSelectVideo({ fileInputRef, error, setError, onFileChange }: Props) {
  const { t } = useTranslation('upload')

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6">
      <input
        ref={fileInputRef}
        id="video-file-input"
        type="file"
        accept="video/mp4,video/quicktime"
        className="hidden"
        onChange={(e) => { setError(''); onFileChange(e) }}
      />
      <label
        htmlFor="video-file-input"
        className={`flex flex-col items-center gap-3 rounded-card border-2 border-dashed p-12 transition-colors cursor-pointer ${
          error ? 'border-danger text-danger' : 'border-theme-border text-theme-muted hover:border-accent hover:text-accent'
        }`}
      >
        <LogoMark size={48} />
        <span>{t('selectVideo.prompt')}</span>
        <span className="text-label">{t('selectVideo.hint')}</span>
      </label>
      {error && <p className="text-body text-danger text-center">{error}</p>}
    </div>
  )
}
