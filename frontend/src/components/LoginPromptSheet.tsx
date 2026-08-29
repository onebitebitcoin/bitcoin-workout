import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

interface LoginPromptSheetProps {
  onClose: () => void
}

export default function LoginPromptSheet({ onClose }: LoginPromptSheetProps) {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center p-4"
      style={{ backgroundColor: 'var(--overlay)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-card bg-theme-surface p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-1 h-1 w-10 rounded-pill bg-theme-border mx-auto" />
        <h2 className="mt-4 text-center text-title text-theme-primary">{t('loginRequired')}</h2>
        <p className="mt-1 text-center text-body text-theme-muted">
          {t('loginToLike')}
        </p>
        <button
          onClick={() => navigate('/login')}
          className="mt-5 w-full rounded-card bg-accent py-3 font-semibold text-accent-fg"
        >
          {t('loginOrRegister')}
        </button>
        <button onClick={onClose} className="mt-3 w-full py-2 text-body text-theme-muted">
          {t('later')}
        </button>
      </div>
    </div>
  )
}
