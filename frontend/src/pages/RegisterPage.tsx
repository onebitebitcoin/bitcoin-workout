import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import { getApiErrorMessage } from '../api/errors'
import { useAuthStore } from '../store/auth'
import type { User } from '../api/types'
import LogoMark from '../components/LogoMark'

export default function RegisterPage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)

  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [lightningAddress, setLightningAddress] = useState('')
  const [emailError, setEmailError] = useState('')
  const [emailLoading, setEmailLoading] = useState(false)

  function isValidLightningAddress(addr: string): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addr)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setEmailError('')

    if (lightningAddress.trim() && !isValidLightningAddress(lightningAddress.trim())) {
      setEmailError(t('lightningAddressInvalid'))
      return
    }

    setEmailLoading(true)
    try {
      const referralCode = (() => {
        try { return localStorage.getItem('referral_code') } catch { return null }
      })()
      const res = await client.post<{ data: { access_token: string; refresh_token: string; user: User } }>(
        '/auth/register',
        { email, username, password, ...(referralCode ? { referral_code: referralCode } : {}) },
      )
      try { localStorage.removeItem('referral_code') } catch { /* ignore */ }
      const { access_token, refresh_token, user: registeredUser } = res.data.data
      if (lightningAddress.trim()) {
        const updated = await client.patch<{ data: User }>(
          '/auth/me',
          { lightning_address: lightningAddress.trim() },
          { headers: { Authorization: `Bearer ${access_token}` } },
        )
        login(access_token, updated.data.data, refresh_token)
      } else {
        login(access_token, registeredUser, refresh_token)
      }
      navigate('/')
    } catch (err: unknown) {
      setEmailError(getApiErrorMessage(err, t('common:unknownError')))
    } finally {
      setEmailLoading(false)
    }
  }

  return (
    <div className="flex min-h-[100dvh] flex-col items-center justify-center bg-theme-page px-6">
      <div className="mb-2 flex h-16 w-16 items-center justify-center rounded-2xl bg-theme-surface text-accent">
        <LogoMark aria-label={t('logoAlt')} role="img" size={40} />
      </div>
      <p className="mb-1 text-2xl font-bold text-accent">Bitcoiners</p>
      <p className="mb-8 text-sm text-theme-muted">{t('registerTitle')}</p>

      <div className="w-full max-w-sm">
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <input
            type="email"
            placeholder={t('emailPlaceholder')}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full rounded-lg bg-theme-surface px-4 py-3 text-theme-primary placeholder-theme-subtle outline-none focus:ring-2 focus:ring-accent"
          />
          <input
            type="text"
            placeholder={t('usernamePlaceholder')}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            className="w-full rounded-lg bg-theme-surface px-4 py-3 text-theme-primary placeholder-theme-subtle outline-none focus:ring-2 focus:ring-accent"
          />
          <input
            type="text"
            placeholder={t('lightningAddressPlaceholder')}
            value={lightningAddress}
            onChange={(e) => setLightningAddress(e.target.value)}
            className="w-full rounded-lg bg-theme-surface px-4 py-3 text-theme-primary placeholder-theme-subtle outline-none focus:ring-2 focus:ring-accent"
          />
          <div className="flex justify-end -mt-2">
            <Link to="/lightning-guide" className="text-xs text-accent underline underline-offset-2">
              {t('howToCreateWallet')}
            </Link>
          </div>
          <input
            type="password"
            placeholder={t('passwordPlaceholder')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full rounded-lg bg-theme-surface px-4 py-3 text-theme-primary placeholder-theme-subtle outline-none focus:ring-2 focus:ring-accent"
          />
          {emailError && <p className="text-sm text-red-400">{emailError}</p>}
          <button
            type="submit"
            disabled={emailLoading}
            className="w-full rounded-lg bg-accent py-3 font-semibold text-accent-fg transition-opacity disabled:opacity-60"
          >
            {emailLoading ? t('processing') : t('registerButton')}
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="w-full text-sm text-theme-muted underline"
          >
            {t('alreadyHaveAccount')}
          </button>
        </form>
      </div>
    </div>
  )
}
