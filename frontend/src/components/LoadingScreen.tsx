import { useTranslation } from 'react-i18next'
import LogoMark from './LogoMark'

export default function LoadingScreen() {
  const { t } = useTranslation('auth')
  return (
    <div className="flex h-[100dvh] flex-col items-center justify-center gap-4 bg-theme-page px-6 text-center">
      <div className="text-accent">
        <LogoMark aria-hidden="true" size={56} />
      </div>
      <div className="text-center">
        <p className="text-body font-semibold tracking-widest text-theme-primary uppercase">
          Bitcoiners
        </p>
        <p className="mt-1 text-label text-theme-muted">{t('loadingStack')}</p>
      </div>
    </div>
  )
}
