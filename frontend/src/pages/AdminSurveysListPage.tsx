import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Plus, Pencil, BarChart2, X, Trash2, Link2 } from 'lucide-react'
import toast from 'react-hot-toast'
import client from '../api/client'
import type { SurveyListItem } from '../api/types'
import { useAuthStore } from '../store/auth'

interface SurveysListResponse {
  surveys: SurveyListItem[]
}

export default function AdminSurveysListPage() {
  const { t } = useTranslation('survey')
  const navigate = useNavigate()
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const isAdmin = user?.is_admin ?? false

  const [closeConfirmId, setCloseConfirmId] = useState<number | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)

  const { data, isLoading, isError } = useQuery<SurveysListResponse>({
    queryKey: ['admin-surveys'],
    queryFn: async () => {
      const res = await client.get<{ data: SurveysListResponse }>('/surveys')
      return res.data.data
    },
    enabled: isAdmin,
  })

  const closeSurvey = useMutation({
    mutationFn: (id: number) => client.post(`/surveys/${id}/close`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-surveys'] })
      toast.success(t('admin.closeSuccess'))
      setCloseConfirmId(null)
    },
    onError: () => {
      toast.error(t('admin.closeFailed'))
    },
  })

  const deleteSurvey = useMutation({
    mutationFn: (id: number) => client.delete(`/surveys/${id}`),
    onSuccess: (_, id) => {
      qc.setQueryData<SurveysListResponse>(['admin-surveys'], (old) =>
        old ? { surveys: old.surveys.filter((s) => s.id !== id) } : old,
      )
      toast.success(t('admin.deleteSuccess'))
      setDeleteConfirmId(null)
    },
    onError: () => {
      toast.error(t('admin.deleteFailed'))
    },
  })

  const handleCopyLink = (slug: string) => {
    const url = `${window.location.origin}/survey/${slug}`
    navigator.clipboard.writeText(url).then(() => {
      toast.success(t('admin.linkCopied'))
    })
  }

  if (!isAdmin) {
    return (
      <div className="flex h-[100dvh] flex-col items-center justify-center bg-theme-page">
        <p className="text-body text-theme-muted">{t('admin.adminOnly')}</p>
      </div>
    )
  }

  const surveys = data?.surveys ?? []

  return (
    <div className="flex h-[100dvh] flex-col bg-theme-page">
      <div className="flex-none px-4 pt-6 pb-3 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/admin')}
              className="flex h-8 w-8 items-center justify-center rounded-pill hover:bg-theme-surface transition-colors"
            >
              <ArrowLeft size={18} strokeWidth={2} className="text-theme-primary" />
            </button>
            <h1 className="text-display text-theme-primary">{t('admin.title')}</h1>
          </div>
          <button
            onClick={() => navigate('/admin/surveys/new')}
            className="flex items-center gap-2 rounded-card bg-accent px-3 py-2 text-label font-semibold text-accent-fg"
          >
            <Plus size={14} />
            {t('admin.newSurvey')}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-24 space-y-3">
        {isLoading && (
          <p className="py-10 text-center text-body text-theme-muted">{t('admin.loading')}</p>
        )}
        {!isLoading && isError && (
          <p className="py-10 text-center text-body text-danger">{t('admin.loadFailed')}</p>
        )}
        {!isLoading && !isError && surveys.length === 0 && (
          <p className="py-10 text-center text-body text-theme-muted">{t('admin.noSurveys')}</p>
        )}

        {surveys.map((s) => (
          <div key={s.id} className="rounded-card bg-theme-surface p-4 space-y-3">
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-theme-primary truncate">{s.title}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-label text-theme-muted">
                  <span
                    className={`rounded-pill px-2 py-1 text-label font-semibold ${
                      s.is_active
                        ? 'bg-success/15 text-success'
                        : 'bg-theme-surface2 text-theme-muted'
                    }`}
                  >
                    {s.is_active ? t('admin.active') : t('admin.inactive')}
                  </span>
                  <span>{t('admin.colResponses')}: {s.response_count}</span>
                  {s.closes_at && (
                    <span>
                      {t('admin.colClosesAt')}: {new Date(s.closes_at).toLocaleDateString('ko-KR')}
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => navigate(`/admin/surveys/${s.id}/edit`)}
                className="flex items-center gap-1 rounded-card bg-theme-surface2 px-3 py-2 text-label font-semibold text-theme-muted hover:text-theme-primary"
              >
                <Pencil size={11} />
                {t('admin.editButton')}
              </button>
              <button
                onClick={() => navigate(`/admin/surveys/${s.id}/responses`)}
                className="flex items-center gap-1 rounded-card bg-theme-surface2 px-3 py-2 text-label font-semibold text-theme-muted hover:text-theme-primary"
              >
                <BarChart2 size={11} />
                {t('admin.responsesButton')}
              </button>
              {s.is_open && (
                <button
                  onClick={() => setCloseConfirmId(s.id)}
                  className="flex items-center gap-1 rounded-card bg-theme-surface2 px-3 py-2 text-label font-semibold text-theme-muted hover:text-theme-primary"
                >
                  <X size={11} />
                  {t('admin.closeButton')}
                </button>
              )}
              <button
                onClick={() => handleCopyLink(s.slug)}
                className="flex items-center gap-1 rounded-card bg-theme-surface2 px-3 py-2 text-label font-semibold text-theme-muted hover:text-theme-primary"
              >
                <Link2 size={11} />
                {t('admin.copyLinkButton')}
              </button>
              <button
                onClick={() => setDeleteConfirmId(s.id)}
                className="flex items-center gap-1 rounded-card bg-danger px-3 py-2 text-label font-semibold text-white"
              >
                <Trash2 size={11} />
                {t('admin.deleteButton')}
              </button>
            </div>
          </div>
        ))}
      </div>

      {closeConfirmId !== null && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4"
          onClick={() => setCloseConfirmId(null)}
        >
          <div
            className="w-full max-w-sm rounded-card bg-theme-surface px-6 pt-5 pb-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="mb-1 text-title text-theme-primary">{t('admin.closeConfirmTitle')}</p>
            <p className="mb-5 text-body text-theme-muted">{t('admin.closeConfirmMessage')}</p>
            <div className="flex gap-3">
              <button
                onClick={() => setCloseConfirmId(null)}
                className="flex-1 rounded-card bg-theme-surface2 py-3 text-body text-theme-muted"
              >
                {t('admin.cancel')}
              </button>
              <button
                onClick={() => closeSurvey.mutate(closeConfirmId)}
                disabled={closeSurvey.isPending}
                className="flex-1 rounded-card bg-accent py-3 text-body font-semibold text-accent-fg disabled:opacity-60"
              >
                {t('admin.confirm')}
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteConfirmId !== null && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/50 p-4"
          onClick={() => setDeleteConfirmId(null)}
        >
          <div
            className="w-full max-w-sm rounded-card bg-theme-surface px-6 pt-5 pb-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="mb-1 text-title text-theme-primary">{t('admin.deleteConfirmTitle')}</p>
            <p className="mb-5 text-body text-theme-muted">{t('admin.deleteConfirmMessage')}</p>
            <div className="flex gap-3">
              <button
                onClick={() => setDeleteConfirmId(null)}
                className="flex-1 rounded-card bg-theme-surface2 py-3 text-body text-theme-muted"
              >
                {t('admin.cancel')}
              </button>
              <button
                onClick={() => deleteSurvey.mutate(deleteConfirmId)}
                disabled={deleteSurvey.isPending}
                className="flex-1 rounded-card bg-danger py-3 text-body font-semibold text-white disabled:opacity-60"
              >
                {t('admin.deleteButton')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
