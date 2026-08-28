import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import type { FeedResponse } from '../api/types'
import VideoCard from '../components/VideoCard'
import LoginPromptSheet from '../components/LoginPromptSheet'
import CommentSheet from '../components/CommentSheet'
import LoadingScreen from '../components/LoadingScreen'
import LogoMark from '../components/LogoMark'
import { useUiStore } from '../store/ui'

async function fetchFeed(cursor?: number): Promise<FeedResponse> {
  const params = cursor ? { cursor } : {}
  const res = await client.get<{ data: FeedResponse }>('/feed', { params })
  return res.data.data
}

export default function FeedPage() {
  const { t } = useTranslation('feed')
  const [activeIndex, setActiveIndex] = useState(0)
  const [showLogin, setShowLogin] = useState(false)
  const [isMuted, setIsMuted] = useState(true)
  const [commentPostId, setCommentPostId] = useState<number | null>(null)
  const setCommentOpen = useUiStore((s) => s.setCommentOpen)
  // 시트 열린 채 라우트 이탈(뒤로가기 등) 시 전역 commentOpen 잔류 → BottomNav 영구 숨김 방지
  useEffect(() => () => setCommentOpen(false), [setCommentOpen])
  const containerRef = useRef<HTMLDivElement>(null)
  const touchStartY = useRef(0)

  const { data, fetchNextPage, hasNextPage, isLoading } = useInfiniteQuery({
    queryKey: ['feed'],
    queryFn: ({ pageParam }) => fetchFeed(pageParam as number | undefined),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })

  const posts = useMemo(() => data?.pages.flatMap((p) => p.posts) ?? [], [data])

  const goTo = useCallback(
    (idx: number) => {
      if (idx < 0 || idx >= posts.length) return
      setActiveIndex(idx)
      if (idx >= posts.length - 2 && hasNextPage) {
        fetchNextPage().catch(() => undefined)
      }
    },
    [posts.length, hasNextPage, fetchNextPage],
  )

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartY.current = e.touches[0].clientY
  }, [])

  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      const delta = touchStartY.current - e.changedTouches[0].clientY
      if (Math.abs(delta) < 30) return
      if (delta > 0) goTo(activeIndex + 1)
      else goTo(activeIndex - 1)
    },
    [activeIndex, goTo],
  )

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const preventScroll = (e: TouchEvent) => e.preventDefault()
    el.addEventListener('touchmove', preventScroll, { passive: false })
    return () => el.removeEventListener('touchmove', preventScroll)
  }, [])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault()
      if (e.deltaY > 30) goTo(activeIndex + 1)
      else if (e.deltaY < -30) goTo(activeIndex - 1)
    }
    el.addEventListener('wheel', handleWheel, { passive: false })
    return () => el.removeEventListener('wheel', handleWheel)
  }, [activeIndex, goTo])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.key === 'ArrowDown') { e.preventDefault(); goTo(activeIndex + 1) }
      else if (e.key === 'ArrowUp') { e.preventDefault(); goTo(activeIndex - 1) }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activeIndex, goTo])

  if (isLoading) return <LoadingScreen />

  if (posts.length === 0) {
    return (
      <div className="flex h-[100dvh] flex-col items-center justify-center gap-4 bg-theme-page px-6 pb-nav-safe text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-card bg-theme-surface text-accent">
          <LogoMark aria-hidden="true" size={42} />
        </div>
        <div>
          <p className="font-semibold text-theme-primary">{t('emptyTitle')}</p>
          <p className="mt-1 text-body text-theme-muted">
            {t('emptySubtitle')}
          </p>
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="h-[100dvh] bg-black flex justify-center">
        <div
          ref={containerRef}
          className="h-[100dvh] overflow-hidden w-full max-w-[430px]"
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
        >
          <div
            style={{
              transform: `translateY(calc(-${activeIndex} * 100dvh))`,
              transition: 'transform 0.32s cubic-bezier(0.4, 0, 0.2, 1)',
              willChange: 'transform',
            }}
          >
            {posts.map((post, idx) => (
              <div key={post.id} style={{ height: '100dvh' }}>
                {Math.abs(idx - activeIndex) <= 1 ? (
                  <VideoCard
                    post={post}
                    onLoginRequired={() => setShowLogin(true)}
                    onCommentClick={() => { setCommentPostId(post.id); setCommentOpen(true) }}
                    isMuted={isMuted}
                    onToggleMute={() => setIsMuted((m) => !m)}
                  />
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </div>
      {showLogin && <LoginPromptSheet onClose={() => setShowLogin(false)} />}
      <CommentSheet
        postId={commentPostId ?? 0}
        open={commentPostId !== null}
        onClose={() => { setCommentPostId(null); setCommentOpen(false) }}
        onLoginRequired={() => setShowLogin(true)}
      />
    </>
  )
}
