import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ShieldCheck, Settings, Share2, Bell,
  ChevronLeft, ChevronRight, Flame, Heart, Eye, MessageCircle, ArrowLeft, Trash2, Pencil,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../store/auth'
import { shareProfileLink } from '../lib/share'
import { useUnreadNotifications } from '../hooks/useUnreadNotifications'
import type { MyStats, HistoryResponse, HistoryWorkoutPost } from '../api/types'
import client from '../api/client'
import LoadingScreen from '../components/LoadingScreen'
import UserAvatar from '../components/UserAvatar'
import { SkeletonCalendarGrid } from '../components/Skeleton'

import { getDaysInMonth, getFirstDayIndex, pad2 } from '../utils/calendar'


export default function ProfilePage() {
  const { t } = useTranslation('profile')
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()
  const unreadCount = useUnreadNotifications()

  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const queryClient = useQueryClient()
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [selectedPosts, setSelectedPosts] = useState<HistoryWorkoutPost[]>([])
  const [videoIdx, setVideoIdx] = useState(0)
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)


  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const videoRefs = useRef<(HTMLVideoElement | null)[]>([])
  const videoItemRefs = useRef<(HTMLDivElement | null)[]>([])
  const pendingScrollIdx = useRef<number>(0)

  const daysOfWeek = t('daysOfWeek', { returnObjects: true }) as string[]

  useEffect(() => {
    videoRefs.current = videoRefs.current.slice(0, selectedPosts.length)
    videoItemRefs.current = videoItemRefs.current.slice(0, selectedPosts.length)
    if (!selectedDate || selectedPosts.length === 0) return
    const container = scrollContainerRef.current
    if (!container) return

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const idx = videoItemRefs.current.indexOf(entry.target as HTMLDivElement)
          if (idx === -1) continue
          const video = videoRefs.current[idx]
          if (entry.isIntersecting) {
            setVideoIdx(idx)
            video?.play().catch(() => {})
          } else {
            video?.pause()
          }
        }
      },
      { root: container, threshold: 0.5 },
    )

    videoItemRefs.current.forEach((el) => { if (el) observer.observe(el) })

    const startIdx = pendingScrollIdx.current
    if (startIdx > 0) {
      pendingScrollIdx.current = 0
      requestAnimationFrame(() => {
        videoItemRefs.current[startIdx]?.scrollIntoView()
      })
    } else {
      videoRefs.current[0]?.play().catch(() => {})
    }

    return () => observer.disconnect()
  }, [selectedDate, selectedPosts])

  const { isLoading } = useQuery<MyStats>({
    queryKey: ['my-stats'],
    queryFn: async () => {
      const res = await client.get<{ data: MyStats }>('/users/me/stats')
      return res.data.data
    },
    enabled: !!user,
  })



  type MyPost = { id: number; cdn_url: string; thumbnail_url?: string | null; caption: string | null; created_at: string; like_count: number; view_count: number; comment_count: number }
  type MyPostsPage = { posts: MyPost[]; has_more: boolean; week_offset: number }

  const {
    data: myPostsData,
    isLoading: myPostsLoading,
  } = useQuery<MyPostsPage>({
    queryKey: ['my-posts'],
    queryFn: async () => {
      const res = await client.get<{ data: MyPostsPage }>('/videos/my-posts', {
        params: { all: true },
      })
      return res.data.data
    },
    enabled: !!user,
  })

  const myPosts = myPostsData?.posts ?? []

  const deleteMutation = useMutation({
    mutationFn: (postId: number) => client.delete(`/videos/posts/${postId}`),
    onSuccess: (_, postId) => {
      queryClient.setQueryData<MyPostsPage>(
        ['my-posts'],
        (old) => old ? { ...old, posts: old.posts.filter((p) => p.id !== postId) } : old
      )
      queryClient.invalidateQueries({ queryKey: ['history'] })
      queryClient.invalidateQueries({ queryKey: ['my-stats'] })
      queryClient.invalidateQueries({ queryKey: ['feed'] })
      setDeleteConfirmId(null)
    },
  })

  const clientTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone

  const { data: historyData, isLoading: historyLoading } = useQuery<HistoryResponse>({
    queryKey: ['history', year, month, clientTimezone],
    queryFn: async () => {
      const res = await client.get('/history', { params: { year, month, timezone: clientTimezone } })
      return res.data.data
    },
    enabled: !!user,
  })

  function prevMonth() {
    if (month === 1) { setYear((y) => y - 1); setMonth(12) }
    else setMonth((m) => m - 1)
    setSelectedDate(null)
  }

  function nextMonth() {
    const ty = now.getFullYear(), tm = now.getMonth() + 1
    if (year > ty || (year === ty && month >= tm)) return
    if (month === 12) { setYear((y) => y + 1); setMonth(1) }
    else setMonth((m) => m + 1)
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

  function openMyPosts(startIdx: number) {
    pendingScrollIdx.current = startIdx
    setSelectedDate('__my_posts__')
    setSelectedPosts(myPosts as HistoryWorkoutPost[])
    setVideoIdx(startIdx)
  }

  const totalDays = getDaysInMonth(year, month)
  const firstIdx = getFirstDayIndex(year, month)
  const workoutDays = historyData?.workout_days ?? {}
  const streak = historyData?.streak ?? 0
  const totalWorkoutDays = historyData?.total_days ?? 0
  const isCurrentMonth = year === now.getFullYear() && month === now.getMonth() + 1
  const todayNum = isCurrentMonth ? now.getDate() : -1
  const cells: Array<{ day: number | null; dateStr: string | null }> = []
  for (let i = 0; i < firstIdx; i++) cells.push({ day: null, dateStr: null })
  for (let d = 1; d <= totalDays; d++) cells.push({ day: d, dateStr: `${year}-${pad2(month)}-${pad2(d)}` })
  while (cells.length % 7 !== 0) cells.push({ day: null, dateStr: null })

  if (isLoading) return <LoadingScreen />

  return (
    <div className="flex flex-col h-[100dvh] overflow-y-auto bg-theme-page pb-nav-safe lg:max-w-2xl lg:mx-auto">

      <div className="flex items-center gap-3 px-4 pt-safe pt-5 pb-4">
        <UserAvatar
          username={user?.username ?? '?'}
          avatarUrl={user?.avatar_url}
          profileColor={user?.app_settings?.profile_color as string | null}
          size={36}
        />

        <div className="flex-1 flex items-center gap-2 min-w-0">
          <span className="text-body font-semibold text-theme-primary truncate">{user?.username}</span>
          {user?.is_admin && (
            <span className="flex-shrink-0 flex items-center gap-1 rounded-pill bg-accent/20 px-2 py-1 text-label font-semibold text-accent">
              <ShieldCheck size={9} />{t('adminBadge')}
            </span>
          )}
        </div>
        <button
          onClick={() => user && shareProfileLink(user.id, user.username, t)}
          className="flex-shrink-0 p-2 text-theme-muted hover:text-theme-primary transition-colors lg:hidden"
          aria-label={t('shareProfile')}
        >
          <Share2 size={16} strokeWidth={1.5} />
        </button>
        <button
          onClick={() => navigate('/notifications')}
          className="relative flex-shrink-0 p-2 text-theme-muted hover:text-theme-primary transition-colors lg:hidden"
          aria-label="알림"
        >
          <Bell size={16} strokeWidth={1.5} />
          {unreadCount > 0 && (
            <span className="absolute top-1 right-1 h-2 w-2 rounded-pill bg-danger" />
          )}
        </button>
        <button
          onClick={() => navigate('/settings')}
          className="flex-shrink-0 p-2 text-theme-muted hover:text-theme-primary transition-colors"
        >
          <Settings size={16} strokeWidth={1.5} />
        </button>
      </div>

      {user?.is_admin && (
        <div className="mx-4 mb-3">
          <button
            onClick={() => navigate('/admin')}
            className="w-full flex items-center justify-center gap-2 rounded-card bg-accent/10 border border-accent/30 px-4 py-3 text-body font-semibold text-accent hover:bg-accent/20 transition-colors"
          >
            <ShieldCheck size={15} />
            {t('goToAdmin')}
          </button>
        </div>
      )}

      <div className="mx-4 mb-4 rounded-card bg-theme-surface px-4 py-3">
        <div className="flex items-center gap-4 py-1">
          <div className="flex items-center gap-2 text-accent-text">
            <Flame size={20} strokeWidth={2} />
            <span className="text-display leading-none">{streak}</span>
            <span className="text-body font-medium text-theme-primary">{t('streakDays')}</span>
          </div>
          <div className="h-4 w-px bg-theme-border" />
          <div className="text-body text-theme-muted">
            {t('thisMonthWorkout')} <span className="font-semibold text-theme-primary">{t('workoutDays', { count: totalWorkoutDays })}</span>
          </div>
        </div>
      </div>

      <div className="mx-4 mb-4">
        <div className="flex items-center justify-between mb-3">
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

        <div className="grid grid-cols-7 mb-1">
          {daysOfWeek.map((d) => (
            <div key={d} className="text-center text-label font-medium text-theme-muted py-1">{d}</div>
          ))}
        </div>

        {historyLoading ? (
          <SkeletonCalendarGrid />
        ) : (
          <div className="grid grid-cols-7 gap-1">
            {cells.map((cell, idx) => {
 if (cell.day === null) return <div key={`empty-${idx}`} className="aspect-square" />
              const posts = cell.dateStr ? (workoutDays[cell.dateStr] ?? []) : []
              const hasWorkout = posts.length > 0
              const isToday = cell.day === todayNum

              if (hasWorkout) {
                return (
                  <button
                    key={cell.dateStr}
                    onClick={() => openDay(cell.dateStr!, posts)}
                    className={`aspect-square relative overflow-hidden rounded-card active:scale-95 transition-transform ${isToday ? 'ring-2 ring-accent ring-offset-1 ring-offset-[--bg-page]' : ''}`}
                  >
                    {posts[0].thumbnail_url ? (
                      <img
                        src={posts[0].thumbnail_url}
                        alt=""
                        className="absolute inset-0 h-full w-full object-cover"
                        loading="lazy"
                        decoding="async"
                      />
                    ) : (
                      <video
                        src={posts[0].cdn_url}
                        className="absolute inset-0 h-full w-full object-cover"
                        muted playsInline preload="none"
                      />
                    )}
                    <div className="absolute inset-0 bg-black/30" />
                    <span className="absolute inset-x-0 bottom-0 flex items-center justify-center pb-2 text-label font-bold text-white leading-none">
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
                  className={`aspect-square flex items-center justify-center rounded-card text-body font-medium ${isToday ? 'ring-1 ring-accent text-accent' : 'text-theme-muted'}`}
                >
                  {cell.day}
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="mb-6">
        <div className="flex items-center justify-between mb-3 px-4">
          <p className="text-body font-semibold text-theme-primary">{t('myVideos')}</p>
          {myPosts.length > 0 && (
            <span className="text-label text-theme-muted">{t('videoCount', { count: myPosts.length })}</span>
          )}
        </div>

        {myPostsLoading ? (
          <div className="flex h-24 items-center justify-center text-body text-theme-muted">
            {t('videosLoading')}
          </div>
        ) : myPosts.length === 0 ? (
          <div className="mx-4 flex h-24 items-center justify-center rounded-card bg-theme-surface text-body text-theme-muted">
            {t('noVideos')}
          </div>
        ) : (
          <div
            className="flex gap-2 overflow-x-auto px-4 pb-1"
            style={{ scrollbarWidth: 'none' }}
          >
            {myPosts.map((post, idx) => {
              const isPending = Date.now() - new Date(post.created_at).getTime() < 24 * 60 * 60 * 1000
              return (
                <div
                  key={post.id}
                  className="relative flex-shrink-0 overflow-hidden rounded-card bg-theme-surface2 group cursor-pointer active:scale-95 transition-transform"
                  style={{ width: '28vw', aspectRatio: '9/16' }}
                  onClick={() => openMyPosts(idx)}
                >
                  {post.thumbnail_url ? (
                    <img
                      src={post.thumbnail_url}
                      className="absolute inset-0 h-full w-full object-cover"
                      loading="lazy"
                      alt=""
                    />
                  ) : (
                    <video
                      src={post.cdn_url}
                      className="absolute inset-0 h-full w-full object-cover"
                      muted
                      playsInline
                      preload="none"
                    />
                  )}
                  <div className="absolute inset-0 bg-black/30" />
                  {isPending && (
                    <div className="absolute top-1.5 left-1.5 h-2 w-2 rounded-pill bg-warning" />
                  )}
                  <div className="absolute top-1.5 right-1.5 flex gap-1">
                    <button
                      onClick={(e) => { e.stopPropagation(); navigate(`/posts/${post.id}/edit`) }}
                      className="flex h-6 w-6 items-center justify-center rounded-pill bg-black/50 text-white/80"
                      aria-label={t('editAriaLabel')}
                    >
                      <Pencil size={11} strokeWidth={2} />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); setDeleteConfirmId(post.id) }}
                      className="flex h-6 w-6 items-center justify-center rounded-pill bg-black/50 text-white/80"
                      aria-label={t('deleteAriaLabel')}
                    >
                      <Trash2 size={11} strokeWidth={2} />
                    </button>
                  </div>
                  <div className="absolute bottom-1.5 right-1 flex flex-col items-end gap-1 text-white/90">
                    <div className="flex items-center gap-1">
                      <Heart size={9} strokeWidth={2} />
                      <span className="text-label font-medium">{post.like_count}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <MessageCircle size={9} strokeWidth={2} />
                      <span className="text-label font-medium">{post.comment_count}</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Eye size={9} strokeWidth={2} />
                      <span className="text-label font-medium">{post.view_count}</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="mx-4 mb-6 flex items-center justify-center">
        <span className="text-label text-theme-muted">v{__APP_VERSION__}</span>
      </div>

      {deleteConfirmId !== null && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
          onClick={() => setDeleteConfirmId(null)}
        >
          <div
            className="w-full max-w-lg rounded-card bg-theme-surface px-6 pt-5 pb-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="text-title text-theme-primary mb-1">{t('deleteConfirmTitle')}</p>
            <p className="text-body text-theme-muted mb-5">{t('deleteConfirmBody')}</p>
            <div className="flex gap-3">
              <button
                onClick={() => setDeleteConfirmId(null)}
                className="flex-1 rounded-card bg-theme-surface2 py-3 text-body text-theme-muted"
              >
                {t('common:cancel')}
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteConfirmId)}
                disabled={deleteMutation.isPending}
                className="flex-1 rounded-card bg-danger py-3 text-body font-semibold text-white disabled:opacity-60"
              >
                {deleteMutation.isPending ? t('deleting') : t('common:delete')}
              </button>
            </div>
          </div>
        </div>
      )}

      {selectedDate && selectedPosts.length > 0 && (
        <div className="fixed inset-0 z-[70] bg-black">
          <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-4 pt-safe pt-4 pb-3 bg-gradient-to-b from-black/60 to-transparent pointer-events-none">
            <button
              onClick={closeModal}
              className="flex h-9 w-9 items-center justify-center rounded-pill bg-black/30 pointer-events-auto"
            >
              <ArrowLeft size={20} strokeWidth={2} color="white" />
            </button>
            <span className="text-body font-semibold text-white">
              {selectedDate === '__my_posts__' ? t('myPostsLabel') : selectedDate.replace(/-/g, '.')}
            </span>
            {selectedPosts.length > 1 ? (
              <span className="text-label text-white/70">{videoIdx + 1} / {selectedPosts.length}</span>
            ) : (
              <div className="w-9" />
            )}
          </div>

          <div
            ref={scrollContainerRef}
            className="h-full w-full overflow-y-scroll scroll-momentum"
            style={{ scrollSnapType: 'y mandatory', scrollbarWidth: 'none' }}
          >
            {selectedPosts.map((post, i) => (
              <div
                key={post.cdn_url}
                ref={(el) => { videoItemRefs.current[i] = el }}
                className="relative h-full w-full flex-shrink-0"
                style={{ scrollSnapAlign: 'start' }}
              >
                <video
                  ref={(el) => { videoRefs.current[i] = el }}
                  src={post.cdn_url}
                  className="h-full w-full object-contain"
                  playsInline
                  loop
                />
                <div className="absolute top-safe top-16 right-4 z-10 flex flex-col items-end gap-2">
                  <div className="flex items-center gap-2 text-white/90 drop-shadow">
                    <Heart size={14} strokeWidth={1.5} />
                    <span className="text-body font-medium">{post.like_count}</span>
                  </div>
                  <div className="flex items-center gap-2 text-white/90 drop-shadow">
                    <Eye size={14} strokeWidth={1.5} />
                    <span className="text-body font-medium">{post.view_count}</span>
                  </div>
                </div>
                {post.caption && (
                  <div className="absolute bottom-0 left-0 right-0 z-10 px-4 pb-6 pt-8 bg-gradient-to-t from-black/70 to-transparent">
                    <p className="text-body text-white/90 line-clamp-2">{post.caption}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
