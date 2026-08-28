import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Share2, Copy, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import toast from 'react-hot-toast'
import client from '../api/client'

interface ReferralData {
  referral_code: string
  invited_count: number
}

export default function InvitePage() {
  const { t } = useTranslation('profile')
  const navigate = useNavigate()

  const { data, isLoading } = useQuery<ReferralData>({
    queryKey: ['my-referral'],
    queryFn: async () => {
      const res = await client.get<{ data: ReferralData }>('/users/me/referral')
      return res.data.data
    },
  })

  const inviteUrl = data ? `${window.location.origin}/login/register?ref=${data.referral_code}` : ''

  function copyLink() {
    if (!inviteUrl) return
    window.navigator.clipboard?.writeText(inviteUrl)
      .then(() => toast.success(t('inviteCopied')))
      .catch(() => toast(inviteUrl))
  }

  function shareLink() {
    if (!inviteUrl) return
    if (typeof navigator !== 'undefined' && 'share' in navigator) {
      navigator.share({ title: 'Bitcoiners', text: t('inviteShareText'), url: inviteUrl })
        .catch((err) => { if (!(err instanceof DOMException && err.name === 'AbortError')) copyLink() })
    } else {
      copyLink()
    }
  }

  return (
    <div className="flex flex-col h-[100dvh] bg-theme-page pb-nav-safe lg:max-w-2xl lg:mx-auto">
      <div className="flex items-center gap-3 px-4 pt-5 pb-4">
        <button onClick={() => navigate(-1)} className="text-theme-muted flex-shrink-0"><ArrowLeft size={20} /></button>
        <h1 className="text-body font-semibold text-theme-primary">{t('inviteTitle')}</h1>
      </div>

      <div className="flex flex-col gap-4 px-6">
        <p className="text-body text-theme-muted leading-relaxed">{t('inviteDescription')}</p>

        {/* 초대 수 */}
        <div className="flex items-center justify-between rounded-card bg-theme-surface px-4 py-3">
          <div className="flex items-center gap-2 text-body text-theme-muted">
            <Users size={16} /> {t('invitedCount')}
          </div>
          <span className="text-title text-accent">{isLoading ? '—' : data?.invited_count ?? 0}</span>
        </div>

        {/* 초대 링크 */}
        <div className="rounded-card bg-theme-surface px-4 py-3 space-y-2">
          <p className="text-label font-medium text-theme-muted">{t('inviteLink')}</p>
          <div className="flex items-center gap-2">
            <input
              readOnly
              value={inviteUrl}
              className="flex-1 rounded-card bg-theme-surface2 px-3 py-2 text-label text-theme-primary outline-none truncate"
            />
            <button onClick={copyLink} className="flex-shrink-0 flex h-9 w-9 items-center justify-center rounded-card bg-theme-surface2 text-theme-muted" aria-label={t('inviteCopyAria')}>
              <Copy size={15} />
            </button>
          </div>
        </div>

        <button onClick={shareLink} disabled={!inviteUrl} className="flex w-full items-center justify-center gap-2 rounded-card bg-accent py-3 font-semibold text-accent-fg disabled:opacity-60">
          <Share2 size={18} /> {t('inviteShare')}
        </button>
      </div>
    </div>
  )
}
