import { useQuery } from '@tanstack/react-query'
import { Plus, Target, Users, CheckCircle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import { useAuthStore } from '../store/auth'
import type { Challenge } from '../api/types'

function formatYmd(dateStr: string) {
  const d = new Date(dateStr)
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`
}

export default function MyChallengeDashboardPage() {
  const navigate = useNavigate()
  const isAdmin = useAuthStore((s) => s.user?.is_admin ?? false)
  const { t } = useTranslation('challenge')

  const { data: challenges = [], isLoading, isError } = useQuery<Challenge[]>({
    queryKey: ['my-challenges'],
    queryFn: async () => {
      const res = await client.get<{ data: { challenges: Challenge[] } }>('/challenges/created')
      return res.data.data.challenges
    },
  })

  return (
    <div className="flex flex-col h-[100dvh] overflow-y-auto bg-theme-page pb-nav-safe lg:max-w-2xl lg:mx-auto">
      <div className="px-4 pt-5 pb-3 flex items-center justify-between">
        <h1 className="text-lg font-bold text-theme-primary">{t('myDashboard.title')}</h1>
        {isAdmin && (
          <button
            onClick={() => navigate('/challenges/create')}
            className="rounded-full bg-accent p-1.5"
          >
            <Plus size={16} className="text-accent-fg" />
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center gap-2 py-16">
          <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      ) : isError ? (
        <div className="px-4 py-16 text-center">
          <p className="text-sm text-red-500">{t('myDashboard.loadError')}</p>
        </div>
      ) : challenges.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-center px-6">
          <Target size={40} className="text-theme-surface2" strokeWidth={1} />
          <p className="text-sm text-theme-muted">{t('myDashboard.noChallenge')}</p>
          {isAdmin && (
            <button
              onClick={() => navigate('/challenges/create')}
              className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-accent-fg"
            >
              {t('myDashboard.createButton')}
            </button>
          )}
        </div>
      ) : (
        <div className="px-4 flex flex-col gap-3">
          {challenges.map((c) => (
            <div key={c.id} className="rounded-2xl bg-theme-surface p-4">
              <div className="flex items-start justify-between gap-2 mb-2">
                <h3 className="font-semibold text-theme-primary text-sm leading-snug flex-1 min-w-0">
                  {c.title}
                </h3>
                <span
                  className={`flex-shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                    c.is_active
                      ? 'bg-accent/15 text-accent'
                      : 'bg-theme-surface2 text-theme-muted'
                  }`}
                >
                  {c.is_active ? t('myDashboard.active') : t('myDashboard.ended')}
                </span>
              </div>

              <p className="text-xs text-theme-muted mb-3">
                {formatYmd(c.start_date)} ~ {formatYmd(c.end_date)}
              </p>

              <div className="flex items-center gap-3 mb-3">
                <div className="flex items-center gap-1 text-xs text-theme-subtle">
                  <Users size={12} />
                  <span>{t('myDashboard.participantCount', { count: c.participant_count })}</span>
                </div>
                <div className="flex items-center gap-1 text-xs text-theme-subtle">
                  <CheckCircle size={12} />
                  <span>{t('myDashboard.completedCount', { count: c.completed_count ?? 0 })}</span>
                </div>
              </div>

              <button
                onClick={() => navigate(`/challenges/${c.id}/dashboard`)}
                className="w-full rounded-xl border border-accent/40 py-1.5 text-xs font-medium text-accent"
              >
                {t('myDashboard.viewParticipants')}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
