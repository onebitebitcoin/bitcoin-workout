import { useState, useRef, useEffect } from 'react'
import { X, Send, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { InfiniteData } from '@tanstack/react-query'
import client from '../api/client'
import type { Comment, FeedResponse } from '../api/types'
import { useAuthStore } from '../store/auth'
import UserAvatar from './UserAvatar'

interface CommentSheetProps {
  postId: number
  open: boolean
  onClose: () => void
  onLoginRequired: () => void
}

interface CommentRowProps {
  comment: Comment
  canDelete: boolean
  onReply: (c: Comment) => void
  onDelete: (c: Comment) => void
}

function CommentRow({ comment, canDelete, onReply, onDelete }: CommentRowProps) {
  const { t } = useTranslation('feed')
  return (
    <div className="flex items-start gap-2">
      <UserAvatar
        username={comment.username}
        avatarUrl={comment.avatar_url}
        profileColor={comment.profile_color}
        size={28}
        className="shrink-0 mt-1"
      />
      <div className="flex-1 min-w-0">
        <span className="text-label font-semibold text-theme-primary">@{comment.username}</span>
        <p className="text-body text-white mt-1 break-words">{comment.content}</p>
        <button
          type="button"
          onClick={() => onReply(comment)}
          className="text-label text-theme-muted hover:text-theme-primary mt-1"
        >
          {t('replyButton')}
        </button>
      </div>
      {canDelete && (
        <button
          onClick={() => onDelete(comment)}
          className="text-theme-muted hover:text-danger mt-1 shrink-0"
        >
          <Trash2 size={14} />
        </button>
      )}
    </div>
  )
}

export default function CommentSheet({ postId, open, onClose, onLoginRequired }: CommentSheetProps) {
  const { t } = useTranslation('feed')
  const qc = useQueryClient()
  const token = useAuthStore((s) => s.token)
  const user = useAuthStore((s) => s.user)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [hasContent, setHasContent] = useState(false)
  const [replyTo, setReplyTo] = useState<{ id: number; username: string } | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const sheetRef = useRef<HTMLDivElement>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const isComposingRef = useRef(false)

  // 키보드가 올라올 때 시트 위치 + 높이 동적 조정
  useEffect(() => {
    const vv = window.visualViewport
    if (!vv || !open) return
    const sheet = sheetRef.current
    const form = formRef.current
    const reposition = () => {
      // Android Chrome은 키보드가 열리면 visual viewport를 아래로 패닝(offsetTop > 0)하므로
      // offsetTop을 빼야 시트가 키보드 바로 위에 붙는다. iOS Safari는 offsetTop이 항상 0이라 영향 없음.
      const keyboardHeight = Math.max(0, window.innerHeight - vv.height - vv.offsetTop)
      if (sheet) {
        sheet.style.bottom = `${keyboardHeight}px`
        sheet.style.maxHeight = `${vv.height - 16}px`
      }
      // 키보드가 올라와 있을 때 safe-area 패딩 제거 (키보드가 이미 safe area 흡수)
      if (form) {
        form.style.paddingBottom = keyboardHeight > 0 ? '0' : ''
      }
    }
    reposition() // 시트 오픈 즉시 실행 (이미 키보드가 올라온 경우 대응)
    vv.addEventListener('resize', reposition)
    vv.addEventListener('scroll', reposition)
    return () => {
      vv.removeEventListener('resize', reposition)
      vv.removeEventListener('scroll', reposition)
      if (sheet) {
        sheet.style.bottom = ''
        sheet.style.maxHeight = ''
      }
      if (form) {
        form.style.paddingBottom = ''
      }
    }
  }, [open])

  const { data: comments = [] } = useQuery<Comment[]>({
    queryKey: ['comments', postId],
    queryFn: async () => {
      const res = await client.get<{ data: { comments: Comment[] } }>(`/feed/${postId}/comments`)
      return res.data.data.comments
    },
    enabled: open,
  })

  // 답글 포함 전체 개수 (헤더 표시용)
  const totalCount = comments.reduce((sum, c) => sum + 1 + (c.replies?.length ?? 0), 0)

  function updateFeedCommentCount(delta: number) {
    qc.setQueriesData<InfiniteData<FeedResponse>>(
      { queryKey: ['feed'] },
      (old) => {
        if (!old) return old
        return {
          ...old,
          pages: old.pages.map((page) => ({
            ...page,
            posts: page.posts.map((p) =>
              p.id === postId ? { ...p, comment_count: p.comment_count + delta } : p
            ),
          })),
        }
      }
    )
    // Sync my-posts cache (profile page)
    qc.setQueryData(['my-posts'], (old: unknown) => {
      if (!old || typeof old !== 'object') return old
      const data = old as { posts: Array<{ id: number; comment_count: number }> }
      return { ...data, posts: data.posts.map((p) => p.id === postId ? { ...p, comment_count: p.comment_count + delta } : p) }
    })
  }

  const addComment = useMutation({
    mutationFn: async ({ text, parentId }: { text: string; parentId: number | null }) => {
      await client.post(`/feed/${postId}/comments`, {
        content: text,
        parent_id: parentId ?? undefined,
      })
    },
    onSuccess: () => {
      if (inputRef.current) {
        inputRef.current.value = ''
        // 키보드 내림 — 등록 후 시트가 키보드 높이만큼 떠 있는 현상 방지
        inputRef.current.blur()
      }
      setHasContent(false)
      setSubmitError(null)
      setReplyTo(null)
      qc.invalidateQueries({ queryKey: ['comments', postId] }).catch(() => undefined)
      updateFeedCommentCount(1)
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: { message?: string } } } })
          ?.response?.data?.detail?.message ?? t('commentSubmitError')
      setSubmitError(msg)
    },
  })

  const deleteComment = useMutation({
    mutationFn: async (c: Comment) => {
      await client.delete(`/feed/${postId}/comments/${c.id}`)
      // 최상위 댓글 삭제 시 딸린 답글도 함께 삭제되므로 그 수만큼 차감
      return 1 + (c.replies?.length ?? 0)
    },
    onSuccess: (removed) => {
      qc.invalidateQueries({ queryKey: ['comments', postId] }).catch(() => undefined)
      updateFeedCommentCount(-removed)
    },
  })

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  // 시트가 닫히면 답글 상태 초기화
  useEffect(() => {
    if (!open) setReplyTo(null)
  }, [open])

  function startReply(c: Comment) {
    if (!token) {
      onLoginRequired()
      return
    }
    setReplyTo({ id: c.id, username: c.username })
    inputRef.current?.focus()
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!token) {
      onLoginRequired()
      return
    }
    if (isComposingRef.current) return
    const text = (inputRef.current?.value ?? '').trim()
    if (!text) return
    if (text.length < 5) {
      setSubmitError(t('commentTooShort'))
      return
    }
    setSubmitError(null)
    addComment.mutate({ text, parentId: replyTo?.id ?? null })
  }

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-[55] bg-black/60"
          onClick={onClose}
        />
      )}

      {/* Sheet — 모바일: 하단 슬라이드업 / 데스크탑: 중앙 모달 */}
      <div
        ref={sheetRef}
        data-testid="comment-sheet"
        className={[
          'fixed z-[60] flex flex-col bg-theme-surface backdrop-blur duration-300',
          'bottom-0 left-0 right-0 rounded-t-2xl transition-transform',
          'lg:bottom-auto lg:right-auto lg:top-1/2 lg:left-1/2 lg:w-full lg:max-w-md lg:rounded-card',
          open
            ? 'translate-y-0 lg:-translate-x-1/2 lg:-translate-y-1/2'
            : 'translate-y-full lg:-translate-x-1/2 lg:opacity-0 lg:pointer-events-none',
        ].join(' ')}
        style={{ maxHeight: '75dvh' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-theme-border">
          <span className="font-semibold text-white">{t('commentCount', { count: totalCount })}</span>
          <button onClick={onClose} className="text-theme-muted hover:text-theme-primary">
            <X size={20} />
          </button>
        </div>

        {/* Comments list */}
        <div className="flex-1 overflow-y-auto px-4 py-2 space-y-3">
          {comments.length === 0 && (
            <p className="text-center text-theme-muted py-8 text-body">{t('commentEmpty')}</p>
          )}
          {comments.map((c) => (
            <div key={c.id} className="space-y-2">
              <CommentRow
                comment={c}
                canDelete={!!user && user.id === c.user_id}
                onReply={startReply}
                onDelete={(target) => deleteComment.mutate(target)}
              />
              {c.replies && c.replies.length > 0 && (
                <div className="ml-8 space-y-2 border-l border-theme-border pl-3">
                  {c.replies.map((r) => (
                    <CommentRow
                      key={r.id}
                      comment={r}
                      canDelete={!!user && user.id === r.user_id}
                      onReply={startReply}
                      onDelete={(target) => deleteComment.mutate(target)}
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Input */}
        <form ref={formRef} onSubmit={handleSubmit} className="flex flex-col px-4 py-3 border-t border-theme-border pb-safe gap-1">
          {replyTo && (
            <div className="flex items-center justify-between px-1 text-label text-theme-muted">
              <span>{t('replyingTo', { username: replyTo.username })}</span>
              <button
                type="button"
                onClick={() => setReplyTo(null)}
                className="text-theme-muted hover:text-theme-primary"
              >
                <X size={14} />
              </button>
            </div>
          )}
          {submitError && (
            <p className="text-label text-danger px-1">{submitError}</p>
          )}
          <div className="flex gap-2">
          <input
            ref={inputRef}
            onInput={(e) => {
              setHasContent(!!e.currentTarget.value.trim())
              if (submitError) setSubmitError(null)
            }}
            onCompositionStart={() => { isComposingRef.current = true }}
            onCompositionEnd={() => { isComposingRef.current = false }}
            placeholder={
              !token
                ? t('commentLoginPlaceholder')
                : replyTo
                  ? t('replyPlaceholder')
                  : t('commentPlaceholder')
            }
            className="flex-1 rounded-pill bg-theme-surface2 px-4 py-2 text-body text-theme-primary placeholder-theme-muted outline-none"
            maxLength={500}
          />
          <button
            type="submit"
            disabled={!hasContent || addComment.isPending}
            className="rounded-pill bg-accent p-2 text-accent-fg disabled:opacity-40"
          >
            <Send size={16} />
          </button>
          </div>
        </form>
      </div>
    </>
  )
}
