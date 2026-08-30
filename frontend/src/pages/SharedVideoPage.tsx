import { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Heart, Eye, Target } from 'lucide-react'
import client from '../api/client'
import type { Post } from '../api/types'
import LoadingScreen from '../components/LoadingScreen'
import { useAuthStore } from '../store/auth'
import { OG_DESCRIPTION_MAX_LEN } from '../constants/caption'

function setMetaProperty(property: string, content: string) {
  let el = document.querySelector<HTMLMetaElement>(`meta[property="${property}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute('property', property)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

function setMetaName(name: string, content: string) {
  let el = document.querySelector<HTMLMetaElement>(`meta[name="${name}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute('name', name)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

export default function SharedVideoPage() {
  const { t } = useTranslation('feed')
  const { shareToken } = useParams<{ shareToken: string }>()
  const navigate = useNavigate()
  const token = useAuthStore((s) => s.token)

  const { data: post, isLoading } = useQuery<Post>({
    queryKey: ['shared-post', shareToken],
    queryFn: async () => {
      const res = await client.get<{ data: { post: Post } }>(`/videos/posts/share/${shareToken}`)
      return res.data.data.post
    },
    enabled: !!shareToken,
  })

  useEffect(() => {
    if (!post) return

    const title = `@${post.username} - Orange Story`
    // 설명은 최대 2200자까지 가능하다 — og:description 에 전문을 넣지 않고 잘라서 보낸다.
    const rawDescription = post.caption ?? t('appTagline')
    const description =
      rawDescription.length > OG_DESCRIPTION_MAX_LEN
        ? `${rawDescription.slice(0, OG_DESCRIPTION_MAX_LEN - 1).trimEnd()}…`
        : rawDescription
    const image = post.thumbnail_url ?? `${window.location.origin}/og-image.png`

    document.title = title
    setMetaProperty('og:title', title)
    setMetaProperty('og:description', description)
    setMetaProperty('og:image', image)
    setMetaProperty('og:type', 'video.other')
    setMetaProperty('og:video', post.cdn_url)
    setMetaProperty('og:video:type', 'video/mp4')
    setMetaName('twitter:title', title)
    setMetaName('twitter:description', description)
    setMetaName('twitter:image', image)
    setMetaName('twitter:card', 'player')

    return () => {
      document.title = `Orange Story | ${t('appTagline')}`
    }
  }, [post, t])

  if (isLoading) return <LoadingScreen />

  if (!post) return (
    <div className="flex h-[100dvh] items-center justify-center bg-theme-page">
      <p className="text-theme-muted">{t('videoNotFound')}</p>
    </div>
  )

  return (
    <div className="flex flex-col h-[100dvh] bg-black">
      <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-4 pt-safe pt-4 pb-3 bg-gradient-to-b from-black/60 to-transparent">
        <button onClick={() => navigate('/')} className="flex h-9 w-9 items-center justify-center rounded-pill bg-black/30">
          <ArrowLeft size={20} color="white" />
        </button>
        <div className="flex items-center gap-2">
          <Target size={16} color="white" />
          <span className="text-body font-semibold text-white">Orange Story</span>
        </div>
        <div className="w-9" />
      </div>

      <video
        src={post.cdn_url}
        className="h-full w-full object-contain"
        autoPlay playsInline controls
      >
        {post.subtitle_url && post.subtitle_status !== 'completed' && (
          <track kind="subtitles" src={post.subtitle_url} srcLang="ko" label={t('subtitleTrackLabel')} default />
        )}
      </video>

      <div className="absolute bottom-0 left-0 right-0 z-10 px-4 pb-8 pt-16 bg-gradient-to-t from-black/70 to-transparent">
        <p className="text-white font-semibold mb-1">@{post.username}</p>
        {post.caption && <p className="text-white/80 text-body mb-3">{post.caption}</p>}
        <div className="flex items-center gap-4 mb-4">
          <div className="flex items-center gap-2 text-white/80">
            <Heart size={14} /><span className="text-body">{post.like_count}</span>
          </div>
          <div className="flex items-center gap-2 text-white/80">
            <Eye size={14} /><span className="text-body">{post.view_count}</span>
          </div>
        </div>
        {!token && (
          <button
            onClick={() => navigate('/login')}
            className="w-full rounded-card bg-accent py-3 text-body font-semibold text-accent-fg"
          >
            {t('loginCta')}
          </button>
        )}
      </div>
    </div>
  )
}
