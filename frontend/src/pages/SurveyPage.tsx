import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { CheckCircle, XCircle } from 'lucide-react'
import client from '../api/client'
import type { Survey, SurveyQuestion } from '../api/types'
import LoadingScreen from '../components/LoadingScreen'

type Step = 'intro' | 'form' | 'review' | 'done'

function formatAnswer(_q: SurveyQuestion, value: unknown): string {
  if (value === undefined || value === null || value === '') return '-'
  if (Array.isArray(value)) {
    if (value.length === 0) return '-'
    return (value as string[]).join(', ')
  }
  return String(value)
}

export default function SurveyPage() {
  const { t } = useTranslation('survey')
  const { slug } = useParams<{ slug: string }>()

  const storageKey = `sh_survey_done_${slug ?? ''}`
  const [alreadyDone] = useState<boolean>(() => localStorage.getItem(storageKey) === 'true')

  const [step, setStep] = useState<Step>('intro')
  const [answers, setAnswers] = useState<Record<string, unknown>>({})
  const [formError, setFormError] = useState<string | null>(null)

  const { data: survey, isLoading, isError } = useQuery<Survey>({
    queryKey: ['survey-public', slug],
    queryFn: async () => {
      const res = await client.get<{ data: { survey: Survey } }>(`/surveys/public/${slug}`)
      return res.data.data.survey
    },
    enabled: !!slug,
  })

  const submit = useMutation({
    mutationFn: async (answerData: Record<string, unknown>) => {
      const res = await client.post<{ data: { submitted: boolean } }>(
        `/surveys/public/${slug}/responses`,
        { answers: answerData },
      )
      return res.data.data
    },
    onSuccess: () => {
      localStorage.setItem(storageKey, 'true')
      setStep('done')
    },
  })

  const validateForm = (): boolean => {
    if (!survey) return false
    for (const q of survey.questions) {
      if (!q.required) continue
      const ans = answers[q.id]
      if (ans === undefined || ans === null || ans === '') return false
      if (Array.isArray(ans) && ans.length === 0) return false
    }
    return true
  }

  const handleNext = () => {
    if (!validateForm()) {
      setFormError(t('form.requiredError'))
      return
    }
    setFormError(null)
    setStep('review')
  }

  const renderQuestionInput = (q: SurveyQuestion) => {
    switch (q.type) {
      case 'scale': {
        const min = q.scale_min ?? 1
        const max = q.scale_max ?? 5
        const current = (answers[q.id] as number | undefined)
        return (
          <div className="space-y-3">
            <div className="flex items-center gap-4">
              <input
                type="range"
                min={min}
                max={max}
                step={1}
                value={current ?? min}
                onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: Number(e.target.value) }))}
                className="h-2 w-full cursor-pointer appearance-none rounded-pill bg-theme-surface2 accent-accent"
              />
              <span className="w-8 shrink-0 text-center text-title text-accent">
                {current ?? <span className="text-theme-muted text-body">—</span>}
              </span>
            </div>
            {(q.scale_min_label || q.scale_max_label) && (
              <div className="flex justify-between text-label text-theme-muted">
                <span>{min} · {q.scale_min_label}</span>
                <span>{q.scale_max_label} · {max}</span>
              </div>
            )}
          </div>
        )
      }
      case 'single': {
        return (
          <div className="space-y-2">
            {(q.options ?? []).map((opt) => (
              <label
                key={opt}
                className="flex cursor-pointer items-center gap-3 rounded-card bg-theme-surface px-4 py-3 transition-colors hover:bg-theme-surface2"
              >
                <input
                  type="radio"
                  name={q.id}
                  value={opt}
                  checked={answers[q.id] === opt}
                  onChange={() => setAnswers((prev) => ({ ...prev, [q.id]: opt }))}
                  className="accent-accent"
                />
                <span className="text-body text-theme-primary">{opt}</span>
              </label>
            ))}
          </div>
        )
      }
      case 'multi': {
        const currentMulti = (answers[q.id] as string[] | undefined) ?? []
        return (
          <div className="space-y-2">
            {(q.options ?? []).map((opt) => (
              <label
                key={opt}
                className="flex cursor-pointer items-center gap-3 rounded-card bg-theme-surface px-4 py-3 transition-colors hover:bg-theme-surface2"
              >
                <input
                  type="checkbox"
                  value={opt}
                  checked={currentMulti.includes(opt)}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setAnswers((prev) => ({ ...prev, [q.id]: [...currentMulti, opt] }))
                    } else {
                      setAnswers((prev) => ({ ...prev, [q.id]: currentMulti.filter((x) => x !== opt) }))
                    }
                  }}
                  className="accent-accent"
                />
                <span className="text-body text-theme-primary">{opt}</span>
              </label>
            ))}
          </div>
        )
      }
      case 'text': {
        return (
          <textarea
            value={(answers[q.id] as string | undefined) ?? ''}
            onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
            placeholder={q.required ? undefined : t('form.optionalPlaceholder')}
            rows={4}
            className="w-full resize-none rounded-card bg-theme-surface px-4 py-3 text-body text-theme-primary placeholder:text-theme-muted outline-none"
          />
        )
      }
      default:
        return null
    }
  }

  if (isLoading) return <LoadingScreen />

  if (isError) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-theme-page">
        <p className="text-body text-danger">{t('error.load')}</p>
      </div>
    )
  }

  if (!survey) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-theme-page">
        <p className="text-body text-theme-muted">{t('notFound')}</p>
      </div>
    )
  }

  if (alreadyDone) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-theme-page px-4">
        <div className="w-full max-w-sm space-y-4 text-center">
          <CheckCircle size={48} className="mx-auto text-accent" />
          <h1 className="text-display text-theme-primary">{t('alreadyDone.title')}</h1>
          <p className="text-body text-theme-muted">{t('alreadyDone.message')}</p>
        </div>
      </div>
    )
  }

  if (!survey.is_active) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-theme-page px-4">
        <div className="w-full max-w-sm space-y-4 text-center">
          <XCircle size={48} className="mx-auto text-theme-muted" />
          <h1 className="text-display text-theme-primary">{t('closed.title')}</h1>
          <p className="text-body text-theme-muted">{t('closed.message')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-[100dvh] bg-theme-page px-4 py-12">
      <div className="mx-auto w-full max-w-lg">
        {step === 'intro' && (
          <div className="space-y-6">
            <div className="space-y-3">
              <h1 className="text-display text-theme-primary">{survey.title}</h1>
              {survey.description && (
                <p className="text-body text-theme-muted leading-relaxed">{survey.description}</p>
              )}
            </div>
            <button
              type="button"
              onClick={() => setStep('form')}
              className="w-full rounded-card bg-accent px-4 py-3 text-body font-semibold text-accent-fg"
            >
              {t('intro.startButton')}
            </button>
          </div>
        )}

        {step === 'form' && (
          <div className="space-y-8">
            {survey.questions.map((q, idx) => (
              <div key={q.id} className="space-y-3">
                <div>
                  <p className="text-body font-semibold text-theme-primary">
                    <span className="mr-2 text-theme-muted">{idx + 1}.</span>
                    {q.title}
                    {q.required && <span className="ml-1 text-label text-danger">*</span>}
                  </p>
                  {q.description && (
                    <p className="mt-1 text-label text-theme-muted">{q.description}</p>
                  )}
                </div>
                {renderQuestionInput(q)}
              </div>
            ))}

            {formError && (
              <p className="rounded-card bg-danger/10 px-4 py-3 text-body text-danger">{formError}</p>
            )}

            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleNext}
                className="rounded-card bg-accent px-6 py-3 text-body font-semibold text-accent-fg"
              >
                {t('form.nextButton')}
              </button>
            </div>
          </div>
        )}

        {step === 'review' && (
          <div className="space-y-6">
            <h2 className="text-title text-theme-primary">{t('review.title')}</h2>
            <div className="space-y-3">
              {survey.questions.map((q, idx) => (
                <div key={q.id} className="rounded-card bg-theme-surface px-4 py-3 space-y-1">
                  <p className="text-label font-semibold text-theme-muted"><span className="mr-1">{idx + 1}.</span>{q.title}</p>
                  <p className="text-body text-theme-primary">{formatAnswer(q, answers[q.id])}</p>
                </div>
              ))}
            </div>

            {submit.isError && (
              <p className="rounded-card bg-danger/10 px-4 py-3 text-body text-danger">{t('error.submit')}</p>
            )}

            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setStep('form')}
                className="flex-1 rounded-card bg-theme-surface2 px-4 py-3 text-body font-semibold text-theme-muted"
              >
                {t('review.editButton')}
              </button>
              <button
                type="button"
                onClick={() => submit.mutate(answers)}
                disabled={submit.isPending}
                className="flex-1 rounded-card bg-accent px-4 py-3 text-body font-semibold text-accent-fg disabled:opacity-60"
              >
                {submit.isPending ? t('review.submittingButton') : t('review.submitButton')}
              </button>
            </div>
          </div>
        )}

        {step === 'done' && (
          <div className="space-y-4 py-16 text-center">
            <CheckCircle size={56} className="mx-auto text-accent" />
            <h2 className="text-display text-theme-primary">{t('done.title')}</h2>
            <p className="text-body text-theme-muted">{t('done.message')}</p>
          </div>
        )}
      </div>
    </div>
  )
}
