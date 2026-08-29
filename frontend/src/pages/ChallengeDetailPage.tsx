import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, Target, Users, CheckCircle, CalendarDays,
  Edit2, UserCircle, Play, TrendingUp, CircleCheck, XCircle, Trash2,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import type { Challenge, ChallengeParticipant, ChallengeVideo } from '../api/types'
import { getApiErrorMessage } from '../api/errors'
import { useAuthStore } from '../store/auth'
import LoadingScreen from '../components/LoadingScreen'

function formatDate(dateStr: string) {
  const d = new Date(dateStr)
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`
}

function DescriptionText({ text }: { text: string }) {
  const parts = text.split(/(https?:\/\/[^\s]+)/)
  return (
    <p className="text-body text-theme-muted leading-relaxed whitespace-pre-wrap break-words select-text">
      {parts.map((part, i) =>
        /^https?:\/\//.test(part) ? (
          <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="text-accent underline break-all">
            {part}
          </a>
        ) : part
      )}
    </p>
  )
}

function UploadCount({ count, total }: { count: number; total: number }) {
  return (
    <span className="flex items-center gap-1 text-label text-theme-muted">
      <Target size={11} className="text-accent" />
      {count} / {total}
    </span>
  )
}

export default function ChallengeDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const { t } = useTranslation('challenge')
  const qc = useQueryClient()
  const [showCloseConfirm, setShowCloseConfirm] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false)
  const [actionError, setActionError] = useState('')
  const [activeTab, setActiveTab] = useState<'info' | 'manager'>('info')

  const { data: challenge, isLoading, isError } = useQuery<Challenge>({
    queryKey: ['challenge', id],
    queryFn: async () => {
      const res = await client.get<{ data: { challenge: Challenge } }>(`/challenges/${id}`)
      return res.data.data.challenge
    },
    enabled: !!id,
  })

  const isCreator = !!user && !!challenge && (user.id === challenge.creator_id || user.is_admin)
  const managerEnabled = isCreator && activeTab === 'manager'

  const { data: participants = [], isLoading: participantsLoading } = useQuery<ChallengeParticipant[]>({
    queryKey: ['challenge-participants', id],
    queryFn: async () => {
      const res = await client.get<{ data: { participants: ChallengeParticipant[] } }>(`/challenges/${id}/participants`)
      return res.data.data.participants
    },
    enabled: managerEnabled,
  })

  const { data: challengeVideos = [], isLoading: videosLoading } = useQuery<ChallengeVideo[]>({
    queryKey: ['challenge-videos', id],
    queryFn: async () => {
      const res = await client.get<{ data: { videos: ChallengeVideo[] } }>(`/challenges/${id}/videos`)
      return res.data.data.videos
    },
    enabled: managerEnabled,
  })

  const completeMutation = useMutation({
    mutationFn: (userId: number) =>
      client.patch(`/challenges/${id}/participants/${userId}/complete`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['challenge-participants', id] }).catch(() => undefined)
    },
  })

  const joinMutation = useMutation({
    mutationFn: () => client.post(`/challenges/${id}/join`),
    onSuccess: () => {
      qc.setQueryData<Challenge>(['challenge', id], (old) =>
        old ? { ...old, joined: true, participant_count: old.participant_count + 1 } : old
      )
      qc.setQueriesData<Challenge[]>(
        { queryKey: ['challenges'] },
        (old) => old?.map((c) => c.id === Number(id) ? { ...c, joined: true, participant_count: c.participant_count + 1 } : c)
      )
      qc.invalidateQueries({ queryKey: ['my-challenges'] }).catch(() => undefined)
      setActionError('')
    },
    onError: (e: unknown) => setActionError(getApiErrorMessage(e, t('detail.joinError'))),
  })

  const leaveMutation = useMutation({
    mutationFn: () => client.delete(`/challenges/${id}/leave`),
    onSuccess: () => {
      qc.setQueryData<Challenge>(['challenge', id], (old) =>
        old ? { ...old, joined: false, completed: false, my_upload_count: 0, participant_count: old.participant_count - 1 } : old
      )
      qc.setQueriesData<Challenge[]>(
        { queryKey: ['challenges'] },
        (old) => old?.map((c) => c.id === Number(id) ? { ...c, joined: false, completed: false, my_upload_count: 0, participant_count: c.participant_count - 1 } : c)
      )
      qc.invalidateQueries({ queryKey: ['my-challenges'] }).catch(() => undefined)
      setShowLeaveConfirm(false)
      setActionError('')
    },
    onError: (e: unknown) => {
      setShowLeaveConfirm(false)
      setActionError(getApiErrorMessage(e, t('detail.leaveError')))
    },
  })

  const closeMutation = useMutation({
    mutationFn: () => client.patch(`/challenges/${id}/close`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['challenges'] }).catch(() => undefined)
      qc.invalidateQueries({ queryKey: ['my-challenges'] }).catch(() => undefined)
      navigate('/challenges', { replace: true })
    },
    onError: (e: unknown) => {
      setShowDeleteConfirm(false)
      setActionError(getApiErrorMessage(e, t('detail.deleteError')))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => client.delete(`/challenges/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['challenges'] }).catch(() => undefined)
      qc.invalidateQueries({ queryKey: ['my-challenges'] }).catch(() => undefined)
      navigate('/challenges', { replace: true })
    },
    onError: (e: unknown) => {
      setShowDeleteConfirm(false)
      setActionError(getApiErrorMessage(e, t('detail.hardDeleteError')))
    },
  })

  if (isLoading) return <LoadingScreen />

  if (isError || !challenge) {
    return (
      <div className="flex h-[100dvh] flex-col items-center justify-center gap-2 bg-theme-page lg:max-w-2xl lg:mx-auto">
        <p className="text-body text-theme-muted">{t('detail.notFound')}</p>
        <button onClick={() => navigate('/challenges')} className="text-label text-accent">
          {t('detail.backToList')}
        </button>
      </div>
    )
  }

  const completedCount = participants.filter((p) => p.completed_at !== null).length
  const avgProgress = participants.length > 0
    ? Math.round(participants.reduce((sum, p) => sum + p.progress, 0) / participants.length)
    : 0

  return (
    <div className="flex flex-col h-[100dvh] overflow-y-auto bg-theme-page pb-nav-safe lg:max-w-2xl lg:mx-auto">
      {/* header */}
      <div className="px-4 pt-5 pb-3 flex items-center gap-2">
        <button onClick={() => navigate(-1)} className="text-theme-muted flex-shrink-0">
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-title text-theme-primary flex-1 truncate">{challenge.title}</h1>
        {!challenge.is_active && (
          <span className="text-label bg-theme-surface2 text-theme-muted px-2 py-1 rounded-pill font-medium flex-shrink-0">
            {t('detail.closedBadge')}
          </span>
        )}
        {isCreator && (
          <>
            <span className="text-label bg-accent/15 text-accent px-2 py-1 rounded-pill font-medium flex-shrink-0">
              {t('detail.managerBadge')}
            </span>
            <button
              onClick={() => navigate(`/challenges/${id}/edit`)}
              className="text-theme-muted flex-shrink-0 p-1"
              aria-label={t('detail.editLabel')}
            >
              <Edit2 size={17} />
            </button>
            {challenge.is_active ? (
              <button
                onClick={() => setShowCloseConfirm(true)}
                className="text-accent-text flex-shrink-0 p-1"
                aria-label={t('detail.closeLabel')}
              >
                <XCircle size={17} />
              </button>
            ) : (
              <button
                onClick={() => setShowDeleteConfirm(true)}
                className="text-danger flex-shrink-0 p-1"
                aria-label={t('detail.deleteLabel')}
              >
                <Trash2 size={17} />
              </button>
            )}
          </>
        )}
      </div>

      {/* tabs (manager only) */}
      {isCreator && (
        <div className="px-4 mb-2 flex gap-1">
          <button
            onClick={() => setActiveTab('info')}
            className={`flex-1 py-2 rounded-card text-body font-medium transition-colors ${
              activeTab === 'info'
                ? 'bg-accent text-accent-fg'
                : 'bg-theme-surface text-theme-muted'
            }`}
          >
            {t('detail.tabInfo')}
          </button>
          <button
            onClick={() => setActiveTab('manager')}
            className={`flex-1 py-2 rounded-card text-body font-medium transition-colors ${
              activeTab === 'manager'
                ? 'bg-accent text-accent-fg'
                : 'bg-theme-surface text-theme-muted'
            }`}
          >
            {t('detail.tabManager')}
          </button>
        </div>
      )}

      {/* info tab */}
      {activeTab === 'info' && (
        <div className="flex flex-col gap-4 px-4 pb-4">
          {/* image */}
          {(challenge.image_thumb_url ?? challenge.image_url) && (
            <div className="flex justify-center pt-1">
              <div className="h-20 w-20 rounded-pill overflow-hidden bg-theme-surface2 ring-2 ring-theme-border">
                <img
                  src={challenge.image_thumb_url ?? challenge.image_url ?? ''}
                  alt=""
                  loading="eager"
                  decoding="async"
                  className="w-full h-full object-cover"
                />
              </div>
            </div>
          )}

          {/* reward title */}
          <div className="flex flex-col gap-1">
            <span className="text-label text-theme-muted">{t('detail.rewardTitle')}</span>
            <div className="inline-flex items-center gap-2 rounded-pill bg-accent/15 px-3 py-2 self-start">
              <Target size={13} className="text-accent" />
              <span className="text-body font-semibold text-accent">{challenge.reward_title}</span>
            </div>
          </div>

          {/* description */}
          {challenge.description && (
            <DescriptionText text={challenge.description} />
          )}

          {/* challenge info */}
          <div className="rounded-card bg-theme-surface p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between text-body">
              <span className="text-theme-muted flex items-center gap-2">
                <CalendarDays size={14} />
                {t('detail.period')}
              </span>
              <span className="text-theme-primary font-medium">
                {formatDate(challenge.start_date)} ~ {formatDate(challenge.end_date)}
              </span>
            </div>
            {challenge.recruit_end && (
              <div className="flex items-center justify-between text-body">
                <span className="text-theme-muted flex items-center gap-2">
                  <CalendarDays size={14} />
                  {t('detail.recruitPeriod')}
                </span>
                <span className="text-theme-primary font-medium">
                  {challenge.recruit_start ? formatDate(challenge.recruit_start) + ' ~ ' : '~ '}
                  {formatDate(challenge.recruit_end)}
                </span>
              </div>
            )}
            <div className="flex items-center justify-between text-body">
              <span className="text-theme-muted flex items-center gap-2">
                <Users size={14} />
                {t('detail.participants')}
              </span>
              <span className="text-theme-primary font-medium">
                {challenge.participant_count}
                {challenge.max_participants ? ` / ${challenge.max_participants}` : ''}
              </span>
            </div>
            <div className="flex items-center justify-between text-body">
              <span className="text-theme-muted">{t('detail.recruitStatus')}</span>
              <span className={`text-label font-semibold px-2 py-1 rounded-pill ${
                challenge.is_recruiting !== false
                  ? 'bg-accent/15 text-accent'
                  : 'bg-theme-surface2 text-theme-muted'
              }`}>
                {challenge.is_recruiting !== false ? t('detail.recruiting') : t('detail.closed')}
              </span>
            </div>
            {challenge.goal_description && (
              <div className="flex items-start justify-between text-body gap-4">
                <span className="text-theme-muted flex-shrink-0">{t('detail.goal')}</span>
                <span className="text-theme-primary font-medium text-right">{challenge.goal_description}</span>
              </div>
            )}
            {challenge.creator_username && (
              <div className="flex items-center justify-between text-body">
                <span className="text-theme-muted flex items-center gap-2">
                  <UserCircle size={14} />
                  {t('detail.manager')}
                </span>
                <span className="text-theme-primary font-medium">@{challenge.creator_username}</span>
              </div>
            )}
          </div>

          {/* my progress */}
          {challenge.joined && (
            <div className="rounded-card bg-theme-surface p-4">
              <div className="flex items-center justify-between text-label text-theme-muted mb-2">
                <span className="flex items-center gap-1">
                  <CheckCircle size={11} className="text-accent" />
                  {t('detail.myProgress')}
                </span>
                <span className="font-medium text-theme-primary">{t('detail.myUploadCount', { count: challenge.my_upload_count })}</span>
              </div>
              {challenge.completed && (
                <div className="mt-3 flex items-center gap-2 text-label text-accent">
                  <CheckCircle size={13} />
                  <span>{t('detail.titleEarned', { title: challenge.reward_title })}</span>
                </div>
              )}
            </div>
          )}

          {actionError && <p className="text-label text-danger">{actionError}</p>}

          {/* action buttons */}
          {!challenge.joined && challenge.is_active && challenge.is_recruiting !== false && (
            <button
              onClick={() => {
                if (!user) { navigate('/login'); return }
                setActionError('')
                joinMutation.mutate()
              }}
              disabled={joinMutation.isPending}
              className="rounded-card bg-accent py-3 text-body font-semibold text-accent-fg disabled:opacity-50"
            >
              {joinMutation.isPending ? t('detail.joining') : t('detail.joinButton')}
            </button>
          )}
          {!challenge.joined && challenge.is_active && challenge.is_recruiting === false && (
            <div className="rounded-card bg-theme-surface py-3 text-body font-medium text-theme-muted text-center">
              {t('detail.recruitClosed')}
            </div>
          )}

          {challenge.joined && !challenge.completed && (
            <div className="flex gap-2">
              <div className="flex-1 flex items-center justify-center gap-2 rounded-card bg-accent/10 py-3">
                <Target size={15} className="text-accent" />
                <span className="text-body font-semibold text-accent">{t('detail.participating')}</span>
              </div>
              <button
                onClick={() => setShowLeaveConfirm(true)}
                className="flex-1 rounded-card border border-danger/30 py-3 text-body text-danger"
              >
                {t('detail.cancelParticipation')}
              </button>
            </div>
          )}

          {challenge.completed && (
            <div className="flex items-center justify-center gap-2 rounded-card bg-accent/10 py-3">
              <CheckCircle size={15} className="text-accent" />
              <span className="text-body font-medium text-accent">{t('detail.completedChallenge')}</span>
            </div>
          )}

        </div>
      )}

      {/* manager tab */}
      {activeTab === 'manager' && isCreator && (
        <div className="flex flex-col gap-5 pb-6">
          {/* stats */}
          <div className="px-4 grid grid-cols-3 gap-2">
            <div className="rounded-card bg-theme-surface p-3 text-center">
              <Users size={16} className="text-accent mx-auto mb-1" />
              <p className="text-title text-theme-primary">{participants.length}</p>
              <p className="text-label text-theme-muted">{t('manager.statsParticipants')}</p>
            </div>
            <div className="rounded-card bg-theme-surface p-3 text-center">
              <CheckCircle size={16} className="text-accent mx-auto mb-1" />
              <p className="text-title text-theme-primary">{completedCount}</p>
              <p className="text-label text-theme-muted">{t('manager.statsCompleted')}</p>
            </div>
            <div className="rounded-card bg-theme-surface p-3 text-center">
              <TrendingUp size={16} className="text-accent mx-auto mb-1" />
              <p className="text-title text-theme-primary">{avgProgress}%</p>
              <p className="text-label text-theme-muted">{t('manager.statsAvgProgress')}</p>
            </div>
          </div>

          {/* participant list */}
          <div className="px-4">
            <h2 className="text-body font-semibold text-theme-primary mb-2">{t('manager.participantList')}</h2>
            {participantsLoading ? (
              <div className="flex justify-center py-8">
                <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-pill animate-spin" />
              </div>
            ) : participants.length === 0 ? (
              <p className="text-body text-theme-muted py-6 text-center">{t('manager.noParticipants')}</p>
            ) : (
              <div className="flex flex-col gap-2">
                {participants.map((p) => (
                  <div key={p.user_id} className="rounded-card bg-theme-surface px-4 py-3">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-body font-medium text-theme-primary truncate">{p.username}</span>
                        <span className="text-label text-theme-muted flex-shrink-0">{t('manager.certCount', { count: p.post_count })}</span>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <UploadCount count={p.upload_count} total={p.condition_value} />
                        <button
                          onClick={() => completeMutation.mutate(p.user_id)}
                          disabled={completeMutation.isPending}
                          className={`flex items-center gap-1 rounded-pill px-2 py-1 text-label font-medium transition-colors disabled:opacity-50 ${
                            p.completed_at !== null
                              ? 'bg-accent/15 text-accent'
                              : 'bg-theme-surface2 text-theme-muted hover:bg-accent/10 hover:text-accent'
                          }`}
                        >
                          <CircleCheck size={11} strokeWidth={2} />
                          {p.completed_at !== null ? t('manager.completed') : t('manager.markComplete')}
                        </button>
                      </div>
                    </div>
                    <div className="h-1.5 w-full rounded-pill bg-theme-surface2">
                      <div
                        className="h-1.5 rounded-pill bg-accent transition-all"
                        style={{ width: `${p.progress}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* uploaded videos */}
          <div className="px-4">
            <h2 className="text-body font-semibold text-theme-primary mb-2">
              {t('manager.videoList')}
              {challengeVideos.length > 0 && (
                <span className="ml-2 text-label font-normal text-theme-muted">{challengeVideos.length}</span>
              )}
            </h2>
            {videosLoading ? (
              <div className="flex justify-center py-8">
                <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-pill animate-spin" />
              </div>
            ) : challengeVideos.length === 0 ? (
              <p className="text-body text-theme-muted py-6 text-center">{t('manager.noVideos')}</p>
            ) : (
              <div className="grid grid-cols-3 gap-2">
                {challengeVideos.map((v) => (
                  <div
                    key={v.post_id}
                    className="relative aspect-square rounded-card overflow-hidden bg-theme-surface2"
                  >
                    {v.thumbnail_url ? (
                      <img
                        src={v.thumbnail_url}
                        alt=""
                        loading="lazy"
                        decoding="async"
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center">
                        <Play size={18} className="text-theme-muted" />
                      </div>
                    )}
                    <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent px-2 py-1">
                      <p className="text-label text-white truncate">@{v.username}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* close confirm */}
      {showCloseConfirm && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
          onClick={() => setShowCloseConfirm(false)}
        >
          <div
            className="w-full max-w-sm rounded-card bg-theme-surface p-5 flex flex-col gap-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <p className="font-semibold text-theme-primary">{t('detail.closeConfirmTitle')}</p>
              <p className="text-label text-theme-muted mt-1">{t('detail.closeConfirmDesc')}</p>
            </div>
            <div className="flex gap-3">
              <button onClick={() => setShowCloseConfirm(false)} className="flex-1 rounded-card bg-theme-surface2 py-3 text-body text-theme-muted">
                {t('common:cancel')}
              </button>
              <button
                onClick={() => closeMutation.mutate()}
                disabled={closeMutation.isPending}
                className="flex-1 rounded-card bg-warning py-3 text-body font-semibold text-theme-page disabled:opacity-50"
              >
                {closeMutation.isPending ? t('detail.closing') : t('detail.close')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* hard delete confirm */}
      {showDeleteConfirm && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
          onClick={() => setShowDeleteConfirm(false)}
        >
          <div
            className="w-full max-w-sm rounded-card bg-theme-surface p-5 flex flex-col gap-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <p className="font-semibold text-theme-primary">{t('detail.deleteConfirmTitle')}</p>
              <p className="text-label text-theme-muted mt-1">{t('detail.deleteConfirmDesc')}</p>
            </div>
            <div className="flex gap-3">
              <button onClick={() => setShowDeleteConfirm(false)} className="flex-1 rounded-card bg-theme-surface2 py-3 text-body text-theme-muted">
                {t('common:cancel')}
              </button>
              <button
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="flex-1 rounded-card bg-danger py-3 text-body font-semibold text-white disabled:opacity-50"
              >
                {deleteMutation.isPending ? t('detail.deleting') : t('detail.delete')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* leave confirm */}
      {showLeaveConfirm && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
          onClick={() => setShowLeaveConfirm(false)}
        >
          <div
            className="w-full max-w-sm rounded-card bg-theme-surface p-5 flex flex-col gap-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <p className="font-semibold text-theme-primary">{t('detail.leaveConfirmTitle')}</p>
              <p className="text-label text-theme-muted mt-1">
                {t('detail.leaveConfirmDesc')}
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => setShowLeaveConfirm(false)}
                className="flex-1 rounded-card bg-theme-surface2 py-3 text-body text-theme-muted"
              >
                {t('detail.backButton')}
              </button>
              <button
                onClick={() => leaveMutation.mutate()}
                disabled={leaveMutation.isPending}
                className="flex-1 rounded-card bg-danger py-3 text-body font-semibold text-white disabled:opacity-50"
              >
                {leaveMutation.isPending ? t('detail.cancelling') : t('detail.cancelButton')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
