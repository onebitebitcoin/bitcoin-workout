import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Target, ChevronRight, Plus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import type { Challenge } from '../api/types'
import { useAuthStore } from '../store/auth'

// 시간/날짜는 한국 시간(Asia/Seoul) 기준
function formatEndDate(dateStr: string, lang: string) {
  const isEn = lang.startsWith('en')
  // ko-KR + numeric 은 "10. 7." 처럼 마침표로 끝난다. long 이어야 "10월 7일"이 된다.
  return new Intl.DateTimeFormat(isEn ? 'en-US' : 'ko-KR', {
    month: isEn ? 'short' : 'long',
    day: 'numeric',
    timeZone: 'Asia/Seoul',
  }).format(new Date(dateStr))
}

function ChallengeCard({
  challenge,
  onNavigate,
}: {
  challenge: Challenge
  onNavigate: (id: number) => void
}) {
  const { t, i18n } = useTranslation('challenge')

  // 카드 전체가 상세로 가는 탭 타깃이다. 그 안에 버튼처럼 생긴 것을 두지 않고
  // 오른쪽에는 상태만 알린다 — 아직 참여 전이면 갈 곳이 있다는 표시(화살표)만.
  const status = !challenge.is_active ? (
    <span className="text-label text-theme-muted shrink-0">{t('card.ended')}</span>
  ) : challenge.completed ? (
    <span className="text-label font-semibold text-accent-text shrink-0">{t('card.completed')}</span>
  ) : challenge.joined ? (
    <span className="text-label font-semibold text-accent-text shrink-0">
      {challenge.my_upload_count > 0
        ? t('card.certCount', { count: challenge.my_upload_count })
        : t('card.joined')}
    </span>
  ) : (
    <ChevronRight size={18} strokeWidth={1.75} className="text-theme-muted shrink-0" />
  )

  return (
    <div
      className={`rounded-card bg-theme-surface cursor-pointer active:opacity-80 overflow-hidden flex ${
        challenge.is_active ? '' : 'opacity-60'
      }`}
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

      <div className="flex-1 min-w-0 px-5 py-4 flex flex-col gap-2">
        <h3 className="text-lead text-theme-primary truncate">{challenge.title}</h3>

        {challenge.description && (
          <p className="text-body text-theme-muted truncate">{challenge.description}</p>
        )}

        <div className="flex items-center justify-between gap-3">
          <span className="text-label text-theme-muted truncate">
            {t('card.participants', { count: challenge.participant_count })}
            {' · '}
            {t('card.endsOn', { date: formatEndDate(challenge.end_date, i18n.language) })}
          </span>
          {status}
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
      <div className="px-5 pt-8 pb-5 flex items-start justify-between gap-5">
        <div className="flex flex-col gap-2 min-w-0">
          <h1 className="text-display text-theme-primary">{t('pageTitle')}</h1>
          <p className="text-body text-theme-muted">{t('pageSubtitle')}</p>
        </div>
        {user && (
          <button
            onClick={() => navigate('/challenges/create')}
            className="h-11 shrink-0 flex items-center gap-2 rounded-card bg-accent px-4 text-label font-semibold text-accent-fg"
          >
            <Plus size={18} strokeWidth={2} />
            {t('addChallenge')}
          </button>
        )}
      </div>

      {/* filters */}
      {user && (
        <div className="px-5 mb-3 flex gap-2">
          {(['all', 'joined', 'available', 'closed'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`h-9 rounded-pill px-4 text-label transition-colors ${
                filter === f
                  ? 'bg-accent font-semibold text-accent-fg'
                  : 'bg-theme-surface text-theme-muted'
              }`}
            >
              {t(`filter.${f}`)}
            </button>
          ))}
        </div>
      )}

      {/* search */}
      <div className="px-5 mb-5">
        <div className="flex items-center gap-3 h-12 rounded-card bg-theme-surface px-4">
          <Search size={18} strokeWidth={1.75} className="text-theme-muted flex-shrink-0" />
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('searchPlaceholder')}
            className="flex-1 bg-transparent text-body text-theme-primary placeholder-theme-muted outline-none"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-pill animate-spin" />
        </div>
      ) : challenges.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-center px-5">
          <Target size={40} className="text-theme-surface2" strokeWidth={1} />
          <p className="text-body text-theme-muted">
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
        <div className="px-5 flex flex-col gap-3">
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
