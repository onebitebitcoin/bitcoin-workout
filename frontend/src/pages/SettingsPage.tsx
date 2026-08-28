import { ChevronLeft, Check, X, Smartphone, Download, ChevronRight, ChevronDown, LogOut, Pencil, Camera, Loader2, RefreshCw, Globe, UserPlus } from 'lucide-react'
import { useState, useRef, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import { useAuthStore } from '../store/auth'
import UserAvatar from '../components/UserAvatar'

const ANDROID_APK_URL = 'https://github.com/onebitebitcoin/stack-health/releases/download/v0.11.1-android/app-release.apk'

const ROW = 'flex items-center justify-between px-4 py-3.5'
const LABEL = 'text-sm text-theme-primary'
const GROUP = 'rounded-xl bg-theme-surface overflow-hidden'
const SECTION = 'text-[10px] font-medium uppercase tracking-widest text-theme-muted px-1 mb-2'

export default function SettingsPage() {
  const navigate = useNavigate()
  const { t, i18n } = useTranslation(['profile', 'common'])
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)
  const logout = useAuthStore((s) => s.logout)
  const [editingLn, setEditingLn] = useState(false)
  const [lnInput, setLnInput] = useState(user?.lightning_address ?? '')
  const [saving, setSaving] = useState(false)
  const [lnSaved, setLnSaved] = useState(false)
  const [lnError, setLnError] = useState('')

  const [editingUsername, setEditingUsername] = useState(false)
  const [usernameInput, setUsernameInput] = useState(user?.username ?? '')
  const [usernameError, setUsernameError] = useState('')
  const [savingUsername, setSavingUsername] = useState(false)
  const [usernameSaved, setUsernameSaved] = useState(false)

  const [showIosGuide, setShowIosGuide] = useState(false)
  const [devMode, setDevMode] = useState(() => !!(user?.app_settings?.developer_mode))
  const [devModeLoading, setDevModeLoading] = useState(false)

  const [avatarUploading, setAvatarUploading] = useState(false)
  const [avatarError, setAvatarError] = useState('')
  const avatarInputRef = useRef<HTMLInputElement>(null)

  const currentLang = i18n.language?.startsWith('en') ? 'en' : 'ko'

  function handleLanguageChange(lang: 'ko' | 'en') {
    void i18n.changeLanguage(lang)
    localStorage.setItem('app-language', lang)
  }

  function compressImage(file: File, maxPx: number, quality: number): Promise<Blob> {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file)
      const img = new Image()
      img.onload = () => {
        URL.revokeObjectURL(url)
        const scale = Math.min(1, maxPx / Math.max(img.width, img.height))
        const w = Math.round(img.width * scale)
        const h = Math.round(img.height * scale)
        const canvas = document.createElement('canvas')
        canvas.width = w
        canvas.height = h
        canvas.getContext('2d')!.drawImage(img, 0, 0, w, h)
        canvas.toBlob(
          (blob) => (blob ? resolve(blob) : reject(new Error('canvas toBlob failed'))),
          'image/jpeg',
          quality,
        )
      }
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('image load failed')) }
      img.src = url
    })
  }

  async function handleAvatarChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!avatarInputRef.current) return
    avatarInputRef.current.value = ''
    if (!file) return

    if (file.size > 5 * 1024 * 1024) {
      setAvatarError(t('profile:avatarSizeError'))
      return
    }

    setAvatarUploading(true)
    setAvatarError('')
    try {
      const compressed = await compressImage(file, 200, 0.82)
      const form = new FormData()
      form.append('file', new File([compressed], 'avatar.jpg', { type: 'image/jpeg' }))
      const res = await client.post<{ data: typeof user }>('/auth/avatar', form)
      if (res.data.data) setUser(res.data.data)
    } catch {
      setAvatarError(t('profile:avatarUploadError'))
    } finally {
      setAvatarUploading(false)
    }
  }


  async function toggleDevMode() {
    const next = !devMode
    setDevModeLoading(true)
    try {
      const res = await client.patch<{ data: typeof user }>('/auth/me', {
        app_settings: { ...(user?.app_settings ?? {}), developer_mode: next },
      })
      if (res.data.data) setUser(res.data.data)
      setDevMode(next)
    } finally {
      setDevModeLoading(false)
    }
  }

  async function saveUsername(e: FormEvent) {
    e.preventDefault()
    if (usernameInput.trim().length < 2 || usernameInput.trim().length > 30) {
      setUsernameError(t('profile:nicknameLengthError'))
      return
    }
    setSavingUsername(true)
    setUsernameError('')
    try {
      const res = await client.patch<{ data: typeof user }>('/auth/me', { username: usernameInput.trim() })
      if (res.data.data) setUser(res.data.data)
      setEditingUsername(false)
      setUsernameSaved(true)
      setTimeout(() => setUsernameSaved(false), 2000)
    } catch {
      setUsernameError(t('profile:nicknameConflictError'))
    } finally {
      setSavingUsername(false)
    }
  }

  function isValidLightningAddress(addr: string): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addr)
  }

  async function saveLightningAddress(e: FormEvent) {
    e.preventDefault()
    const trimmed = lnInput.trim()
    if (trimmed && !isValidLightningAddress(trimmed)) {
      setLnError(t('profile:lightningAddressHint'))
      return
    }
    setLnError('')
    setSaving(true)
    try {
      const res = await client.patch<{ data: typeof user }>('/auth/me', { lightning_address: trimmed || null })
      if (res.data.data) setUser(res.data.data)
      setEditingLn(false)
      setLnSaved(true)
      setTimeout(() => setLnSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col h-[100dvh] bg-theme-page pb-nav-safe lg:max-w-2xl lg:mx-auto">
      {/* 헤더 */}
      <div className="flex items-center gap-3 px-4 pt-5 pb-4">
        <button onClick={() => navigate(-1)} className="p-1 text-theme-muted hover:text-theme-primary transition-colors">
          <ChevronLeft size={20} strokeWidth={1.5} />
        </button>
        <h1 className="text-base font-bold text-theme-primary">{t('profile:settings')}</h1>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pt-4 space-y-4">

        {/* 계정 */}
        <div>
          <p className={SECTION}>{t('profile:account')}</p>
          <div className={GROUP}>
            {/* 프로필 이미지 */}
            <div className={`${ROW} border-b border-theme-surface2`}>
              <span className={LABEL}>{t('profile:profilePhoto')}</span>
              <div className="flex flex-col items-end gap-1">
                <label
                  htmlFor="avatar-file-input"
                  className={`relative group ${avatarUploading ? 'pointer-events-none' : 'cursor-pointer'}`}
                  aria-label={t('profile:profilePhoto')}
                >
                  <UserAvatar
                    username={user?.username ?? ''}
                    avatarUrl={user?.avatar_url}
                    profileColor={(user?.app_settings?.profile_color as string | null) ?? null}
                    size={44}
                  />
                  <div className={`absolute inset-0 rounded-full flex items-center justify-center bg-black/40 transition-opacity ${avatarUploading ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>
                    {avatarUploading
                      ? <Loader2 size={16} className="text-white animate-spin" />
                      : <Camera size={16} className="text-white" />
                    }
                  </div>
                </label>
                <input
                  id="avatar-file-input"
                  ref={avatarInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  className="hidden"
                  disabled={avatarUploading}
                  onChange={handleAvatarChange}
                />
              </div>
            </div>
            {avatarError && <p className="text-[10px] text-red-400 px-4 py-1">{avatarError}</p>}

            {/* 닉네임 */}
            <div>
              <div className={ROW}>
                <span className={LABEL}>{t('profile:nickname')}</span>
                {!editingUsername ? (
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm text-theme-subtle">@{user?.username}</span>
                    {usernameSaved
                      ? <Check size={11} className="text-green-400" />
                      : <button
                          onClick={() => { setEditingUsername(true); setUsernameInput(user?.username ?? '') }}
                          className="text-theme-muted hover:text-theme-primary transition-colors"
                        >
                          <Pencil size={13} strokeWidth={1.5} />
                        </button>
                    }
                  </div>
                ) : (
                  <form onSubmit={saveUsername} className="flex items-center gap-2">
                    <input
                      type="text"
                      value={usernameInput}
                      onChange={(e) => setUsernameInput(e.target.value)}
                      autoFocus
                      maxLength={30}
                      className="w-36 bg-theme-surface2 rounded-lg px-2.5 py-1 text-sm text-theme-primary outline-none border border-accent"
                    />
                    <button type="submit" disabled={savingUsername} className="text-accent disabled:opacity-50">
                      <Check size={15} />
                    </button>
                    <button type="button" onClick={() => { setEditingUsername(false); setUsernameError('') }} className="text-theme-muted">
                      <X size={15} />
                    </button>
                  </form>
                )}
              </div>
              {usernameError && <p className="text-[10px] text-red-400 px-4 pb-2">{usernameError}</p>}
            </div>

            {/* 이메일 */}
            <div>
              <div className={ROW}>
                <span className={LABEL}>{t('profile:email')}</span>
                <span className="text-sm text-theme-subtle truncate max-w-[180px]">{user?.email}</span>
              </div>
            </div>

            {/* Lightning 주소 */}
            <div>
              <div className={ROW}>
                <span className={LABEL}>{t('profile:lightningAddress')}</span>
                {!editingLn ? (
                  <div className="flex items-center gap-1.5">
                    {lnSaved
                      ? <span className="flex items-center gap-1 text-xs text-green-400"><Check size={11} />{t('common:saved')}</span>
                      : <span className="text-sm text-theme-subtle truncate max-w-[150px]">
                          {user?.lightning_address ?? t('profile:lightningAddressPlaceholder')}
                        </span>
                    }
                    {!lnSaved && (
                      <button
                        onClick={() => { setEditingLn(true); setLnInput(user?.lightning_address ?? '') }}
                        className="text-theme-muted hover:text-theme-primary transition-colors flex-shrink-0"
                      >
                        <Pencil size={13} strokeWidth={1.5} />
                      </button>
                    )}
                  </div>
                ) : null}
              </div>
              {editingLn && (
                <form onSubmit={saveLightningAddress} className="px-4 pb-3 space-y-1">
                  <div className="flex items-center gap-2 rounded-lg bg-theme-surface2 px-3 py-2">
                    <input
                      type="text"
                      value={lnInput}
                      onChange={(e) => { setLnInput(e.target.value); setLnError('') }}
                      placeholder="you@wallet.com"
                      autoFocus
                      className="flex-1 bg-transparent text-sm text-theme-primary outline-none font-mono"
                    />
                    <button type="submit" disabled={saving} className="text-accent disabled:opacity-50">
                      <Check size={15} />
                    </button>
                    <button type="button" onClick={() => { setEditingLn(false); setLnError('') }} className="text-theme-muted">
                      <X size={15} />
                    </button>
                  </div>
                  {lnError && <p className="text-[10px] text-red-400">{lnError}</p>}
                </form>
              )}
            </div>
          </div>
        </div>

        {/* 언어 */}
        <div>
          <p className={SECTION}>{t('common:language')}</p>
          <div className={GROUP}>
            <div className={ROW}>
              <div className="flex items-center gap-2">
                <Globe size={13} className="text-theme-muted" />
                <span className={LABEL}>{t('profile:languageToggleLabel')}</span>
              </div>
              <div className="flex items-center gap-1 bg-theme-surface2 rounded-lg p-0.5">
                <button
                  onClick={() => handleLanguageChange('ko')}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                    currentLang === 'ko'
                      ? 'bg-accent text-white'
                      : 'text-theme-subtle hover:text-theme-primary'
                  }`}
                >
                  {t('common:languageKo')}
                </button>
                <button
                  onClick={() => handleLanguageChange('en')}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                    currentLang === 'en'
                      ? 'bg-accent text-white'
                      : 'text-theme-subtle hover:text-theme-primary'
                  }`}
                >
                  {t('common:languageEn')}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* 앱 다운로드 */}
        <div>
          <p className={SECTION}>{t('profile:appDownload')}</p>
          <div className={GROUP}>
            {/* Android */}
            <a
              href={ANDROID_APK_URL}
              target="_blank"
              rel="noopener noreferrer"
              className={ROW}
            >
              <div className="flex items-center gap-2">
                <Smartphone size={13} className="text-[#3DDC84]" />
                <span className={LABEL}>{t('profile:androidApk')}</span>
              </div>
              <Download size={14} className="text-theme-muted" />
            </a>

            {/* iOS PWA */}
            <button
              onClick={() => setShowIosGuide((v) => !v)}
              className={`w-full ${ROW}`}
            >
              <div className="flex items-center gap-2">
                <Smartphone size={13} className="text-blue-400" />
                <span className={LABEL}>{t('profile:iosPwa')}</span>
              </div>
              <ChevronDown size={14} className={`text-theme-muted transition-transform ${showIosGuide ? 'rotate-180' : ''}`} />
            </button>

            {showIosGuide && (
              <div className="px-4 pb-3 space-y-1.5">
                {([
                  t('profile:iosGuideStep1'),
                  t('profile:iosGuideStep2'),
                  t('profile:iosGuideStep3'),
                  t('profile:iosGuideStep4'),
                ] as string[]).map((step) => (
                  <p key={step} className="text-xs text-theme-subtle">{step}</p>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* 정보 */}
        <div>
          <p className={SECTION}>{t('profile:info')}</p>
          <div className={GROUP}>
            <button
              onClick={() => navigate('/invite')}
              className={`w-full ${ROW}`}
            >
              <span className={`${LABEL} flex items-center gap-2`}><UserPlus size={15} className="text-theme-muted" /> {t('profile:inviteFriends')}</span>
              <ChevronRight size={14} className="text-theme-muted" />
            </button>
            <button
              onClick={() => navigate('/terms')}
              className={`w-full ${ROW}`}
            >
              <span className={LABEL}>{t('profile:terms')}</span>
              <ChevronRight size={14} className="text-theme-muted" />
            </button>
            <div className={ROW}>
              <span className={LABEL}>{t('profile:version')}</span>
              <div className="flex items-center gap-2">
                <span className="text-sm text-theme-subtle font-mono">v{__APP_VERSION__}</span>
                <button
                  onClick={() => window.location.reload()}
                  className="text-theme-subtle hover:text-theme-muted transition-colors active:opacity-50"
                  aria-label={t('common:retry')}
                >
                  <RefreshCw size={12} />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* 개발자 */}
        <div>
          <p className={SECTION}>{t('profile:developer')}</p>
          <div className={GROUP}>
            <div className={ROW}>
              <div>
                <span className={LABEL}>{t('profile:developerMode')}</span>
                <p className="text-[11px] text-theme-muted mt-0.5">{t('profile:developerModeDesc')}</p>
              </div>
              <button
                onClick={toggleDevMode}
                disabled={devModeLoading}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 ${devMode ? 'bg-accent' : 'bg-theme-surface2'} disabled:opacity-50`}
              >
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 ${devMode ? 'translate-x-6' : 'translate-x-1'}`} />
              </button>
            </div>
          </div>
        </div>

        {/* 로그아웃 */}
        <button
          onClick={() => { logout(); window.location.href = '/login' }}
          className="w-full flex items-center justify-center gap-2 rounded-xl bg-red-500/10 px-4 py-3.5 text-sm font-semibold text-red-400 hover:bg-red-500/20 active:opacity-70 transition-colors"
        >
          <LogOut size={15} strokeWidth={2} />
          {t('profile:logout')}
        </button>

      </div>
    </div>
  )
}
