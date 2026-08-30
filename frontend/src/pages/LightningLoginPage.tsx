import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { Copy, Check, AlertTriangle, ArrowLeft } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import { LN_POLL_INTERVAL_MS, LN_LOGIN_EXPIRE_MS } from '../lib/constants'
import { useAuthStore } from '../store/auth'
import type { User } from '../api/types'
import LogoMark from '../components/LogoMark'

// LNURL 에 박히는 도메인이 곧 계정 신원이다 (LUD-04). 서버는 QR 을 만들 때 사용자가
// 누구인지 알 수 없으므로, 어느 쪽인지는 사용자가 직접 고른다.
// 배경: docs/LNURL-DOMAIN-MIGRATION.md
type LnauthDomain = 'legacy' | 'current'

export default function LightningLoginPage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)

  const [domain, setDomain] = useState<LnauthDomain | null>(null)
  const [lnChallenge, setLnChallenge] = useState<{ k1: string; lnurl: string } | null>(null)
  const [lnError, setLnError] = useState('')
  const [lnLoading, setLnLoading] = useState(true)
  const [lnExpired, setLnExpired] = useState(false)
  const [lnCopied, setLnCopied] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function startChallenge(forDomain: LnauthDomain) {
    setLnLoading(true)
    setLnError('')
    setLnExpired(false)
    setLnChallenge(null)

    client
      .get<{ data: { k1: string; lnurl: string } }>(
        `/auth/lnauth/challenge?domain=${forDomain}`,
      )
      .then((res) => {
        const { k1, lnurl } = res.data.data
        setLnChallenge({ k1, lnurl })
        setLnLoading(false)

        pollRef.current = setInterval(async () => {
          try {
            const r = await client.get<{ data: { verified: boolean; token?: string; refresh_token?: string; is_new_user?: boolean } }>(
              `/auth/lnauth/verify?k1=${k1}`,
            )
            if (r.data.data.verified && r.data.data.token) {
              if (pollRef.current) clearInterval(pollRef.current)
              if (timeoutRef.current) clearTimeout(timeoutRef.current)
              const token = r.data.data.token
              const refreshToken = r.data.data.refresh_token ?? ''
              if (r.data.data.is_new_user) {
                navigate(`/setup-username?token=${encodeURIComponent(token)}&refresh=${encodeURIComponent(refreshToken)}`)
                return
              }
              const me = await client.get<{ data: User }>('/auth/me', {
                headers: { Authorization: `Bearer ${token}` },
              })
              login(token, me.data.data, refreshToken)
              navigate('/')
            }
          } catch {
            // ignore poll errors
          }
        }, LN_POLL_INTERVAL_MS)

        timeoutRef.current = setTimeout(() => {
          if (pollRef.current) clearInterval(pollRef.current)
          setLnExpired(true)
        }, LN_LOGIN_EXPIRE_MS)
      })
      .catch(() => {
        setLnLoading(false)
        setLnError(t('challengeFailed'))
      })
  }

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [])

  function choose(next: LnauthDomain) {
    setDomain(next)
    startChallenge(next)
  }

  function resetChoice() {
    if (pollRef.current) clearInterval(pollRef.current)
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    setDomain(null)
    setLnChallenge(null)
    setLnError('')
    setLnExpired(false)
  }

  async function copyToClipboard(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      window.prompt('아래 주소를 복사하세요:', text)
    }
  }

  return (
    <div className="flex min-h-[100dvh] flex-col items-center justify-center bg-theme-page px-6">
      <div className="mb-2 flex h-16 w-16 items-center justify-center rounded-card bg-theme-surface text-accent">
        <LogoMark aria-label={t('logoAlt')} role="img" size={40} />
      </div>
      <p className="mb-1 text-display font-display text-accent">Orange Story</p>
      <p className="mb-8 text-body text-theme-muted">{t('lightningLoginTitle')}</p>

      <div className="w-full max-w-sm flex flex-col gap-4">
        {!domain && (
          <>
            <p className="text-center text-body text-theme-muted">{t('lightningWhoAreYou')}</p>
            <button
              onClick={() => choose('legacy')}
              className="w-full rounded-card border border-theme-border bg-theme-surface px-4 py-4 text-left transition-colors hover:bg-theme-surface2"
            >
              <span className="block text-body text-theme-text">{t('lightningExistingAccount')}</span>
              <span className="block text-label text-theme-muted">{t('lightningExistingAccountDesc')}</span>
            </button>
            <button
              onClick={() => choose('current')}
              className="w-full rounded-card border border-theme-border bg-theme-surface px-4 py-4 text-left transition-colors hover:bg-theme-surface2"
            >
              <span className="block text-body text-theme-text">{t('lightningNewAccount')}</span>
              <span className="block text-label text-theme-muted">{t('lightningNewAccountDesc')}</span>
            </button>
          </>
        )}
        {domain && lnLoading && <p className="text-center text-body text-theme-muted">{t('qrGenerating')}</p>}
        {lnError && <p className="text-center text-body text-danger">{lnError}</p>}
        {lnExpired && (
          <div className="text-center">
            <p className="mb-2 text-body text-theme-muted">{t('qrExpired')}</p>
            <button
              onClick={() => domain && startChallenge(domain)}
              className="text-body text-accent underline"
            >
              {t('regenerate')}
            </button>
          </div>
        )}
        {lnChallenge && !lnExpired && (
          <>
            {domain === 'current' && (
              <div className="flex gap-2 rounded-card border border-theme-border bg-theme-surface px-3 py-3">
                <AlertTriangle size={15} className="mt-0.5 shrink-0 text-danger" />
                <p className="text-label text-theme-muted">{t('lightningNewAccountWarning')}</p>
              </div>
            )}
            <div className="flex justify-center">
              <div className="rounded-card bg-white p-4">
                <QRCodeSVG value={`lightning:${lnChallenge.lnurl}`} size={200} />
              </div>
            </div>
            <p className="text-center text-label text-theme-muted">
              {t('scanQrCode')}
            </p>
            <button
              onClick={() => {
                copyToClipboard(lnChallenge.lnurl).then(() => {
                  setLnCopied(true)
                  setTimeout(() => setLnCopied(false), 2000)
                })
              }}
              className="flex w-full items-center justify-center gap-2 rounded-card border border-theme-border bg-theme-surface px-3 py-3 text-body text-theme-muted transition-colors hover:bg-theme-surface2"
            >
              {lnCopied ? (
                <>
                  <Check size={15} className="text-success" />
                  <span className="text-success">{t('copied')}</span>
                </>
              ) : (
                <>
                  <Copy size={15} />
                  {t('copyLnurl')}
                </>
              )}
            </button>
            <div className="flex items-center justify-center gap-2 text-label text-theme-muted">
              <div className="h-2 w-2 animate-pulse rounded-pill bg-lightning" />
              {t('waitingForAuth')}
            </div>
            <button
              onClick={resetChoice}
              className="flex items-center justify-center gap-1 text-label text-theme-muted underline"
            >
              <ArrowLeft size={13} />
              {t('lightningChangeChoice')}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
