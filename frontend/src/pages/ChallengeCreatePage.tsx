import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Trophy, ImagePlus, Move } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import client from '../api/client'
import { getApiErrorMessage } from '../api/errors'
import { useAuthStore } from '../store/auth'

const CROP_INSET = 24

export default function ChallengeCreatePage() {
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

  const [imageSrc, setImageSrc] = useState<string | null>(null)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [imgReady, setImgReady] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const dragRef = useRef({ startX: 0, startY: 0, ox: 0, oy: 0 })
  const previewRef = useRef<HTMLDivElement>(null)
  const imgRef = useRef<HTMLImageElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const renderedRef = useRef({ w: 0, h: 0 })

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    setImageSrc(URL.createObjectURL(f))
    setOffset({ x: 0, y: 0 })
    setImgReady(false)
    renderedRef.current = { w: 0, h: 0 }
  }

  function onImageLoad(e: React.SyntheticEvent<HTMLImageElement>) {
    const img = e.currentTarget
    const container = previewRef.current
    if (!container) return
    const containerSize = container.getBoundingClientRect().width
    if (!containerSize) return
    const cropSize = containerSize - CROP_INSET * 2
    const scale = Math.max(cropSize / img.naturalWidth, cropSize / img.naturalHeight)
    const w = img.naturalWidth * scale
    const h = img.naturalHeight * scale
    renderedRef.current = { w, h }
    setOffset({
      x: CROP_INSET + (cropSize - w) / 2,
      y: CROP_INSET + (cropSize - h) / 2,
    })
    setImgReady(true)
  }

  function onPointerDown(e: React.PointerEvent) {
    e.currentTarget.setPointerCapture(e.pointerId)
    setIsDragging(true)
    dragRef.current = { startX: e.clientX, startY: e.clientY, ox: offset.x, oy: offset.y }
  }

  function onPointerMove(e: React.PointerEvent) {
    if (!isDragging) return
    const container = previewRef.current
    if (!container) return
    const { w, h } = renderedRef.current
    if (!w || !h) return
    const { startX, startY, ox, oy } = dragRef.current
    const containerSize = container.getBoundingClientRect().width
    const cropSize = containerSize - CROP_INSET * 2
    const newX = Math.min(CROP_INSET, Math.max(CROP_INSET + cropSize - w, ox + (e.clientX - startX)))
    const newY = Math.min(CROP_INSET, Math.max(CROP_INSET + cropSize - h, oy + (e.clientY - startY)))
    setOffset({ x: newX, y: newY })
  }

  function onPointerUp() {
    setIsDragging(false)
  }

  async function cropAndUpload(challengeId: number): Promise<void> {
    const img = imgRef.current
    const container = previewRef.current
    if (!img || !container || !imageSrc) return
    const containerSize = container.getBoundingClientRect().width
    const cropSize = containerSize - CROP_INSET * 2
    const scale = Math.max(cropSize / img.naturalWidth, cropSize / img.naturalHeight)
    const srcX = (CROP_INSET - offset.x) / scale
    const srcY = (CROP_INSET - offset.y) / scale
    const srcSize = cropSize / scale

    const canvas = document.createElement('canvas')
    canvas.width = 400
    canvas.height = 400
    const ctx = canvas.getContext('2d')!
    ctx.drawImage(img, srcX, srcY, srcSize, srcSize, 0, 0, 400, 400)

    await new Promise<void>((resolve) => {
      canvas.toBlob(async (blob) => {
        if (!blob) { resolve(); return }
        const fd = new FormData()
        fd.append('file', blob, 'challenge.jpg')
        try {
          await client.post(`/challenges/${challengeId}/image`, fd, {
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
      const res = await client.post('/challenges', {
        title: form.title,
        description: form.description,
        reward_title: form.reward_title,
        goal_description: form.goal_description || null,
        condition_value: 30,
        recruit_start: form.recruit_start || null,
        recruit_end: form.recruit_end || null,
        start_date: form.start_date,
        end_date: form.end_date,
        max_participants: form.max_participants ? Number(form.max_participants) : null,
        categories: [],
      })
      const challengeId = res.data.data.challenge.id
      if (imageSrc) await cropAndUpload(challengeId)
      return res
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['challenges'] }).catch(() => undefined)
      qc.invalidateQueries({ queryKey: ['my-challenges'] }).catch(() => undefined)
      navigate('/challenges')
    },
    onError: (e: unknown) => {
      setError(getApiErrorMessage(e, t('create.errorDefault')))
    },
  })

  if (!user) {
    return (
      <div className="flex h-[100dvh] flex-col items-center justify-center gap-3 bg-theme-page lg:max-w-2xl lg:mx-auto">
        <p className="text-theme-muted text-body">{t('create.loginRequired')}</p>
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
        <h1 className="text-title text-theme-primary">{t('create.title')}</h1>
      </div>

      <div className="px-4 flex flex-col gap-4">

        {/* image upload */}
        <div>
          <label className="block text-label text-theme-muted mb-2">{t('create.image')}</label>
          {imageSrc ? (
            <div className="flex flex-col gap-2">
              <div
                ref={previewRef}
                className="relative w-full aspect-square overflow-hidden rounded-card bg-black cursor-grab active:cursor-grabbing touch-none"
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
                onPointerCancel={onPointerUp}
              >
                <img
                  ref={imgRef}
                  src={imageSrc}
                  alt=""
                  draggable={false}
                  onLoad={onImageLoad}
                  className={`absolute max-w-none select-none transition-opacity duration-200 ${imgReady ? 'opacity-100' : 'opacity-0'}`}
                  style={{
                    width: renderedRef.current.w ? `${renderedRef.current.w}px` : '100%',
                    height: renderedRef.current.h ? `${renderedRef.current.h}px` : 'auto',
                    transform: `translate(${offset.x}px, ${offset.y}px)`,
                  }}
                />

                {/* crop overlay - top */}
                <div className="absolute top-0 left-0 right-0 bg-black/50 pointer-events-none" style={{ height: CROP_INSET }} />
                <div className="absolute bottom-0 left-0 right-0 bg-black/50 pointer-events-none" style={{ height: CROP_INSET }} />
                <div className="absolute bg-black/50 pointer-events-none" style={{ top: CROP_INSET, bottom: CROP_INSET, left: 0, width: CROP_INSET }} />
                <div className="absolute bg-black/50 pointer-events-none" style={{ top: CROP_INSET, bottom: CROP_INSET, right: 0, width: CROP_INSET }} />

                {/* crop frame border */}
                <div
                  className="absolute border border-white/60 pointer-events-none"
                  style={{ inset: CROP_INSET }}
                />

                {/* drag hint */}
                <div
                  className="absolute pointer-events-none flex items-center justify-center"
                  style={{ inset: CROP_INSET }}
                >
                  <div className="flex items-center gap-2 rounded-pill bg-black/40 px-3 py-1">
                    <Move size={12} className="text-white/80" />
                    <span className="text-label text-white/80">{t('create.dragHint')}</span>
                  </div>
                </div>
              </div>
              <label
                htmlFor="challenge-image-input"
                className="text-label text-theme-muted text-center py-1 cursor-pointer"
              >
                {t('create.changeImage')}
              </label>
            </div>
          ) : (
            <label
              htmlFor="challenge-image-input"
              className="w-full aspect-square rounded-card bg-theme-surface flex flex-col items-center justify-center gap-2 text-theme-muted border-2 border-dashed border-theme-border cursor-pointer"
            >
              <ImagePlus size={28} strokeWidth={1.5} />
              <span className="text-label">{t('create.selectImage')}</span>
            </label>
          )}
          <input
            id="challenge-image-input"
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
          {mutation.isPending ? t('create.submitting') : t('create.submitButton')}
        </button>
      </div>
    </div>
  )
}
