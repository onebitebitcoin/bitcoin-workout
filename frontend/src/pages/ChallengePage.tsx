import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Target, Users, CheckCircle, Plus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import type { Challenge } from '../api/types'
import { useAuthStore } from '../store/auth'

function formatMonthDay(dateStr: string) {
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function ChallengeCard({
  challenge,
  onNavigate,
}: {
  challenge: Challenge
  onNavigate: (id: number) => void
}) {
  const { t } = useTranslation('challenge')

  return (
    <div
      className="rounded-xl bg-theme-surface cursor-pointer active:opacity-80 overflow-hidden flex"
      onClick={() => onNavigate(challenge.id)}
    >
      {(challenge.image_thumb_url ?? challenge.image_url) ? (
        <img
          src={challenge.image_thumb_url ?? challenge.image_url ?? ''}
          alt=""
          loading="lazy"
          decoding="async"
          className="w-24 flex-shrink-0 object-cover self-stretch"
        />
      ) : (
        <div className="w-24 flex-shrink-0 bg-theme-surface2 self-stretch" />
      )}

      <div className="flex-1 min-w-0 px-3 py-2.5 flex flex-col gap-1">
        {/* title + completed icon */}
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-semibold text-theme-primary text-sm leading-tight truncate">{challenge.title}</h3>
          {!challenge.is_active && (
            <span className="shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-zinc-700/50 text-theme-muted">{t('card.ended')}</span>
          )}
          {challenge.is_active && challenge.completed && <CheckCircle size={15} className="text-accent flex-shrink-0" />}
        </div>

        {/* description */}
        {challenge.description && (
          <p className="text-[11px] text-theme-muted leading-snug line-clamp-1">{challenge.description}</p>
        )}

        {/* progress */}
        {challenge.joined && (
          <div className="flex items-center gap-1 text-[10px] text-accent font-medium">
            <CheckCircle size={10} strokeWidth={2} />
            {t('card.certCount', { count: challenge.my_upload_count })}
          </div>
        )}

        {/* bottom info + button */}
        <div className="flex items-center justify-between mt-auto pt-0.5">
          <div className="flex items-center gap-1 text-[10px] text-theme-subtle">
            <Users size={11} />
            <span>{t('card.participantCount', { count: challenge.participant_count })}</span>
            <span>·</span>
            <span>~{formatMonthDay(challenge.end_date)}</span>
          </div>
          {challenge.completed ? (
            <span className="text-[10px] font-semibold text-accent">{t('card.completed')}</span>
          ) : challenge.joined ? (
            <span className="text-[10px] font-semibold text-accent">{t('card.joined')}</span>
          ) : (
            <span className="rounded-lg bg-accent px-2.5 py-1 text-[10px] font-semibold text-accent-fg">
              {t('card.join')}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

export default function ChallengePage() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const { t } = useTranslation('challenge')
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState<'all' | 'joined' | 'available' | 'closed'>('all')

  const { data: challenges = [], isLoading } = useQuery<Challenge[]>({
    queryKey: ['challenges', q, filter],
    queryFn: async () => {
      const params: Record<string, string | boolean> = {}
      if (q) params.q = q
      if (filter === 'joined') params.joined = true
      if (filter === 'available') params.available = true
      if (filter === 'closed') params.closed = true
      const res = await client.get<{ data: { challenges: Challenge[] } }>('/challenges', { params })
      return res.data.data.challenges
    },
  })

  return (
    <div className="flex flex-col h-[100dvh] overflow-y-auto bg-theme-page pb-nav-safe lg:max-w-2xl lg:mx-auto">
      <div className="px-4 pt-5 pb-3 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-theme-primary">{t('pageTitle')}</h1>
          <p className="text-xs text-theme-muted mt-0.5">{t('pageSubtitle')}</p>
        </div>
        {user && (
          <button
            onClick={() => navigate('/challenges/create')}
            className="flex items-center gap-1.5 rounded-xl bg-accent px-3 py-1.5 text-xs font-semibold text-accent-fg"
          >
            <Plus size={13} />
            {t('addChallenge')}
          </button>
        )}
      </div>

      {/* filters */}
      {user && (
        <div className="px-4 mb-3 flex gap-2">
          {(['all', 'joined', 'available', 'closed'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                filter === f ? 'bg-accent text-accent-fg' : 'bg-theme-surface text-theme-muted'
              }`}
            >
              {t(`filter.${f}`)}
            </button>
          ))}
        </div>
      )}

      {/* search */}
      <div className="px-4 mb-4">
        <div className="flex items-center gap-2 rounded-xl bg-theme-surface px-3 py-2.5">
          <Search size={16} className="text-theme-subtle flex-shrink-0" />
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('searchPlaceholder')}
            className="flex-1 bg-transparent text-sm text-theme-primary placeholder-theme-subtle outline-none"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      ) : challenges.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 py-16 text-center px-6">
          <Target size={40} className="text-theme-surface2" strokeWidth={1} />
          <p className="text-sm text-theme-muted">
            {filter === 'joined'
              ? t('empty.joined')
              : filter === 'available'
              ? t('empty.available')
              : filter === 'closed'
              ? t('empty.closed')
              : q
              ? t('empty.search')
              : t('empty.default')}
          </p>
        </div>
      ) : (
        <div className="px-4 flex flex-col gap-3">
          {challenges.map((c) => (
            <ChallengeCard
              key={c.id}
              challenge={c}
              onNavigate={(id) => navigate(`/challenges/${id}`)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
