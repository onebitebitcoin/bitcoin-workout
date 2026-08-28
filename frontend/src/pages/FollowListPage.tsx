import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, UserPlus, UserCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import type { FollowUser } from '../api/types'
import UserAvatar from '../components/UserAvatar'
import { useAuthStore } from '../store/auth'

type Mode = 'followers' | 'following'

export default function FollowListPage({ mode }: { mode: Mode }) {
  const { userId } = useParams<{ userId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation('profile')
  const qc = useQueryClient()
  const currentUser = useAuthStore((s) => s.user)

  const queryKey = ['follow-list', mode, userId, location.pathname]
  const { data: users = [], isLoading } = useQuery<FollowUser[]>({
    queryKey,
    queryFn: async () => {
      const res = await client.get<{ data: { users: FollowUser[] } }>(`/users/${userId}/${mode}`)
      return res.data.data.users
    },
    enabled: !!userId,
  })

  const followMutation = useMutation({
    mutationFn: async ({ targetId, follow }: { targetId: number; follow: boolean }) => {
      if (follow) await client.post(`/users/${targetId}/follow`)
      else await client.delete(`/users/${targetId}/follow`)
      return { targetId, follow }
    },
    onMutate: async ({ targetId, follow }) => {
      await qc.cancelQueries({ queryKey })
      const prev = qc.getQueryData<FollowUser[]>(queryKey)
      if (prev) {
        qc.setQueryData<FollowUser[]>(queryKey, prev.map((u) => (u.id === targetId ? { ...u, is_following: follow } : u)))
      }
      return { prev }
    },
    onError: (_e, _v, ctx) => { if (ctx?.prev) qc.setQueryData(queryKey, ctx.prev) },
    onSettled: () => { qc.invalidateQueries({ queryKey }) },
  })

  return (
    <div className="flex flex-col h-[100dvh] overflow-y-auto bg-theme-page pb-nav-safe lg:max-w-2xl lg:mx-auto">
      <div className="flex items-center gap-3 px-4 pt-5 pb-4">
        <button onClick={() => navigate(-1)} className="text-theme-muted flex-shrink-0"><ArrowLeft size={20} /></button>
        <h1 className="text-body font-semibold text-theme-primary">{mode === 'followers' ? t('followers') : t('following')}</h1>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2 px-4">
          {[1, 2, 3].map((i) => <div key={i} className="h-12 rounded-card bg-theme-surface2" />)}
        </div>
      ) : users.length === 0 ? (
        <p className="text-center text-body text-theme-muted mt-12">{mode === 'followers' ? t('noFollowers') : t('noFollowing')}</p>
      ) : (
        <div className="flex flex-col">
          {users.map((u) => (
            <div key={u.id} className="flex items-center gap-3 px-4 py-3">
              <button onClick={() => navigate(`/users/${u.id}`)} className="flex items-center gap-3 flex-1 min-w-0">
                <UserAvatar username={u.username} avatarUrl={u.avatar_url} size={36} />
                <span className="text-body font-medium text-theme-primary truncate">@{u.username}</span>
              </button>
              {currentUser && currentUser.id !== u.id && (
                <button
                  onClick={() => followMutation.mutate({ targetId: u.id, follow: !u.is_following })}
                  disabled={followMutation.isPending}
                  className={`flex-shrink-0 flex items-center gap-1 rounded-pill px-3 py-2 text-label font-semibold transition-colors disabled:opacity-60 ${
                    u.is_following ? 'bg-theme-surface2 text-theme-muted' : 'bg-accent text-accent-fg'
                  }`}
                >
                  {u.is_following ? <><UserCheck size={13} /> {t('followingBtn')}</> : <><UserPlus size={13} /> {t('followBtn')}</>}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
