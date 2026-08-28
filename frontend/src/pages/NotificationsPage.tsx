import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Bell } from 'lucide-react'
import client from '../api/client'
import type { AppNotification } from '../api/types'
import UserAvatar from '../components/UserAvatar'

function timeAgo(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60) return `${diff}초 전`
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`
  return `${Math.floor(diff / 86400)}일 전`
}

export default function NotificationsPage() {
  const { t } = useTranslation('notification')
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data, isLoading } = useQuery<AppNotification[]>({
    queryKey: ['notifications'],
    queryFn: async () => {
      const res = await client.get<{ data: { notifications: AppNotification[] } }>('/notifications')
      return res.data.data.notifications
    },
  })

  const readAll = useMutation({
    mutationFn: () => client.post('/notifications/read-all'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications-unread'] })
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  useEffect(() => {
    readAll.mutate()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleClick(n: AppNotification) {
    if (n.type === 'follow') {
      navigate(`/users/${n.actor.id}`)
      return
    }
    const path = n.type === 'comment'
      ? `/posts/${n.post_id}?comment=1`
      : `/posts/${n.post_id}`
    navigate(path)
  }

  const notifications = data ?? []

  return (
    <div className="flex flex-col h-[100dvh] overflow-y-auto bg-theme-page pb-nav-safe lg:max-w-2xl lg:mx-auto">
      <div className="flex items-center gap-3 px-4 pt-5 pb-4 border-b border-theme-border">
        <Bell size={20} strokeWidth={1.5} className="text-theme-primary" />
        <h1 className="text-title font-semibold text-theme-primary">{t('title')}</h1>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-0">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-3">
              <div className="h-10 w-10 rounded-pill bg-theme-surface2 flex-shrink-0" />
              <div className="flex-1 flex flex-col gap-2">
                <div className="h-3 w-3/4 rounded bg-theme-surface2" />
                <div className="h-2.5 w-1/3 rounded bg-theme-surface2" />
              </div>
            </div>
          ))}
        </div>
      ) : notifications.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 py-20">
          <Bell size={40} strokeWidth={1} className="text-theme-surface2" />
          <p className="text-body text-theme-muted">{t('empty')}</p>
        </div>
      ) : (
        <div className="flex flex-col">
          {notifications.map((n) => (
            <button
              key={n.id}
              onClick={() => handleClick(n)}
              className={`flex items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-theme-surface active:bg-theme-surface2 ${
                !n.is_read ? 'bg-accent/5' : ''
              }`}
            >
              <div className="relative flex-shrink-0">
                <UserAvatar
                  username={n.actor.username}
                  avatarUrl={n.actor.avatar_url}
                  profileColor={n.actor.profile_color}
                  size={40}
                />
                {!n.is_read && (
                  <span className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-pill bg-danger border-2 border-theme-page" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-body text-theme-primary leading-snug">
                  {n.type === 'comment'
                    ? t('commented', { username: n.actor.username })
                    : n.type === 'follow'
                    ? t('followed', { username: n.actor.username })
                    : t('liked', { username: n.actor.username })}
                </p>
                <p className="text-label text-theme-muted mt-1">{timeAgo(n.created_at)}</p>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
