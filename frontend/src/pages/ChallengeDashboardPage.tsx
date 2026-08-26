import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, Users, CheckCircle, TrendingUp, Target } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import client from '../api/client'
import type { Challenge, ChallengeParticipant } from '../api/types'
import LoadingScreen from '../components/LoadingScreen'

interface ParticipantsResponse {
  challenge: Challenge
  participants: ChallengeParticipant[]
}

export default function ChallengeDashboardPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { t } = useTranslation('challenge')

  const { data, isLoading, isError, error } = useQuery<ParticipantsResponse>({
    queryKey: ['challenge-participants', id],
    queryFn: async () => {
      const res = await client.get<{ data: ParticipantsResponse }>(`/challenges/${id}/participants`)
      return res.data.data
    },
  })

  if (isLoading) return <LoadingScreen />

  if (isError) {
    const axiosError = error as { response?: { status?: number } }
    const status = axiosError?.response?.status
    const is403or404 = status === 403 || status === 404
    return (
      <div className="flex flex-col h-[100dvh] bg-theme-page lg:max-w-2xl lg:mx-auto">
        <div className="px-4 pt-5 pb-3 flex items-center gap-3">
          <button onClick={() => navigate('/my-challenges')} className="text-theme-muted">
            <ChevronLeft size={20} />
          </button>
        </div>
        <div className="flex flex-col items-center justify-center flex-1 px-6 text-center">
          <p className="text-sm text-theme-muted">
            {is403or404 ? t('dashboard.accessDenied') : t('dashboard.loadError')}
          </p>
        </div>
      </div>
    )
  }

  const challenge = data?.challenge
  const participants = data?.participants ?? []

  const completedCount = participants.filter((p) => p.completed_at !== null).length
  const avgProgress =
    participants.length > 0
      ? Math.round(participants.reduce((sum, p) => sum + p.progress, 0) / participants.length)
      : 0

  return (
    <div className="flex flex-col h-[100dvh] overflow-y-auto bg-theme-page pb-nav-safe lg:max-w-2xl lg:mx-auto">
      <div className="px-4 pt-5 pb-3 flex items-center gap-3">
        <button onClick={() => navigate('/my-challenges')} className="text-theme-muted">
          <ChevronLeft size={20} />
        </button>
        <h1 className="text-base font-bold text-theme-primary truncate">{challenge?.title}</h1>
      </div>

      {/* stats */}
      <div className="px-4 mb-4 grid grid-cols-3 gap-2">
        <div className="rounded-xl bg-theme-surface p-3 text-center">
          <Users size={16} className="text-accent mx-auto mb-1" />
          <p className="text-lg font-bold text-theme-primary">{participants.length}</p>
          <p className="text-[10px] text-theme-muted">{t('dashboard.statsParticipants')}</p>
        </div>
        <div className="rounded-xl bg-theme-surface p-3 text-center">
          <CheckCircle size={16} className="text-accent mx-auto mb-1" />
          <p className="text-lg font-bold text-theme-primary">{completedCount}</p>
          <p className="text-[10px] text-theme-muted">{t('dashboard.statsCompleted')}</p>
        </div>
        <div className="rounded-xl bg-theme-surface p-3 text-center">
          <TrendingUp size={16} className="text-accent mx-auto mb-1" />
          <p className="text-lg font-bold text-theme-primary">{avgProgress}%</p>
          <p className="text-[10px] text-theme-muted">{t('dashboard.statsAvgProgress')}</p>
        </div>
      </div>

      {/* participant list */}
      <div className="px-4">
        <h2 className="text-sm font-semibold text-theme-primary mb-2">{t('dashboard.participantList')}</h2>
        {participants.length === 0 ? (
          <p className="text-sm text-theme-muted py-8 text-center">{t('dashboard.noParticipants')}</p>
        ) : (
          <div className="flex flex-col gap-2">
            {participants.map((p) => (
              <div key={p.user_id} className="rounded-xl bg-theme-surface px-4 py-3">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-sm font-medium text-theme-primary">{p.username}</span>
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-0.5 text-xs text-theme-muted">
                      <Target size={11} className="text-accent" />
                      {p.upload_count} / {p.condition_value}
                    </span>
                    {p.completed_at !== null && (
                      <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-medium text-accent">
                        {t('dashboard.statsCompleted')}
                      </span>
                    )}
                  </div>
                </div>
                <div className="h-1.5 w-full rounded-full bg-theme-surface2">
                  <div
                    className="h-1.5 rounded-full bg-accent transition-all"
                    style={{ width: `${p.progress}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
