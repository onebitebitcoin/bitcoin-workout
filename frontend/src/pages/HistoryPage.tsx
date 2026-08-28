import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Flame, Heart, Eye, ArrowLeft, Award, Share2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import type { HistoryResponse, HistoryWorkoutPost } from '../api/types'

import { getDaysInMonth, getFirstDayIndex, pad2 } from '../utils/calendar'

export default function HistoryPage() {
  const { t } = useTranslation('profile')
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [selectedPosts, setSelectedPosts] = useState<HistoryWorkoutPost[]>([])
  const [videoIdx, setVideoIdx] = useState(0)

  const daysOfWeek = t('daysOfWeek', { returnObjects: true }) as string[]

  const clientTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone

  const { data, isLoading } = useQuery<HistoryResponse>({
    queryKey: ['history', year, month, clientTimezone],
    queryFn: async () => {
      const res = await client.get('/history', { params: { year, month, timezone: clientTimezone } })
      return res.data.data
    },
  })

  function prevMonth() {
    if (month === 1) {
      setYear((y) => y - 1)
      setMonth(12)
    } else {
      setMonth((m) => m - 1)
    }
    setSelectedDate(null)
  }

  function nextMonth() {
    const todayYear = now.getFullYear()
    const todayMonth = now.getMonth() + 1
    if (year > todayYear || (year === todayYear && month >= todayMonth)) return
    if (month === 12) {
      setYear((y) => y + 1)
      setMonth(1)
    } else {
      setMonth((m) => m + 1)
    }
    setSelectedDate(null)
  }

  function openDay(dateStr: string, posts: HistoryWorkoutPost[]) {
    setSelectedDate(dateStr)
    setSelectedPosts(posts)
    setVideoIdx(0)
  }

  function closeModal() {
    setSelectedDate(null)
    setSelectedPosts([])
    setVideoIdx(0)
  }

  const totalDays = getDaysInMonth(year, month)
  const firstIdx = getFirstDayIndex(year, month)
  const workoutDays = data?.workout_days ?? {}
  const streak = data?.streak ?? 0
  // 5단계인데 색은 3종뿐이라 100일과 30일이, 14일과 7일이 서로 같은 색이었다.
  // 단계는 이미 문구가 말하므로 색은 하나로 둔다.
  const streakBadge =
    streak >= 100 ? 'badge100'
    : streak >= 30 ? 'badge30'
    : streak >= 14 ? 'badge14'
    : streak >= 7 ? 'badge7'
    : streak >= 3 ? 'badge3'
    : null
  const totalWorkoutDays = data?.total_days ?? 0

  const isCurrentMonth =
    year === now.getFullYear() && month === now.getMonth() + 1
  const todayNum = isCurrentMonth ? now.getDate() : -1

  const cells: Array<{ day: number | null; dateStr: string | null }> = []
  for (let i = 0; i < firstIdx; i++) cells.push({ day: null, dateStr: null })
  for (let d = 1; d <= totalDays; d++) {
    cells.push({ day: d, dateStr: `${year}-${pad2(month)}-${pad2(d)}` })
  }
  while (cells.length % 7 !== 0) cells.push({ day: null, dateStr: null })

  return (
    <div className="flex flex-col h-[100dvh] bg-theme-page overflow-y-auto pb-nav-safe lg:max-w-2xl lg:mx-auto">
      <div className="px-4 pt-6 pb-3">
        <h1 className="text-display text-theme-primary">{t('historyTitle')}</h1>
      </div>

      <div className="mx-4 mb-4 rounded-card bg-theme-surface px-4 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 text-accent-text">
              <Flame size={24} strokeWidth={2} />
              <span className="text-display leading-none">{streak}</span>
            </div>
            <div>
              <p className="text-body font-semibold text-theme-primary">{t('streakDays')}</p>
              {streak === 0 && (
                <p className="text-label text-theme-muted">{t('streakStart')}</p>
              )}
            </div>
          </div>
          <div className="text-right">
            {streakBadge && (
              <span className="inline-flex items-center gap-1 rounded-pill bg-accent/15 px-3 py-1 text-label font-semibold text-accent-text">
                <Award size={14} strokeWidth={1.75} /> {t(streakBadge)}
              </span>
            )}
          </div>
        </div>
        <div className="mt-3 h-px bg-theme-border" />
        <div className="mt-3 flex items-center justify-between">
          <p className="text-body text-theme-muted">
            {t('thisMonthWorkout')}{' '}
            <span className="font-semibold text-theme-primary">{t('workoutDays', { count: totalWorkoutDays })}</span>
          </p>
          <button
            onClick={() => {
              const text = t('shareText', { days: totalWorkoutDays, streak })
              if (typeof navigator !== 'undefined' && 'share' in navigator) {
                navigator.share({ title: t('shareTitle'), text, url: window.location.origin }).catch(() => undefined)
              } else {
                window.navigator.clipboard?.writeText(text).then(() => alert(t('clipboardCopied'))).catch(() => undefined)
              }
            }}
            className="flex items-center gap-1 rounded-card bg-accent/10 px-3 py-2 text-label font-medium text-accent hover:bg-accent/20 transition-colors"
          >
            <Share2 size={12} />
            {t('shareButton')}
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between px-4 mb-3">
        <button
          onClick={prevMonth}
          className="flex h-8 w-8 items-center justify-center rounded-pill hover:bg-theme-surface transition-colors"
        >
          <ChevronLeft size={20} strokeWidth={2} className="text-theme-primary" />
        </button>
        <span className="text-title font-semibold text-theme-primary">
          {t('calendarYear', { year, month })}
        </span>
        <button
          onClick={nextMonth}
          disabled={isCurrentMonth}
          className="flex h-8 w-8 items-center justify-center rounded-pill hover:bg-theme-surface transition-colors disabled:opacity-30"
        >
          <ChevronRight size={20} strokeWidth={2} className="text-theme-primary" />
        </button>
      </div>

      <div className="px-4">
        {isLoading ? (
          <div className="flex h-48 items-center justify-center text-theme-muted text-body">
            {t('historyLoading')}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-7 mb-1">
              {daysOfWeek.map((d) => (
                <div
                  key={d}
                  className="text-center text-label font-medium text-theme-muted py-1"
                >
                  {d}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1">
            {cells.map((cell, idx) => {
              if (cell.day === null) {
 return <div key={`empty-${idx}`} className="aspect-square" />
              }
              const hasWorkout = cell.dateStr !== null && workoutDays[cell.dateStr]?.length > 0
              const isToday = cell.day === todayNum
              const posts = cell.dateStr ? (workoutDays[cell.dateStr] ?? []) : []

              if (hasWorkout) {
                return (
                  <button
                    key={cell.dateStr}
                    onClick={() => openDay(cell.dateStr!, posts)}
                    className={`
                      aspect-square relative overflow-hidden rounded-card
                      active:scale-95 transition-transform
                      ${isToday ? 'ring-2 ring-accent ring-offset-1 ring-offset-[--bg-page]' : ''}
                    `}
                  >
                    {posts[0].thumbnail_url ? (
                      <img
                        src={posts[0].thumbnail_url}
                        className="absolute inset-0 h-full w-full object-cover"
                        loading="lazy"
                        alt=""
                      />
                    ) : (
                      <video
                        src={posts[0].cdn_url}
                        className="absolute inset-0 h-full w-full object-cover"
                        muted
                        playsInline
                        preload="none"
                      />
                    )}
                    <div className="absolute inset-0 bg-black/30" />
                    <span className="absolute inset-0 flex items-center justify-center text-label font-bold text-white leading-none">
                      {cell.day}
                    </span>
                    {posts.length > 1 && (
                      <div className="absolute top-1 right-1 h-1.5 w-1.5 rounded-pill bg-accent" />
                    )}
                  </button>
                )
              }

              return (
                <div
                  key={cell.dateStr}
                  className={`
                    aspect-square flex items-center justify-center rounded-card
                    text-body font-medium
                    ${isToday ? 'ring-1 ring-accent text-accent' : 'text-theme-muted'}
                  `}
                >
                  {cell.day}
                </div>
              )
            })}
            </div>
          </>
        )}
      </div>

      {selectedDate && selectedPosts.length > 0 && (
        <div className="fixed inset-0 z-[70] bg-black flex flex-col">
          <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-4 pt-safe pt-4 pb-3 bg-gradient-to-b from-black/60 to-transparent">
            <button
              onClick={closeModal}
              className="flex h-9 w-9 items-center justify-center rounded-pill bg-black/30"
            >
              <ArrowLeft size={20} strokeWidth={2} color="white" />
            </button>
            <span className="text-body font-semibold text-white">
              {selectedDate.replace(/-/g, '.')}
            </span>
            {selectedPosts.length > 1 ? (
              <span className="text-label text-white/70">
                {videoIdx + 1} / {selectedPosts.length}
              </span>
            ) : (
              <div className="w-9" />
            )}
          </div>

          <video
            key={selectedPosts[videoIdx].cdn_url}
            src={selectedPosts[videoIdx].cdn_url}
            className="h-full w-full object-contain"
            autoPlay
            playsInline
            controls
          />

          <div className="absolute bottom-0 left-0 right-0 z-10 px-4 pb-6 pt-16 bg-gradient-to-t from-black/70 to-transparent">
            <div className="flex items-center gap-4 mb-2">
              <div className="flex items-center gap-2 text-white/80">
                <Heart size={14} strokeWidth={1.5} />
                <span className="text-body">{selectedPosts[videoIdx].like_count}</span>
              </div>
              <div className="flex items-center gap-2 text-white/80">
                <Eye size={14} strokeWidth={1.5} />
                <span className="text-body">{selectedPosts[videoIdx].view_count}</span>
              </div>
            </div>
            {selectedPosts[videoIdx].caption && (
              <p className="text-body text-white/90 line-clamp-2 mb-3">
                {selectedPosts[videoIdx].caption}
              </p>
            )}
            {selectedPosts.length > 1 && (
              <div className="flex gap-2">
                {selectedPosts.map((_, i) => (
                  <button
                    key={i}
                    onClick={() => setVideoIdx(i)}
                    className={`h-1 flex-1 rounded-pill transition-all ${
                      i === videoIdx ? 'bg-accent' : 'bg-white/30'
                    }`}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
