import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { CheckCircle, XCircle, Camera } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import { getApiErrorMessage } from '../api/errors'
import { useAuthStore } from '../store/auth'
import type { User } from '../api/types'
import LogoMark from '../components/LogoMark'
import { getProfileColor } from '../utils/profileColor'

const PROFILE_COLORS = [
  '#6366f1', '#8b5cf6', '#ec4899', '#f97316',
  '#14b8a6', '#22c55e', '#3b82f6', '#eab308',
]

export default function SetupUsernamePage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const login = useAuthStore((s) => s.login)

  const token = searchParams.get('token')
  const refreshToken = searchParams.get('refresh')

  const [username, setUsername] = useState('')
  const [lightningAddress, setLightningAddress] = useState('')
  const [available, setAvailable] = useState<boolean | null>(null)
  const [checking, setChecking] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [loadingUser, setLoadingUser] = useState(true)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [selectedColor] = useState(() => PROFILE_COLORS[Math.floor(Math.random() * PROFILE_COLORS.length)])
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!token) {
      navigate('/login', { replace: true })
    }
  }, [token, navigate])

  useEffect(() => {
    if (!token) return
    client.get<{ data: User }>('/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    }).then((res) => {
      const u = res.data.data
      if (u.username) setUsername(u.username)
      if (u.lightning_address) setLightningAddress(u.lightning_address)
      if (u.avatar_url) setPreviewUrl(u.avatar_url)
    }).catch(() => {}).finally(() => setLoadingUser(false))
  }, [token])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (username.length < 2) {
      setAvailable(null)
      return
    }
    setChecking(true)
    debounceRef.current = setTimeout(async () => {
      try {
        const params = new URLSearchParams({ username })
        if (token) params.set('token', token)
        const res = await client.get<{ data: { available: boolean } }>(
          `/auth/check-username?${params.toString()}`,
        )
        setAvailable(res.data.data.available)
      } catch {
        setAvailable(null)
      } finally {
        setChecking(false)
      }
    }, 400)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [username, token])

  function isValidLightningAddress(addr: string): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addr)
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || !token) return

    const objectUrl = URL.createObjectURL(file)
    setPreviewUrl(objectUrl)
    setUploading(true)

    try {
      const formData = new FormData()
      formData.append('file', file)
      await client.post<{ data: User }>('/auth/avatar', formData, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'multipart/form-data' },
      })
    } catch {
      setPreviewUrl(null)
    } finally {
      setUploading(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!token || !available) return

    if (lightningAddress.trim() && !isValidLightningAddress(lightningAddress.trim())) {
      setError(t('lightningAddressInvalid'))
      return
    }

    setError('')
    setSubmitting(true)
    try {
      const body: Record<string, string> = { username }
      if (lightningAddress.trim()) body.lightning_address = lightningAddress.trim()
      await client.patch('/auth/me', body, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const me = await client.get<{ data: User }>('/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      })
      login(token, me.data.data, refreshToken)
      navigate('/', { replace: true })
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, t('profileSetupFailed')))
    } finally {
      setSubmitting(false)
    }
  }

  const displayColor = getProfileColor(username || 'user', selectedColor)

  if (loadingUser) return null

  return (
    <div className="flex min-h-[100dvh] flex-col items-center justify-center bg-theme-page px-6">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-theme-surface text-accent">
        <LogoMark aria-label={t('logoAlt')} role="img" size={40} />
      </div>
      <p className="mb-1 text-xs font-bold tracking-[0.28em] text-accent uppercase">Bitcoiners</p>
      <p className="mb-8 text-sm text-theme-muted">{t('setupProfileTitle')}</p>

      <div className="w-full max-w-sm">
        <div className="flex justify-center mb-6">
          <div className="relative">
            <label htmlFor="setup-avatar-input" className="cursor-pointer">
              {previewUrl ? (
                <img src={previewUrl} alt={t('profileAlt')} className="h-20 w-20 rounded-full object-cover" />
              ) : (
                <div
                  className="h-20 w-20 rounded-full flex items-center justify-center font-bold text-white text-3xl"
                  style={{ backgroundColor: displayColor }}
                >
                  {username ? username[0].toUpperCase() : '?'}
                </div>
              )}
            </label>
            <label
              htmlFor="setup-avatar-input"
              className={`absolute -bottom-1 -right-1 flex h-7 w-7 items-center justify-center rounded-full bg-accent text-accent-fg shadow-md ${uploading ? 'pointer-events-none opacity-60' : 'cursor-pointer'}`}
            >
              {uploading ? (
                <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent-fg border-t-transparent" />
              ) : (
                <Camera size={13} strokeWidth={2} />
              )}
            </label>
            <input
              id="setup-avatar-input"
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              className="hidden"
              disabled={uploading}
              onChange={handleFileChange}
            />
          </div>
        </div>

        <p className="text-center text-xs text-theme-muted mb-6 -mt-2">
          {t('changePhoto')}
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <p className="text-xs text-theme-muted mb-1.5 ml-1">{t('nicknameLabel')}</p>
            <div className="relative">
              <input
                type="text"
                placeholder={t('nicknamePlaceholder')}
                value={username}
                onChange={(e) => setUsername(e.target.value.trim())}
                minLength={2}
                maxLength={30}
                required
                className="w-full rounded-lg bg-theme-surface px-4 py-3 pr-10 text-theme-primary placeholder-theme-subtle outline-none focus:ring-2 focus:ring-accent"
              />
              {username.length >= 2 && !checking && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                  {available === true && <CheckCircle size={18} className="text-green-500" />}
                  {available === false && <XCircle size={18} className="text-red-400" />}
                </div>
              )}
              {checking && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                </div>
              )}
            </div>
            {username.length >= 2 && !checking && (
              <p className={`mt-1 text-xs ml-1 ${available ? 'text-green-500' : 'text-red-400'}`}>
                {available ? t('usernameAvailable') : t('usernameTaken')}
              </p>
            )}
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5 ml-1">
              <p className="text-xs text-theme-muted">
                {t('lightningAddressLabel')} <span className="text-theme-subtle">{t('lightningAddressOptional')}</span>
              </p>
              <Link to="/lightning-guide" className="text-xs text-accent underline underline-offset-2">
                {t('howToCreateWallet')}
              </Link>
            </div>
            <div className="relative">
              <input
                type="text"
                placeholder="user@walletofsatoshi.com"
                value={lightningAddress}
                onChange={(e) => setLightningAddress(e.target.value)}
                className="w-full rounded-lg bg-theme-surface py-3 px-4 text-theme-primary placeholder-theme-subtle outline-none focus:ring-2 focus:ring-accent"
              />
            </div>
          </div>

          {error && <p className="text-sm text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={!available || submitting || uploading}
            className="w-full rounded-lg bg-accent py-3 font-semibold text-accent-fg transition-opacity disabled:opacity-40"
          >
            {submitting ? t('settingUp') : t('startButton')}
          </button>
        </form>
      </div>
    </div>
  )
}
