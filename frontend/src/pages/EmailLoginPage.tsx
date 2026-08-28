import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import { getApiErrorMessage } from '../api/errors'
import { useAuthStore } from '../store/auth'
import type { User } from '../api/types'
import LogoMark from '../components/LogoMark'

export default function EmailLoginPage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [emailError, setEmailError] = useState('')
  const [emailLoading, setEmailLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setEmailError('')
    setEmailLoading(true)
    try {
      const res = await client.post<{ data: { access_token: string; refresh_token: string; user: User } }>(
        '/auth/login',
        { email, password },
      )
      login(res.data.data.access_token, res.data.data.user, res.data.data.refresh_token)
      navigate('/')
    } catch (err: unknown) {
      setEmailError(getApiErrorMessage(err, t('common:unknownError')))
    } finally {
      setEmailLoading(false)
    }
  }

  return (
    <div className="flex min-h-[100dvh] flex-col items-center justify-center bg-theme-page px-6">
      <div className="mb-2 flex h-16 w-16 items-center justify-center rounded-card bg-theme-surface text-accent">
        <LogoMark aria-label={t('logoAlt')} role="img" size={40} />
      </div>
      <p className="mb-1 text-display text-accent">Bitcoiners</p>
      <p className="mb-8 text-body text-theme-muted">{t('emailLoginTitle')}</p>

      <div className="w-full max-w-sm">
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <input
            type="email"
            placeholder={t('emailPlaceholder')}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full rounded-card bg-theme-surface px-4 py-3 text-theme-primary placeholder-theme-muted outline-none focus:ring-2 focus:ring-accent"
          />
          <input
            type="password"
            placeholder={t('passwordPlaceholder')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full rounded-card bg-theme-surface px-4 py-3 text-theme-primary placeholder-theme-muted outline-none focus:ring-2 focus:ring-accent"
          />
          {emailError && <p className="text-body text-danger">{emailError}</p>}
          <button
            type="submit"
            disabled={emailLoading}
            className="w-full rounded-card bg-accent py-3 font-semibold text-accent-fg transition-opacity disabled:opacity-60"
          >
            {emailLoading ? t('processing') : t('loginButton')}
          </button>
          <button
            type="button"
            onClick={() => navigate('/login/register')}
            className="w-full text-body text-theme-muted underline"
          >
            {t('noAccount')}
          </button>
        </form>
      </div>
    </div>
  )
}
