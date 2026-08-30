import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import client from '../api/client'
import { getApiErrorMessage } from '../api/errors'
import type { Post } from '../api/types'
import { MAIN_CATEGORIES, MAIN_CATEGORY_LABEL_KEYS, type MainCategory } from '../constants/category'
import { CAPTION_MAX_LEN } from '../constants/caption'

export default function PostEditPage() {
  const { postId } = useParams<{ postId: string }>()
  const navigate = useNavigate()
  const { t } = useTranslation('upload')
  const qc = useQueryClient()

  const [mainCategory, setMainCategory] = useState<MainCategory | null>(null)
  // 세부 태그 UI는 폐기됐지만 저장 시 기존 tags[1:]를 잃지 않으려고 원본을 들고 있는다.
  const [originalTags, setOriginalTags] = useState<string[]>([])
  const [caption, setCaption] = useState('')
  const [error, setError] = useState('')

  const { data: post, isLoading } = useQuery<Post>({
    queryKey: ['post', postId],
    queryFn: async () => {
      const res = await client.get<{ data: { post: Post } }>(`/videos/posts/${postId}`)
      return res.data.data.post
    },
    enabled: !!postId,
  })

  useEffect(() => {
    if (!post) return
    setCaption(post.caption ?? '')
    const tags = post.tags ?? []
    const main = tags[0] && (MAIN_CATEGORIES as readonly string[]).includes(tags[0]) ? (tags[0] as MainCategory) : null
    setMainCategory(main)
    setOriginalTags(tags)
  }, [post])

  const mutation = useMutation({
    mutationFn: async () => {
      // 세부 태그는 더 이상 편집하지 않지만, 기존 값(tags[1:])은 그대로 실어 보존한다.
      const tags = [mainCategory, ...originalTags.slice(1)].filter((v): v is string => Boolean(v))
      const body: Record<string, unknown> = {
        caption,
        tags,
      }
      const res = await client.patch<{ data: { post: Post } }>(`/videos/posts/${postId}`, body)
      return res.data.data.post
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['post', postId] })
      qc.invalidateQueries({ queryKey: ['my-posts'] })
      qc.invalidateQueries({ queryKey: ['feed'] })
      qc.invalidateQueries({ queryKey: ['history'] })
      toast.success(t('edit.saved'))
      navigate(-1)
    },
    onError: (err) => setError(getApiErrorMessage(err, t('edit.failed'))),
  })

  const MAIN_CATEGORY_LABELS = Object.fromEntries(
    MAIN_CATEGORIES.map((cat) => [cat, t(`tagChallenge.${MAIN_CATEGORY_LABEL_KEYS[cat]}`)]),
  ) as Record<MainCategory, string>

  function selectMain(cat: MainCategory) {
    setMainCategory(cat)
  }

  if (isLoading) {
 return <div className="flex h-[100dvh] items-center justify-center bg-theme-page text-theme-muted text-body">{t('edit.loading')}</div>
  }

  return (
    <div className="relative flex h-[100dvh] flex-col bg-theme-page pb-nav-safe lg:max-w-2xl lg:mx-auto">
      <div className="flex items-center gap-2 px-4 pt-4 pb-3">
        <button onClick={() => navigate(-1)} className="flex-shrink-0 p-1 text-theme-muted hover:text-theme-primary" aria-label={t('common:back')}>
          <ChevronLeft size={20} strokeWidth={1.5} />
        </button>
        <span className="text-body font-semibold text-theme-primary">{t('edit.title')}</span>
      </div>

      <div className="flex flex-1 flex-col px-6 pt-2 pb-6 overflow-y-auto gap-4">
        {/* 카테고리 */}
        <div>
          <p className="mb-2 text-body font-semibold text-theme-primary">{t('tagChallenge.category')}</p>
          <div className="flex gap-2 mb-3">
            {MAIN_CATEGORIES.map((cat) => (
              <button key={cat} onClick={() => selectMain(cat)} className={`flex-1 rounded-card py-3 text-body font-medium transition-colors ${mainCategory === cat ? 'bg-accent text-accent-fg' : 'bg-theme-surface text-theme-muted'}`}>
                {MAIN_CATEGORY_LABELS[cat]}
              </button>
            ))}
          </div>
        </div>

        {/* 설명 */}
        <div className="flex flex-col gap-1">
          <p className="text-body font-semibold text-theme-primary mb-1">{t('caption.captionLabel')} <span className="text-label font-normal text-theme-muted">{t('caption.captionOptional')}</span></p>
          <textarea value={caption} onChange={(e) => setCaption(e.target.value.slice(0, CAPTION_MAX_LEN))} maxLength={CAPTION_MAX_LEN} placeholder={t('caption.captionPlaceholder')} rows={5} className="resize-none rounded-card bg-theme-surface px-4 py-3 text-theme-primary placeholder-theme-muted outline-none focus:ring-2 focus:ring-accent" />
          <p className="text-right text-label text-theme-muted">{caption.length}/{CAPTION_MAX_LEN}</p>
        </div>

        {error && <p className="text-body text-danger">{error}</p>}

        <button
          onClick={() => {
            setError('')
            // 카테고리 미선택 상태로 저장하면 tags[0]이 통째로 빠지고 tags[1]이 그 자리로 밀린다.
            if (!mainCategory) { setError(t('tagChallenge.categoryRequired')); return }
            mutation.mutate()
          }}
          disabled={mutation.isPending}
          className="mt-auto w-full rounded-card bg-accent py-3 font-semibold text-accent-fg disabled:opacity-60"
        >
          {mutation.isPending ? t('edit.saving') : t('edit.save')}
        </button>
      </div>
    </div>
  )
}
