import { useRef, useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Trophy, ImagePlus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import { getApiErrorMessage } from '../api/errors'
import { useAuthStore } from '../store/auth'
import type { Challenge } from '../api/types'
import LoadingScreen from '../components/LoadingScreen'

export default function ChallengeEditPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const { t } = useTranslation('challenge')

  const [form, setForm] = useState({
    title: '',
    description: '',
    reward_title: '',
    goal_description: '',
    recruit_start: '',
    recruit_end: '',
    start_date: '',
    end_date: '',
    max_participants: '',
  })
  const [error, setError] = useState('')
  const [initialized, setInitialized] = useState(false)

  const [imageSrc, setImageSrc] = useState<string | null>(null)
  const [isExistingImage, setIsExistingImage] = useState(false)
  const imgRef = useRef<HTMLImageElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: challenge, isLoading, isError } = useQuery<Challenge>({
    queryKey: ['challenge', id],
    queryFn: async () => {
      const res = await client.get<{ data: { challenge: Challenge } }>(`/challenges/${id}`)
      return res.data.data.challenge
    },
    enabled: !!id,
  })

  useEffect(() => {
    if (!challenge || initialized) return
    const start = challenge.start_date ? challenge.start_date.slice(0, 10) : ''
    const end = challenge.end_date ? challenge.end_date.slice(0, 10) : ''
    setForm({
      title: challenge.title ?? '',
      description: challenge.description ?? '',
      reward_title: challenge.reward_title ?? '',
      goal_description: challenge.goal_description ?? '',
      recruit_start: challenge.recruit_start ? challenge.recruit_start.slice(0, 10) : '',
      recruit_end: challenge.recruit_end ? challenge.recruit_end.slice(0, 10) : '',
      start_date: start,
      end_date: end,
      max_participants: challenge.max_participants ? String(challenge.max_participants) : '',
    })
    if (challenge.image_url) {
      setImageSrc(challenge.image_url)
      setIsExistingImage(true)
    }
    setInitialized(true)
  }, [challenge, initialized])

  const isCreator = !!user && !!challenge && (user.id === challenge.creator_id || user.is_admin)

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    setImageSrc(URL.createObjectURL(f))
    setIsExistingImage(false)
  }

  async function cropAndUpload(): Promise<void> {
    if (isExistingImage) return
    const img = imgRef.current
    if (!img || !imageSrc) return
    const size = Math.min(img.naturalWidth, img.naturalHeight)
    const srcX = (img.naturalWidth - size) / 2
    const srcY = (img.naturalHeight - size) / 2
    const canvas = document.createElement('canvas')
    canvas.width = 400
    canvas.height = 400
    const ctx = canvas.getContext('2d')!
    ctx.drawImage(img, srcX, srcY, size, size, 0, 0, 400, 400)
    await new Promise<void>((resolve) => {
      canvas.toBlob(async (blob) => {
        if (!blob) { resolve(); return }
        const fd = new FormData()
        fd.append('file', blob, 'challenge.jpg')
        try {
          await client.post(`/challenges/${id}/image`, fd, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
        } catch {
          // image upload failure is non-blocking
        }
        resolve()
      }, 'image/jpeg', 0.82)
    })
  }

  const mutation = useMutation({
    mutationFn: async () => {
      await client.patch(`/challenges/${id}`, {
        title: form.title,
        description: form.description,
        reward_title: form.reward_title,
        goal_description: form.goal_description || null,
        recruit_start: form.recruit_start || null,
        recruit_end: form.recruit_end || null,
        start_date: form.start_date,
        end_date: form.end_date,
        max_participants: form.max_participants ? Number(form.max_participants) : null,
        categories: [],
      })
      if (imageSrc && !isExistingImage) await cropAndUpload()
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['challenge', id] }).catch(() => undefined)
      qc.invalidateQueries({ queryKey: ['challenges'] }).catch(() => undefined)
      qc.invalidateQueries({ queryKey: ['my-challenges'] }).catch(() => undefined)
      navigate(`/challenges/${id}`)
    },
    onError: (e: unknown) => {
      setError(getApiErrorMessage(e, t('edit.errorDefault')))
    },
  })

  if (isLoading) return <LoadingScreen />

  if (isError || !challenge) {
    return (
      <div className="flex h-[100dvh] flex-col items-center justify-center gap-2 bg-theme-page lg:max-w-2xl lg:mx-auto">
        <p className="text-body text-theme-muted">{t('edit.notFound')}</p>
        <button onClick={() => navigate('/challenges')} className="text-label text-accent">
          {t('edit.backToList')}
        </button>
      </div>
    )
  }

  if (!isCreator) {
    return (
      <div className="flex h-[100dvh] flex-col items-center justify-center gap-3 bg-theme-page lg:max-w-2xl lg:mx-auto">
        <p className="text-theme-muted text-body">{t('edit.noPermission')}</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-[100dvh] overflow-y-auto bg-theme-page pb-nav-safe lg:max-w-2xl lg:mx-auto">
      {/* header */}
      <div className="px-4 pt-5 pb-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="text-theme-muted">
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-title text-theme-primary">{t('edit.title')}</h1>
      </div>

      <div className="px-4 flex flex-col gap-4">

        {/* image */}
        <div className="flex justify-center">
          <label
            htmlFor="challenge-edit-image-input"
            className="relative h-24 w-24 rounded-pill overflow-hidden bg-theme-surface2 ring-2 ring-theme-border group cursor-pointer"
          >
            {imageSrc ? (
              <img
                ref={imgRef}
                src={imageSrc}
                alt=""
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full gap-1">
                <ImagePlus size={20} strokeWidth={1.5} className="text-theme-muted" />
                <span className="text-label text-theme-muted">{t('edit.imageLabel')}</span>
              </div>
            )}
            <div className="absolute inset-0 bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 group-active:opacity-100 transition-opacity">
              <ImagePlus size={18} className="text-white" />
            </div>
          </label>
          <input
            id="challenge-edit-image-input"
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={onFileChange}
          />
        </div>

        {/* title */}
        <div>
          <label className="block text-label text-theme-muted mb-1">{t('create.challengeTitle')}</label>
          <input
            value={form.title}
            onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            placeholder={t('create.titlePlaceholder')}
            className="w-full rounded-card bg-theme-surface px-3 py-3 text-body text-theme-primary placeholder-theme-muted outline-none"
          />
        </div>

        {/* description */}
        <div>
          <label className="block text-label text-theme-muted mb-1">{t('create.description')} <span className="text-danger">*</span></label>
          <textarea
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            placeholder={t('create.descriptionPlaceholder')}
            rows={3}
            className="w-full rounded-card bg-theme-surface px-3 py-3 text-body text-theme-primary placeholder-theme-muted outline-none resize-none"
          />
        </div>

        {/* reward title */}
        <div>
          <label className="block text-label text-theme-muted mb-1">{t('create.rewardTitle')}</label>
          <div className="flex items-center gap-2 rounded-card bg-theme-surface px-3 py-3">
            <Trophy size={14} className="text-accent flex-shrink-0" />
            <input
              value={form.reward_title}
              onChange={(e) => setForm((f) => ({ ...f, reward_title: e.target.value }))}
              placeholder={t('create.rewardPlaceholder')}
              className="flex-1 bg-transparent text-body text-theme-primary placeholder-theme-muted outline-none"
            />
          </div>
        </div>

        {/* goal */}
        <div>
          <label className="block text-label text-theme-muted mb-1">{t('create.goal')} <span className="text-theme-muted">{t('create.goalOptional')}</span></label>
          <input
            value={form.goal_description}
            onChange={(e) => setForm((f) => ({ ...f, goal_description: e.target.value }))}
            placeholder={t('create.goalPlaceholder')}
            className="w-full rounded-card bg-theme-surface px-3 py-3 text-body text-theme-primary placeholder-theme-muted outline-none"
          />
        </div>

        {/* recruit period */}
        <div>
          <label className="block text-label text-theme-muted mb-1">{t('create.recruitPeriod')} <span className="text-theme-muted">{t('create.recruitOptional')}</span></label>
          <div className="grid grid-cols-2 gap-3">
            <input
              type="date"
              value={form.recruit_start}
              onChange={(e) => setForm((f) => ({ ...f, recruit_start: e.target.value }))}
              className="w-full rounded-card bg-theme-surface px-3 py-3 text-body text-theme-primary outline-none"
            />
            <input
              type="date"
              value={form.recruit_end}
              onChange={(e) => setForm((f) => ({ ...f, recruit_end: e.target.value }))}
              className="w-full rounded-card bg-theme-surface px-3 py-3 text-body text-theme-primary outline-none"
            />
          </div>
        </div>

        {/* challenge period */}
        <div>
          <label className="block text-label text-theme-muted mb-1">{t('create.challengePeriod')}</label>
          <div className="grid grid-cols-2 gap-3">
            <input
              type="date"
              value={form.start_date}
              onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))}
              className="w-full rounded-card bg-theme-surface px-3 py-3 text-body text-theme-primary outline-none"
            />
            <input
              type="date"
              value={form.end_date}
              onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))}
              className="w-full rounded-card bg-theme-surface px-3 py-3 text-body text-theme-primary outline-none"
            />
          </div>
        </div>

        {/* max participants */}
        <div>
          <label className="block text-label text-theme-muted mb-1">{t('create.maxParticipants')} <span className="text-theme-muted">{t('create.maxParticipantsOptional')}</span></label>
          <input
            type="number"
            min={1}
            value={form.max_participants}
            onChange={(e) => setForm((f) => ({ ...f, max_participants: e.target.value }))}
            placeholder={t('create.maxParticipantsPlaceholder')}
            className="w-full rounded-card bg-theme-surface px-3 py-3 text-body text-theme-primary placeholder-theme-muted outline-none"
          />
        </div>

        {error && <p className="text-label text-danger">{error}</p>}

        {/* submit */}
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending || !form.title || !form.description || !form.reward_title || !form.start_date || !form.end_date}
          className="mt-6 mb-4 rounded-card bg-accent py-4 text-body font-semibold text-accent-fg disabled:opacity-50"
        >
          {mutation.isPending ? t('edit.submitting') : t('edit.submitButton')}
        </button>
      </div>
    </div>
  )
}
