import { useRef, useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Heart, MessageCircle, Volume2, VolumeX, Pause, Play, Share2, Rewind, FastForward } from 'lucide-react'
import toast from 'react-hot-toast'
import { clsx } from 'clsx'
import { useQueryClient, type InfiniteData } from '@tanstack/react-query'
import type { Post, FeedResponse } from '../api/types'
import client from '../api/client'
import { useAuthStore } from '../store/auth'

// 더블탭 시크: 왼쪽 -3초 / 오른쪽 +3초 (쇼츠 표준)
const SEEK_SECONDS = 3
const DOUBLE_TAP_MS = 280

interface VideoCardProps {
  post: Post
  onLoginRequired: () => void
  onCommentClick: () => void
  isMuted: boolean
  onToggleMute: () => void
}

export default function VideoCard({ post, onLoginRequired, onCommentClick, isMuted, onToggleMute }: VideoCardProps) {
  const { t } = useTranslation('feed')
  const navigate = useNavigate()
  const containerRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()
  const [liked, setLiked] = useState(post.is_liked ?? false)
  const [likeCount, setLikeCount] = useState(post.like_count)
  const [likeAnim, setLikeAnim] = useState<'burst' | 'shrink' | null>(null)
  const viewSent = useRef(false)

  // Sync local state when feed data is refetched (SPA navigation stale cache fix)
  useEffect(() => { setLiked(post.is_liked ?? false) }, [post.is_liked])
  useEffect(() => { setLikeCount(post.like_count) }, [post.like_count])
  const [isPaused, setIsPaused] = useState(false)
  const [flashIcon, setFlashIcon] = useState<'play' | 'pause' | null>(null)
  const [seekFlash, setSeekFlash] = useState<'left' | 'right' | null>(null)
  const [progress, setProgress] = useState(0)
  const [isScrubbing, setIsScrubbing] = useState(false)
  const [fitContain, setFitContain] = useState(false)
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const seekFlashTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const singleTapTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastTap = useRef<{ time: number; side: 'left' | 'right' } | null>(null)
  const isDragging = useRef(false)
  const progressBarRef = useRef<HTMLDivElement>(null)
  const isLikePending = useRef(false)
  const commentCount = post.comment_count ?? 0

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        const video = videoRef.current
        if (!video) return
        if (entry.isIntersecting) {
          setIsPaused(false)
          video.play().catch(() => undefined)
          if (!viewSent.current && token) {
            viewSent.current = true
            client.post(`/feed/${post.id}/view`).catch(() => undefined)
          }
        } else {
          video.pause()
          video.currentTime = 0
        }
      },
      { threshold: 0.5 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [post.id, token])

  useEffect(() => {
    if (videoRef.current) videoRef.current.muted = isMuted
  }, [isMuted])

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    const onTimeUpdate = () => {
      if (video.duration) setProgress((video.currentTime / video.duration) * 100)
    }
    const onMeta = () => {
      // 9:16(0.5625)보다 눈에 띄게 넓은 비율(1:1 이미지 합성, 4:3 사진, 가로 영상)은
      // cover로 채우면 좌우가 크게 잘려 확대돼 보이므로 contain으로 전체 표시
      setFitContain(video.videoWidth / video.videoHeight > 0.65)
    }
    video.addEventListener('timeupdate', onTimeUpdate)
    video.addEventListener('loadedmetadata', onMeta)
    return () => {
      video.removeEventListener('timeupdate', onTimeUpdate)
      video.removeEventListener('loadedmetadata', onMeta)
    }
  }, [])

  useEffect(() => () => {
    if (flashTimer.current) clearTimeout(flashTimer.current)
    if (seekFlashTimer.current) clearTimeout(seekFlashTimer.current)
    if (singleTapTimer.current) clearTimeout(singleTapTimer.current)
  }, [])

  const seekToRatio = useCallback((clientX: number) => {
    const video = videoRef.current
    const bar = progressBarRef.current
    if (!video || !video.duration || !bar) return
    const rect = bar.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    video.currentTime = ratio * video.duration
  }, [])

  useEffect(() => {
    const onMove = (e: MouseEvent | TouchEvent) => {
      if (!isDragging.current) return
      const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX
      seekToRatio(clientX)
    }
    const onEnd = () => {
      if (!isDragging.current) return
      isDragging.current = false
      setIsScrubbing(false)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onEnd)
    document.addEventListener('touchmove', onMove as EventListener, { passive: true })
    document.addEventListener('touchend', onEnd)
    return () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onEnd)
      document.removeEventListener('touchmove', onMove as EventListener)
      document.removeEventListener('touchend', onEnd)
    }
  }, [seekToRatio])

  const handleTap = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) {
      video.play().catch(() => undefined)
      setIsPaused(false)
      setFlashIcon('play')
    } else {
      video.pause()
      setIsPaused(true)
      setFlashIcon('pause')
    }
    if (flashTimer.current) clearTimeout(flashTimer.current)
    flashTimer.current = setTimeout(() => setFlashIcon(null), 600)
  }, [])

  const seekBy = useCallback((side: 'left' | 'right') => {
    const video = videoRef.current
    if (!video || !video.duration) return
    const delta = side === 'left' ? -SEEK_SECONDS : SEEK_SECONDS
    video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + delta))
    setSeekFlash(side)
    if (seekFlashTimer.current) clearTimeout(seekFlashTimer.current)
    seekFlashTimer.current = setTimeout(() => setSeekFlash(null), 500)
  }, [])

  // 영역 탭 처리: 같은 영역 DOUBLE_TAP_MS 이내 재탭이면 더블탭(시크), 아니면 단일탭(재생/일시정지)
  const handleAreaTap = useCallback((side: 'left' | 'right') => {
    const now = Date.now()
    const prev = lastTap.current
    if (prev && prev.side === side && now - prev.time < DOUBLE_TAP_MS) {
      if (singleTapTimer.current) {
        clearTimeout(singleTapTimer.current)
        singleTapTimer.current = null
      }
      lastTap.current = null
      seekBy(side)
      return
    }
    lastTap.current = { time: now, side }
    if (singleTapTimer.current) clearTimeout(singleTapTimer.current)
    singleTapTimer.current = setTimeout(() => {
      singleTapTimer.current = null
      lastTap.current = null
      handleTap()
    }, DOUBLE_TAP_MS)
  }, [seekBy, handleTap])

  const handleLike = useCallback(async () => {
    if (!token) {
      onLoginRequired()
      return
    }
    if (isLikePending.current) return
    isLikePending.current = true
    try {
      const res = await client.post<{ data: { liked: boolean; like_count: number } }>(
        `/feed/${post.id}/like`,
      )
      const { liked: newLiked, like_count: newCount } = res.data.data
      setLiked(newLiked)
      setLikeCount(newCount)
      setLikeAnim(newLiked ? 'burst' : 'shrink')
      setTimeout(() => setLikeAnim(null), 400)
      // Update feed cache so navigating away and back shows correct liked state
      queryClient.setQueryData<InfiniteData<FeedResponse>>(['feed'], (old) => {
        if (!old) return old
        return {
          ...old,
          pages: old.pages.map((page) => ({
            ...page,
            posts: page.posts.map((p) =>
              p.id === post.id ? { ...p, is_liked: newLiked, like_count: newCount } : p
            ),
          })),
        }
      })
      // Sync my-posts cache (profile page)
      queryClient.setQueryData(['my-posts'], (old: unknown) => {
        if (!old || typeof old !== 'object') return old
        const data = old as { posts: Array<{ id: number; like_count: number }> }
        return { ...data, posts: data.posts.map((p) => p.id === post.id ? { ...p, like_count: newCount } : p) }
      })
    } catch {
      // ignore
    } finally {
      isLikePending.current = false
    }
  }, [token, post.id, onLoginRequired, queryClient])

  return (
    <div ref={containerRef} className="relative h-[100dvh] w-full flex-shrink-0 bg-black">
      <video
        ref={videoRef}
        src={post.cdn_url}
        className={`h-full w-full ${fitContain ? 'object-contain' : 'object-cover'}`}
        loop
        muted={isMuted}
        playsInline
        preload="metadata"
      >
        {post.subtitle_url && post.subtitle_status !== 'completed' && (
          <track kind="subtitles" src={post.subtitle_url} srcLang="ko" label={t('subtitleTrackLabel')} default />
        )}
      </video>

      {/* 탭 오버레이 — 좌/우 분리 (단일탭: 재생/일시정지, 더블탭: 시크) */}
      <div className="absolute inset-0 flex" style={{ zIndex: 1 }}>
        <div className="flex-1" onClick={() => handleAreaTap('left')} />
        <div className="flex-1" onClick={() => handleAreaTap('right')} />
      </div>

      {/* 더블탭 시크 플래시 */}
      {seekFlash && (
        <div
          className={clsx(
            'absolute inset-y-0 flex w-1/2 items-center justify-center pointer-events-none',
            seekFlash === 'left' ? 'left-0' : 'right-0',
          )}
          style={{ zIndex: 2 }}
        >
          <div className="flex flex-col items-center gap-2 rounded-pill bg-black/50 px-5 py-4 animate-ping-once">
            {seekFlash === 'left'
              ? <Rewind size={32} className="text-white fill-white" />
              : <FastForward size={32} className="text-white fill-white" />}
            <span className="text-label font-mono text-white">{SEEK_SECONDS}s</span>
          </div>
        </div>
      )}

      {/* 일시정지/재생 아이콘 플래시 */}
      {flashIcon && (
        <div
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
          style={{ zIndex: 2 }}
        >
          <div className="rounded-pill bg-black/50 p-4 animate-ping-once">
            {flashIcon === 'pause'
              ? <Pause size={40} className="text-white fill-white" />
              : <Play size={40} className="text-white fill-white" />
            }
          </div>
        </div>
      )}

      {/* 음소거 토글 — 우상단 */}
      <button
        onClick={(e) => { e.stopPropagation(); onToggleMute() }}
        className="absolute top-4 right-4 flex h-11 w-11 items-center justify-center rounded-pill bg-black/55 text-white"
        style={{ zIndex: 3 }}
        aria-label={isMuted ? t('unmuteAria') : t('muteAria')}
      >
        {isMuted ? <VolumeX size={20} strokeWidth={1.75} /> : <Volume2 size={20} strokeWidth={1.75} />}
      </button>

      {/* 일시정지 중 표시 */}
      {isPaused && !flashIcon && (
        <div
          className="absolute top-4 left-4 rounded-pill bg-black/40 p-2"
          style={{ zIndex: 3 }}
        >
          <Pause size={16} className="text-white fill-white" />
        </div>
      )}

      {/* right actions - 세로 버튼 스택 */}
      <div
        className="absolute right-3 flex flex-col items-center gap-5 bottom-nav-safe"
        style={{ zIndex: 4, paddingBottom: '1.5rem' }}
      >
        {/* 좋아요 */}
        <button
          onClick={(e) => { e.stopPropagation(); handleLike() }}
          className="flex w-11 flex-col items-center gap-2"
        >
          <Heart
            size={26}
            strokeWidth={1.75}
            className={clsx(
              liked ? 'fill-danger text-danger' : 'text-white',
              likeAnim === 'burst' && 'animate-heart-burst',
              likeAnim === 'shrink' && 'animate-heart-shrink',
            )}
          />
          <span className="text-label font-mono text-white">{likeCount}</span>
        </button>

        {/* 댓글 */}
        <button
          data-testid="comment-btn"
          onClick={(e) => { e.stopPropagation(); onCommentClick() }}
          className="flex w-11 flex-col items-center gap-2"
        >
          <MessageCircle size={26} strokeWidth={1.75} className="text-white" />
          <span className="text-label font-mono text-white">{commentCount}</span>
        </button>

        {/* 공유 */}
        <button
          onClick={(e) => {
            e.stopPropagation()
            const shareUrl = `${window.location.origin}/shorts/${post.share_token}`
            const shareMessage = `${t('shareText')}\n${shareUrl}`
            const copyToClipboard = () =>
              window.navigator.clipboard?.writeText(shareUrl)
                .then(() => toast.success(t('shareCopied')))
                .catch(() => toast(t('shareLinkFallback') + shareUrl))
            if (typeof navigator !== 'undefined' && 'share' in navigator) {
              navigator.share({ title: 'Orange Story', text: shareMessage })
                .catch((err) => { if (!(err instanceof DOMException && err.name === 'AbortError')) copyToClipboard() })
            } else {
              copyToClipboard()
            }
          }}
          className="flex w-11 flex-col items-center gap-2"
        >
          <Share2 size={26} strokeWidth={1.75} className="text-white" />
          <span className="text-label text-white">{t('share')}</span>
        </button>
      </div>

      {/* 재생 진행 바 — 드래그로 위치 조정 가능 */}
      <div
        ref={progressBarRef}
        className={`absolute left-0 right-0 flex items-end cursor-pointer bottom-nav-safe ${isScrubbing ? 'h-12' : 'h-8'}`}
        style={{ zIndex: 5 }}
        onClick={(e) => e.stopPropagation()}
        onMouseDown={(e) => { e.stopPropagation(); isDragging.current = true; setIsScrubbing(true); seekToRatio(e.clientX) }}
        onTouchStart={(e) => { isDragging.current = true; setIsScrubbing(true); seekToRatio(e.touches[0].clientX) }}
      >
        <div className={`w-full bg-white/25 transition-all ${isScrubbing ? 'h-2' : 'h-1'}`}>
          <div
            className="h-full bg-white transition-none relative"
            style={{ width: `${progress}%` }}
          >
            {isScrubbing && (
              <div className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-1/2 h-4 w-4 rounded-pill bg-white" />
            )}
          </div>
        </div>
      </div>

      {/* bottom overlay */}
      <div
        className="absolute left-0 right-0 flex flex-col gap-2 bg-gradient-to-t from-black/80 to-transparent pl-5 pr-16 pb-5 pt-20 bottom-nav-safe"
        style={{ zIndex: 3 }}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={(e) => { e.stopPropagation(); navigate(`/users/${post.user_id}`) }}
          className="flex items-center gap-3 active:opacity-70"
        >
          {post.avatar_url ? (
            <img
              src={post.avatar_url}
              alt={post.username}
              className="h-9 w-9 rounded-pill object-cover shrink-0"
            />
          ) : (
            <div
              className={`flex h-9 w-9 items-center justify-center rounded-pill text-body font-bold shrink-0 ${post.profile_color ? 'text-white' : 'bg-accent text-accent-fg'}`}
              style={post.profile_color ? { backgroundColor: post.profile_color } : undefined}
            >
              {post.username.charAt(0).toUpperCase()}
            </div>
          )}
          <p className="text-lead text-white">@{post.username}</p>
        </button>
        {post.caption && (
          <p className="text-body text-white/80 line-clamp-2">{post.caption}</p>
        )}
        {post.tags.length > 0 && (
          <p className="text-eyebrow text-white/60">{post.tags.join(' · ')}</p>
        )}
      </div>

    </div>
  )
}
