import { useState, useEffect } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import client from '../api/client'
import type { Post } from '../api/types'
import VideoCard from '../components/VideoCard'
import CommentSheet from '../components/CommentSheet'
import { useUiStore } from '../store/ui'

export default function PostDetailPage() {
  const { postId } = useParams<{ postId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const setCommentOpen = useUiStore((s) => s.setCommentOpen)

  const [isMuted, setIsMuted] = useState(true)
  const [commentOpen, setLocalCommentOpen] = useState(false)

  // 시트 열린 채 라우트 이탈(뒤로가기 등) 시 전역 commentOpen 잔류 → BottomNav 영구 숨김 방지
  useEffect(() => () => setCommentOpen(false), [setCommentOpen])

  const { data: post, isLoading, isError } = useQuery<Post>({
    queryKey: ['post', postId],
    queryFn: async () => {
      const res = await client.get<{ data: { post: Post } }>(`/videos/posts/${postId}`)
      return { ...res.data.data.post, is_liked: false }
    },
    enabled: !!postId,
  })

  // ?comment=1 → CommentSheet 자동 오픈
  useEffect(() => {
    if (post && searchParams.get('comment') === '1') {
      setLocalCommentOpen(true)
      setCommentOpen(true)
    }
  }, [post, searchParams, setCommentOpen])

  function openComment() {
    setLocalCommentOpen(true)
    setCommentOpen(true)
  }

  function closeComment() {
    setLocalCommentOpen(false)
    setCommentOpen(false)
  }

  if (isLoading) {
    return (
      <div className="flex h-[100dvh] items-center justify-center bg-black">
        <div className="h-8 w-8 rounded-pill border-2 border-white/30 border-t-white animate-spin" />
      </div>
    )
  }

  if (isError || !post) {
    return (
      <div className="flex h-[100dvh] flex-col items-center justify-center gap-3 bg-black">
        <p className="text-body text-white/60">영상을 찾을 수 없어요</p>
        <button onClick={() => navigate(-1)} className="text-label text-white/40 underline">
          뒤로 가기
        </button>
      </div>
    )
  }

  return (
    <div className="relative h-[100dvh] bg-black overflow-hidden">
      {/* 뒤로가기 버튼 */}
      <button
        onClick={() => navigate(-1)}
        className="absolute top-4 left-4 z-20 flex h-9 w-9 items-center justify-center rounded-pill bg-black/40 text-white"
      >
        <ArrowLeft size={20} />
      </button>

      <VideoCard
        post={post}
        onLoginRequired={() => navigate('/login')}
        onCommentClick={openComment}
        isMuted={isMuted}
        onToggleMute={() => setIsMuted((m) => !m)}
      />

      <CommentSheet
        postId={post.id}
        open={commentOpen}
        onClose={closeComment}
        onLoginRequired={() => navigate('/login')}
      />
    </div>
  )
}
