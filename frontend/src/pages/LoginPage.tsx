import { useNavigate, useSearchParams } from 'react-router-dom'
import { Zap, Mail, AlertCircle } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import LogoMark from '../components/LogoMark'
import { getApiErrorMessageFromBody } from '../api/errors'

export default function LoginPage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [googleLoading, setGoogleLoading] = useState(false)
  const [googleError, setGoogleError] = useState('')

  const errorParam = searchParams.get('error')

  async function handleGoogleLogin() {
    setGoogleLoading(true)
    setGoogleError('')
    try {
      const res = await fetch('/api/v1/auth/google', { redirect: 'manual' })
      if (res.type === 'opaqueredirect') {
        window.location.href = '/api/v1/auth/google'
      } else {
        const data = await res.json().catch(() => ({}))
        setGoogleError(getApiErrorMessageFromBody(data, t('googleUnavailable')))
        setGoogleLoading(false)
      }
    } catch {
      setGoogleError(t('serverUnreachable'))
      setGoogleLoading(false)
    }
  }

  return (
    <div className="flex min-h-[100dvh] flex-col items-center justify-center bg-theme-page px-6">
      <div className="relative mb-5 flex h-20 w-20 items-center justify-center rounded-3xl bg-theme-surface text-accent ring-1 ring-white/5">
        <div className="absolute inset-0 rounded-3xl bg-accent opacity-15 blur-2xl scale-[2] pointer-events-none" />
        <LogoMark aria-label={t('logoAlt')} role="img" size={44} />
      </div>
      <p className="mb-1 text-2xl font-bold text-accent">Bitcoiners</p>
      <p className="mb-8 text-sm text-theme-muted">{t('tagline')}</p>

      {errorParam && (
        <div className="mb-4 flex items-center gap-2 rounded-lg bg-red-500/10 px-4 py-2 text-sm text-red-400">
          <AlertCircle size={16} />
          <span>
            {errorParam === 'google_auth_failed'
              ? t('googleAuthFailed')
              : t('loginFailed')}
          </span>
        </div>
      )}

      <div className="w-full max-w-sm space-y-3">
        <div className="flex flex-col gap-1.5">
          <button
            onClick={handleGoogleLogin}
            disabled={googleLoading}
            className="flex w-full items-center justify-center gap-3 rounded-lg border border-theme-border bg-theme-surface px-4 py-3 font-medium text-theme-primary transition-colors hover:bg-theme-surface2 disabled:opacity-60"
          >
            {googleLoading ? (
              <svg className="h-4 w-4 animate-spin text-theme-muted" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
            ) : (
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4" />
                <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="#34A853" />
                <path d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05" />
                <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335" />
              </svg>
            )}
            {googleLoading ? t('googleConnecting') : t('continueWithGoogle')}
          </button>
          {googleError && (
            <div className="flex items-center gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">
              <AlertCircle size={13} />
              {googleError}
            </div>
          )}
        </div>

        <button
          onClick={() => navigate('/login/lightning')}
          className="flex w-full items-center justify-center gap-3 rounded-lg border border-theme-border bg-theme-surface px-4 py-3 font-medium text-theme-primary transition-colors hover:bg-theme-surface2"
        >
          <Zap size={18} className="text-yellow-500" />
          {t('continueWithLightning')}
        </button>

        <div className="flex items-center gap-3">
          <div className="h-px flex-1 bg-theme-border" />
          <span className="text-xs text-theme-subtle">{t('or')}</span>
          <div className="h-px flex-1 bg-theme-border" />
        </div>

        <button
          onClick={() => navigate('/login/email')}
          className="flex w-full items-center justify-center gap-3 rounded-lg border border-theme-border bg-theme-surface px-4 py-3 font-medium text-theme-primary transition-colors hover:bg-theme-surface2"
        >
          <Mail size={18} className="text-theme-muted" />
          {t('loginWithEmail')}
        </button>
      </div>
    </div>
  )
}
