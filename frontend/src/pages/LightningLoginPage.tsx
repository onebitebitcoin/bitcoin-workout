import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { Copy, Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import { LN_POLL_INTERVAL_MS, LN_LOGIN_EXPIRE_MS } from '../lib/constants'
import { useAuthStore } from '../store/auth'
import type { User } from '../api/types'
import LogoMark from '../components/LogoMark'

export default function LightningLoginPage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)

  const [lnChallenge, setLnChallenge] = useState<{ k1: string; lnurl: string } | null>(null)
  const [lnError, setLnError] = useState('')
  const [lnLoading, setLnLoading] = useState(true)
  const [lnExpired, setLnExpired] = useState(false)
  const [lnCopied, setLnCopied] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function startChallenge() {
    setLnLoading(true)
    setLnError('')
    setLnExpired(false)
    setLnChallenge(null)

    client
      .get<{ data: { k1: string; lnurl: string } }>('/auth/lnauth/challenge')
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
    startChallenge()
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function copyToClipboard(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      window.prompt('아래 주소를 복사하세요:', text)
    }
  }

  return (
    <div className="flex min-h-[100dvh] flex-col items-center justify-center bg-theme-page px-6">
      <div className="mb-2 flex h-16 w-16 items-center justify-center rounded-2xl bg-theme-surface text-accent">
        <LogoMark aria-label={t('logoAlt')} role="img" size={40} />
      </div>
      <p className="mb-1 text-2xl font-bold text-accent">Bitcoiners</p>
      <p className="mb-8 text-sm text-theme-muted">{t('lightningLoginTitle')}</p>

      <div className="w-full max-w-sm flex flex-col gap-4">
        {lnLoading && <p className="text-center text-sm text-theme-muted">{t('qrGenerating')}</p>}
        {lnError && <p className="text-center text-sm text-red-400">{lnError}</p>}
        {lnExpired && (
          <div className="text-center">
            <p className="mb-2 text-sm text-theme-muted">{t('qrExpired')}</p>
            <button
              onClick={startChallenge}
              className="text-sm text-accent underline"
            >
              {t('regenerate')}
            </button>
          </div>
        )}
        {lnChallenge && !lnExpired && (
          <>
            <div className="flex justify-center">
              <div className="rounded-xl bg-white p-4">
                <QRCodeSVG value={`lightning:${lnChallenge.lnurl}`} size={200} />
              </div>
            </div>
            <p className="text-center text-xs text-theme-muted">
              {t('scanQrCode')}
            </p>
            <button
              onClick={() => {
                copyToClipboard(lnChallenge.lnurl).then(() => {
                  setLnCopied(true)
                  setTimeout(() => setLnCopied(false), 2000)
                })
              }}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-theme-border bg-theme-surface px-3 py-3 text-sm text-theme-muted transition-colors hover:bg-theme-surface2"
            >
              {lnCopied ? (
                <>
                  <Check size={15} className="text-green-500" />
                  <span className="text-green-500">{t('copied')}</span>
                </>
              ) : (
                <>
                  <Copy size={15} />
                  {t('copyLnurl')}
                </>
              )}
            </button>
            <div className="flex items-center justify-center gap-2 text-xs text-theme-subtle">
              <div className="h-2 w-2 animate-pulse rounded-full bg-yellow-500" />
              {t('waitingForAuth')}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
