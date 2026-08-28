import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowLeft } from 'lucide-react'
import client from '../api/client'
import type {
  Survey,
  SurveyQuestion,
  SurveyResponse,
  SurveyAggregate,
  SurveyAggregateScaleValue,
} from '../api/types'
import { useAuthStore } from '../store/auth'

interface ResponsesData {
  count: number
  responses: SurveyResponse[]
  aggregate: SurveyAggregate
}

function isScaleAgg(v: unknown): v is SurveyAggregateScaleValue {
  return typeof v === 'object' && v !== null && 'avg' in v
}

function AggregateView({ question, agg }: { question: SurveyQuestion; agg: unknown }) {
  if (question.type === 'scale' && isScaleAgg(agg)) {
    const entries = Object.entries(agg.distribution).sort((a, b) => Number(a[0]) - Number(b[0]))
    const maxVal = Math.max(...Object.values(agg.distribution), 1)
    return (
      <div className="space-y-3">
        <div className="flex gap-4 text-label text-theme-muted">
          <span>
            평균 <strong className="text-theme-primary">{agg.avg.toFixed(2)}</strong>
          </span>
          <span>
            응답 <strong className="text-theme-primary">{agg.count}</strong>명
          </span>
        </div>
        <div className="space-y-2">
          {entries.map(([val, cnt]) => (
            <div key={val} className="flex items-center gap-2">
              <span className="w-6 shrink-0 text-center text-label text-theme-muted">{val}</span>
              <div className="flex-1 overflow-hidden rounded-pill bg-theme-surface2 h-3">
                <div
                  className="h-full rounded-pill bg-accent transition-all"
                  style={{ width: `${(cnt / maxVal) * 100}%` }}
                />
              </div>
              <span className="w-6 shrink-0 text-right text-label text-theme-muted">{cnt}</span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if ((question.type === 'single' || question.type === 'multi') && !isScaleAgg(agg)) {
    const optAgg = agg as Record<string, number>
    const entries = Object.entries(optAgg)
    const maxVal = Math.max(...Object.values(optAgg), 1)
    return (
      <div className="space-y-2">
        {entries.map(([opt, cnt]) => (
          <div key={opt} className="flex items-center gap-2">
            <span className="w-28 shrink-0 truncate text-right text-label text-theme-muted">{opt}</span>
            <div className="flex-1 overflow-hidden rounded-pill bg-theme-surface2 h-3">
              <div
                className="h-full rounded-pill bg-accent transition-all"
                style={{ width: `${(cnt / maxVal) * 100}%` }}
              />
            </div>
            <span className="w-6 shrink-0 text-right text-label text-theme-muted">{cnt}</span>
          </div>
        ))}
      </div>
    )
  }

  return null
}

function formatIndividualAnswer(value: unknown): string {
  if (value === undefined || value === null || value === '') return '-'
  if (Array.isArray(value)) return (value as string[]).join(', ')
  return String(value)
}

export default function AdminSurveyResponsesPage() {
  const { t } = useTranslation('survey')
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const isAdmin = user?.is_admin ?? false

  const { data: survey, isLoading: surveyLoading } = useQuery<Survey>({
    queryKey: ['admin-survey-for-responses', id],
    queryFn: async () => {
      const res = await client.get<{ data: { survey: Survey } }>(`/surveys/${id}`)
      return res.data.data.survey
    },
    enabled: isAdmin && !!id,
  })

  const { data: respData, isLoading: respLoading, isError: respError } = useQuery<ResponsesData>({
    queryKey: ['admin-survey-responses', id],
    queryFn: async () => {
      const res = await client.get<{ data: ResponsesData }>(`/surveys/${id}/responses`)
      return res.data.data
    },
    enabled: isAdmin && !!id,
  })

  if (!isAdmin) {
    return (
      <div className="flex h-[100dvh] items-center justify-center bg-theme-page">
        <p className="text-body text-theme-muted">{t('admin.adminOnly')}</p>
      </div>
    )
  }

  const isLoading = surveyLoading || respLoading

  return (
    <div className="flex h-[100dvh] flex-col bg-theme-page">
      <div className="flex-none px-4 pt-6 pb-3 space-y-1">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/admin/surveys')}
            className="flex h-8 w-8 items-center justify-center rounded-pill hover:bg-theme-surface transition-colors"
          >
            <ArrowLeft size={18} strokeWidth={2} className="text-theme-primary" />
          </button>
          <div>
            <h1 className="text-display text-theme-primary">{t('admin.responses.title')}</h1>
            {survey && <p className="text-label text-theme-muted truncate">{survey.title}</p>}
          </div>
        </div>
        {respData && (
          <p className="pl-11 text-body font-semibold text-accent">
            {t('admin.responses.totalCount', { count: respData.count })}
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-24 space-y-6">
        {isLoading && (
          <p className="py-10 text-center text-body text-theme-muted">{t('admin.responses.loading')}</p>
        )}
        {!isLoading && respError && (
          <p className="py-10 text-center text-body text-danger">{t('admin.responses.loadFailed')}</p>
        )}

        {!isLoading && respData && survey && (
          <>
            {respData.count === 0 ? (
              <p className="py-10 text-center text-body text-theme-muted">
                {t('admin.responses.noResponses')}
              </p>
            ) : (
              <>
                <div className="space-y-3">
                  <p className="text-label font-semibold uppercase tracking-wider text-theme-muted">
                    {t('admin.responses.aggregateLabel')}
                  </p>
                  {survey.questions.map((q) => {
                    if (q.type === 'text') return null
                    const agg = respData.aggregate[q.id]
                    if (!agg) return null
                    return (
                      <div key={q.id} className="rounded-card bg-theme-surface p-4 space-y-3">
                        <p className="text-body font-semibold text-theme-primary">{q.title}</p>
                        <AggregateView question={q} agg={agg} />
                      </div>
                    )
                  })}
                </div>

                <div className="space-y-3">
                  <p className="text-label font-semibold uppercase tracking-wider text-theme-muted">
                    {t('admin.responses.individualLabel')}
                  </p>
                  {respData.responses.map((r, ri) => (
                    <div key={r.id} className="rounded-card bg-theme-surface p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <p className="text-label font-semibold text-theme-muted">
                          {t('admin.responses.responseNumber', { n: ri + 1 })}
                        </p>
                        <p className="text-label text-theme-muted">
                          {new Date(r.created_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}
                        </p>
                      </div>
                      <div className="space-y-2">
                        {survey.questions.map((q) => {
                          const ans = r.answers[q.id]
                          if (ans === undefined || ans === null || ans === '') {
                            if (!q.required) return null
                          }
                          return (
                            <div key={q.id}>
                              <p className="text-label text-theme-muted">{q.title}</p>
                              <p className="text-body text-theme-primary break-words">
                                {formatIndividualAnswer(ans)}
                              </p>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
