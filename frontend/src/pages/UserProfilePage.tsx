import { useState, useRef, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Trophy, ArrowLeft, Target, Heart, Eye, MessageCircle, Share2, UserPlus, UserCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import type { UserProfile, PublicPost } from '../api/types'
import UserAvatar from '../components/UserAvatar'
import { shareProfileLink } from '../lib/share'
import { useAuthStore } from '../store/auth'

type Tab = 'videos' | 'challenges' | 'titles'

export default function UserProfilePage() {
  const { t } = useTranslation('profile')
  const { userId } = useParams<{ userId: string }>()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<Tab>('videos')
  const [viewerIdx, setViewerIdx] = useState<number | null>(null)
  const [activeVideoIdx, setActiveVideoIdx] = useState(0)
  const videoRefs = useRef<(HTMLVideoElement | null)[]>([])
  const videoItemRefs = useRef<(HTMLDivElement | null)[]>([])
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  const qc = useQueryClient()
  const currentUser = useAuthStore((s) => s.user)

  const { data, isLoading, isError } = useQuery<UserProfile>({
    queryKey: ['user-profile', userId],
    queryFn: async () => {
      const res = await client.get<{ data: UserProfile }>(`/users/${userId}/profile`)
      return res.data.data
    },
    enabled: !!userId,
  })

  const followMutation = useMutation({
    mutationFn: async (follow: boolean) => {
      if (follow) await client.post(`/users/${userId}/follow`)
      else await client.delete(`/users/${userId}/follow`)
      return follow
    },
    onMutate: async (follow: boolean) => {
      await qc.cancelQueries({ queryKey: ['user-profile', userId] })
      const prev = qc.getQueryData<UserProfile>(['user-profile', userId])
      if (prev) {
        qc.setQueryData<UserProfile>(['user-profile', userId], {
          ...prev,
          is_following: follow,
          follower_count: prev.follower_count + (follow ? 1 : -1),
        })
      }
      return { prev }
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(['user-profile', userId], ctx.prev)
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['user-profile', userId] })
    },
  })

  const posts: PublicPost[] = data?.posts ?? []

  useEffect(() => {
    if (viewerIdx === null) return
    videoRefs.current = videoRefs.current.slice(0, posts.length)
    videoItemRefs.current = videoItemRefs.current.slice(0, posts.length)

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const idx = videoItemRefs.current.indexOf(entry.target as HTMLDivElement)
          if (idx === -1) return
          const video = videoRefs.current[idx]
          if (entry.isIntersecting) {
            setActiveVideoIdx(idx)
            video?.play().catch(() => {})
          } else {
            video?.pause()
          }
        })
      },
      { threshold: 0.5 },
    )
    videoItemRefs.current.forEach((el) => { if (el) observer.observe(el) })
    return () => observer.disconnect()
  }, [viewerIdx, posts.length])

  const openViewer = useCallback((idx: number) => {
    setViewerIdx(idx)
    setActiveVideoIdx(idx)
    setTimeout(() => {
      videoItemRefs.current[idx]?.scrollIntoView()
      videoRefs.current[0]?.play().catch(() => {})
    }, 50)
  }, [])

  const closeViewer = useCallback(() => {
    videoRefs.current.forEach((v) => v?.pause())
    setViewerIdx(null)
  }, [])

  if (isLoading) return (
    <div className="flex flex-col h-[100dvh] bg-theme-page pb-nav-safe lg:max-w-2xl lg:mx-auto">
      <div className="flex items-center gap-3 px-4 pt-5 pb-4">
        <div className="w-5 h-5 rounded bg-theme-surface2 flex-shrink-0" />
        <div className="w-10 h-10 rounded-pill bg-theme-surface2 flex-shrink-0" />
        <div className="flex-1 flex flex-col gap-2">
          <div className="h-3 w-24 rounded bg-theme-surface2" />
          <div className="h-2.5 w-16 rounded bg-theme-surface2" />
        </div>
      </div>
      <div className="flex gap-2 px-4 mb-4">
        {[1,2,3].map(i => <div key={i} className="flex-1 h-9 rounded-card bg-theme-surface2" />)}
      </div>
      <div className="grid grid-cols-3 gap-px mx-px">
        {Array.from({length: 9}).map((_, i) => (
          <div key={i} className="aspect-[9/16] bg-theme-surface2" />
        ))}
      </div>
    </div>
  )

  if (isError || !data) {
    return (
      <div className="flex h-[100dvh] flex-col items-center justify-center gap-2 bg-theme-page lg:max-w-2xl lg:mx-auto">
        <p className="text-body text-theme-muted">{t('userNotFound')}</p>
      </div>
    )
  }

  const { user, post_count, titles, active_challenges } = data

  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: 'videos', label: t('tabVideos'), count: post_count },
    { key: 'challenges', label: t('tabChallenges'), count: active_challenges.length },
    { key: 'titles', label: t('tabTitles'), count: titles.length },
  ]

  return (
    <div className="flex flex-col h-[100dvh] overflow-y-auto bg-theme-page pb-nav-safe lg:max-w-2xl lg:mx-auto">
      <div className="flex items-center gap-3 px-4 pt-5 pb-4">
        <button onClick={() => navigate(-1)} className="text-theme-muted flex-shrink-0">
          <ArrowLeft size={20} />
        </button>
        <UserAvatar username={user.username} avatarUrl={user.avatar_url} size={40} />
        <div className="flex-1 min-w-0">
          <p className="text-body font-semibold text-theme-primary leading-tight">@{user.username}</p>
          <div className="flex items-center gap-3 text-label text-theme-muted mt-1">
            <button onClick={() => navigate(`/users/${user.id}/followers`)} className="hover:text-theme-primary">
              <span className="font-semibold text-theme-primary">{data.follower_count}</span> {t('followers')}
            </button>
            <button onClick={() => navigate(`/users/${user.id}/following`)} className="hover:text-theme-primary">
              <span className="font-semibold text-theme-primary">{data.following_count}</span> {t('following')}
            </button>
          </div>
        </div>
        {currentUser && currentUser.id !== user.id && (
          <button
            onClick={() => followMutation.mutate(!data.is_following)}
            disabled={followMutation.isPending}
            className={`flex-shrink-0 flex items-center gap-1 rounded-pill px-3 py-2 text-label font-semibold transition-colors disabled:opacity-60 ${
              data.is_following ? 'bg-theme-surface2 text-theme-muted' : 'bg-accent text-accent-fg'
            }`}
          >
            {data.is_following ? <><UserCheck size={14} /> {t('followingBtn')}</> : <><UserPlus size={14} /> {t('followBtn')}</>}
          </button>
        )}
        <button
          onClick={() => shareProfileLink(user.id, user.username, t)}
          className="flex-shrink-0 p-2 text-theme-muted hover:text-theme-primary transition-colors"
          aria-label={t('shareProfile')}
        >
          <Share2 size={18} strokeWidth={1.5} />
        </button>
      </div>

      <div className="flex gap-2 px-4 mb-4">
        {tabs.map(({ key, label, count }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex-1 rounded-card py-2 text-label font-medium transition-colors ${
              activeTab === key
                ? 'bg-accent text-accent-fg'
                : 'bg-theme-surface text-theme-muted'
            }`}
          >
            {label}
            <span className="ml-1 opacity-70">{count}</span>
          </button>
        ))}
      </div>

      {activeTab === 'videos' && (
        posts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-2">
            <p className="text-body text-theme-muted">{t('noUserVideos')}</p>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-px mx-px">
            {posts.map((post, idx) => (
              <div
                key={post.id}
                className="relative aspect-[9/16] overflow-hidden bg-theme-surface cursor-pointer active:opacity-80"
                onClick={() => openViewer(idx)}
              >
                {post.thumbnail_url ? (
                  <img
                    src={post.thumbnail_url}
                    alt=""
                    className="h-full w-full object-cover"
                    loading="lazy"
                    decoding="async"
                  />
                ) : (
                  <video
                    src={post.cdn_url}
                    className="h-full w-full object-cover"
                    muted
                    playsInline
                    preload="none"
                  />
                )}
                <div className="absolute inset-0 bg-black/30" />
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
            ))}
          </div>
        )
      )}

      {activeTab === 'challenges' && (
        <div className="px-4">
          {active_challenges.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-2">
              <Target size={36} className="text-theme-surface2" strokeWidth={1.5} />
              <p className="text-body text-theme-muted">{t('noActiveChallenges')}</p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {active_challenges.map((c) => {
                const progress = Math.min(
                  100,
                  Math.round((c.upload_count / c.condition_value) * 100),
                )
                return (
                  <div
                    key={c.challenge_id}
                    className="rounded-card bg-theme-surface px-4 py-3 cursor-pointer active:opacity-80"
                    onClick={() => navigate(`/challenges/${c.challenge_id}`)}
                  >
                    <div className="flex justify-between items-center text-body mb-2">
                      <span className="font-medium text-theme-primary truncate flex-1 mr-2">
                        {c.title}
                      </span>
                      <span className="text-label text-theme-muted flex-shrink-0">
                        {t('challengeCount', { upload: c.upload_count, total: c.condition_value })}
                      </span>
                    </div>
                    <div className="h-1.5 w-full rounded-pill bg-theme-surface2">
                      <div
                        className="h-1.5 rounded-pill bg-accent transition-all"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                    <p className="text-label text-theme-muted mt-2">{t('challengeProgress', { progress })}</p>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {activeTab === 'titles' && (
        <div className="px-4">
          {titles.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-2">
              <Trophy size={36} className="text-theme-surface2" strokeWidth={1.5} />
              <p className="text-body text-theme-muted">{t('noTitles')}</p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {titles.map((titleItem, i) => (
                <div
                  key={i}
                  className="rounded-card bg-theme-surface px-4 py-3 flex items-center gap-3"
                >
                  <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-pill bg-accent/15">
                    <Trophy size={16} className="text-accent" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-body font-semibold text-accent">{titleItem.title}</p>
                    <p className="text-label text-theme-muted truncate">{titleItem.challenge_title}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {viewerIdx !== null && posts.length > 0 && (
        <div className="fixed inset-0 z-[70] bg-black">
          <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-4 pt-safe pt-4 pb-3 bg-gradient-to-b from-black/60 to-transparent pointer-events-none">
            <button
              onClick={closeViewer}
              className="flex h-9 w-9 items-center justify-center rounded-pill bg-black/30 pointer-events-auto"
            >
              <ArrowLeft size={20} strokeWidth={2} color="white" />
            </button>
            <span className="text-body font-semibold text-white">@{user.username}</span>
            {posts.length > 1 ? (
              <span className="text-label text-white/70">{activeVideoIdx + 1} / {posts.length}</span>
            ) : (
              <div className="w-9" />
            )}
          </div>

          <div
            ref={scrollContainerRef}
            className="h-full w-full overflow-y-scroll scroll-momentum"
            style={{ scrollSnapType: 'y mandatory', scrollbarWidth: 'none' }}
          >
            {posts.map((post, i) => (
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
                    <MessageCircle size={14} strokeWidth={1.5} />
                    <span className="text-body font-medium">{post.comment_count}</span>
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
