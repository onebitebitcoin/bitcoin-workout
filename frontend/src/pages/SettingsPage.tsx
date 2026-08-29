import { ChevronLeft, Check, X, ChevronRight, LogOut, Pencil, Camera, Loader2, RefreshCw, Globe, UserPlus } from 'lucide-react'
import { useState, useRef, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import { useAuthStore } from '../store/auth'
import UserAvatar from '../components/UserAvatar'


const ROW = 'flex items-center justify-between gap-3 px-5 py-3 min-h-16'
const LABEL = 'text-body text-theme-primary'
// 옮겨 적는 값(아이디·이메일·주소·버전)은 Mono
const VALUE = 'text-label font-mono text-theme-muted'
const GROUP = 'rounded-card bg-theme-surface overflow-hidden'
const SECTION = 'text-eyebrow text-theme-muted px-1 mb-3'

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
      <div className="flex flex-col gap-2 px-5 pt-6 pb-5">
        <button onClick={() => navigate(-1)} className="-ml-3 h-11 w-11 flex items-center justify-center text-theme-muted hover:text-theme-primary transition-colors">
          <ChevronLeft size={18} strokeWidth={1.75} />
        </button>
        <h1 className="text-display text-theme-primary">{t('profile:settings')}</h1>
      </div>

      <div className="flex-1 overflow-y-auto px-5 space-y-6">

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
                  <div className={`absolute inset-0 rounded-pill flex items-center justify-center bg-black/40 transition-opacity ${avatarUploading ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>
                    {avatarUploading
                      ? <Loader2 size={18} className="text-white animate-spin" />
                      : <Camera size={18} className="text-white" />
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
            {avatarError && <p className="text-label text-danger px-5 pb-2">{avatarError}</p>}

            {/* 닉네임 */}
            <div>
              <div className={ROW}>
                <span className={LABEL}>{t('profile:nickname')}</span>
                {!editingUsername ? (
                  <div className="flex items-center gap-2">
                    <span className="text-label font-mono text-theme-muted">@{user?.username}</span>
                    {usernameSaved
                      ? <Check size={14} className="text-success" />
                      : <button
                          onClick={() => { setEditingUsername(true); setUsernameInput(user?.username ?? '') }}
                          className="text-theme-muted hover:text-theme-primary transition-colors"
                        >
                          <Pencil size={18} strokeWidth={1.75} />
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
                      className="w-40 bg-theme-surface2 rounded-card px-3 py-2 text-body text-theme-primary outline-none border border-accent"
                    />
                    <button type="submit" disabled={savingUsername} className="text-accent disabled:opacity-50">
                      <Check size={18} strokeWidth={1.75} />
                    </button>
                    <button type="button" onClick={() => { setEditingUsername(false); setUsernameError('') }} className="text-theme-muted">
                      <X size={18} strokeWidth={1.75} />
                    </button>
                  </form>
                )}
              </div>
              {usernameError && <p className="text-label text-danger px-5 pb-3">{usernameError}</p>}
            </div>

            {/* 이메일 */}
            <div>
              <div className={ROW}>
                <span className={LABEL}>{t('profile:email')}</span>
                <span className={`${VALUE} truncate max-w-[200px]`}>{user?.email}</span>
              </div>
            </div>

            {/* Lightning 주소 */}
            <div>
              <div className={ROW}>
                <span className={LABEL}>{t('profile:lightningAddress')}</span>
                {!editingLn ? (
                  <div className="flex items-center gap-2">
                    {lnSaved
                      ? <span className="flex items-center gap-1 text-label text-success"><Check size={14} />{t('common:saved')}</span>
                      : <span className={`truncate max-w-[170px] text-label text-theme-muted ${user?.lightning_address ? 'font-mono' : ''}`}>
                          {user?.lightning_address ?? t('profile:lightningAddressPlaceholder')}
                        </span>
                    }
                    {!lnSaved && (
                      <button
                        onClick={() => { setEditingLn(true); setLnInput(user?.lightning_address ?? '') }}
                        className="text-theme-muted hover:text-theme-primary transition-colors flex-shrink-0"
                      >
                        <Pencil size={18} strokeWidth={1.75} />
                      </button>
                    )}
                  </div>
                ) : null}
              </div>
              {editingLn && (
                <form onSubmit={saveLightningAddress} className="px-5 pb-4 space-y-2">
                  <div className="flex items-center gap-3 rounded-card bg-theme-surface2 px-4 py-3">
                    <input
                      type="text"
                      value={lnInput}
                      onChange={(e) => { setLnInput(e.target.value); setLnError('') }}
                      placeholder="you@wallet.com"
                      autoFocus
                      className="flex-1 bg-transparent text-body font-mono text-theme-primary outline-none"
                    />
                    <button type="submit" disabled={saving} className="text-accent disabled:opacity-50">
                      <Check size={18} strokeWidth={1.75} />
                    </button>
                    <button type="button" onClick={() => { setEditingLn(false); setLnError('') }} className="text-theme-muted">
                      <X size={18} strokeWidth={1.75} />
                    </button>
                  </div>
                  {lnError && <p className="text-label text-danger">{lnError}</p>}
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
              <div className="flex items-center gap-3">
                <Globe size={18} strokeWidth={1.75} className="text-theme-muted" />
                <span className={LABEL}>{t('profile:languageToggleLabel')}</span>
              </div>
              <div className="flex items-center gap-1 bg-theme-surface2 rounded-pill p-1">
                <button
                  onClick={() => handleLanguageChange('ko')}
                  className={`h-9 px-4 rounded-pill text-label transition-colors ${
                    currentLang === 'ko'
                      ? 'bg-accent font-semibold text-accent-fg'
                      : 'text-theme-muted hover:text-theme-primary'
                  }`}
                >
                  {t('common:languageKo')}
                </button>
                <button
                  onClick={() => handleLanguageChange('en')}
                  className={`h-9 px-4 rounded-pill text-label transition-colors ${
                    currentLang === 'en'
                      ? 'bg-accent font-semibold text-accent-fg'
                      : 'text-theme-muted hover:text-theme-primary'
                  }`}
                >
                  {t('common:languageEn')}
                </button>
              </div>
            </div>
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
              <span className={`${LABEL} flex items-center gap-3`}><UserPlus size={18} strokeWidth={1.75} className="text-theme-muted" /> {t('profile:inviteFriends')}</span>
              <ChevronRight size={18} strokeWidth={1.75} className="text-theme-muted" />
            </button>
            <button
              onClick={() => navigate('/terms')}
              className={`w-full ${ROW}`}
            >
              <span className={LABEL}>{t('profile:terms')}</span>
              <ChevronRight size={18} strokeWidth={1.75} className="text-theme-muted" />
            </button>
            <div className={ROW}>
              <span className={LABEL}>{t('profile:version')}</span>
              <div className="flex items-center gap-2">
                <span className={VALUE}>v{__APP_VERSION__}</span>
                <button
                  onClick={() => window.location.reload()}
                  className="text-theme-muted hover:text-theme-primary transition-colors active:opacity-50"
                  aria-label={t('common:retry')}
                >
                  <RefreshCw size={18} strokeWidth={1.75} />
                </button>
              </div>
            </div>
          </div>
        </div>


        {/* 로그아웃 */}
        <button
          onClick={() => { logout(); window.location.href = '/login' }}
          className="w-full h-14 flex items-center justify-center gap-3 rounded-card bg-theme-surface px-5 text-body font-semibold text-danger hover:bg-theme-surface2 active:opacity-70 transition-colors"
        >
          <LogOut size={18} strokeWidth={1.75} />
          {t('profile:logout')}
        </button>

      </div>
    </div>
  )
}
