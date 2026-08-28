import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Plus, Trash2, ChevronUp, ChevronDown, X } from 'lucide-react'
import toast from 'react-hot-toast'
import client from '../api/client'
import type { Survey, SurveyQuestion } from '../api/types'
import { useAuthStore } from '../store/auth'

type QuestionType = 'scale' | 'single' | 'multi' | 'text'

interface QuestionDraft {
  id: string
  type: QuestionType
  title: string
  description: string
  required: boolean
  options: string[]
  scale_min: string
  scale_max: string
  scale_min_label: string
  scale_max_label: string
}

function toDatetimeLocal(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function fromSurveyQuestion(q: SurveyQuestion): QuestionDraft {
  return {
    id: q.id,
    type: q.type,
    title: q.title,
    description: q.description ?? '',
    required: q.required,
    options: q.options && q.options.length > 0 ? q.options : [''],
    scale_min: String(q.scale_min ?? 1),
    scale_max: String(q.scale_max ?? 5),
    scale_min_label: q.scale_min_label ?? '',
    scale_max_label: q.scale_max_label ?? '',
  }
}

function newQuestion(): QuestionDraft {
  return {
    id: `q_${Date.now().toString(36)}`,
    type: 'scale',
    title: '',
    description: '',
    required: true,
    options: [''],
    scale_min: '1',
    scale_max: '5',
    scale_min_label: '',
    scale_max_label: '',
  }
}

export default function AdminSurveyEditorPage() {
  const { t } = useTranslation('survey')
  const navigate = useNavigate()
  const { id } = useParams<{ id?: string }>()
  const isEdit = !!id
  const user = useAuthStore((s) => s.user)
  const isAdmin = user?.is_admin ?? false

  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [closesAt, setClosesAt] = useState('')
  const [questions, setQuestions] = useState<QuestionDraft[]>([])
  const [titleError, setTitleError] = useState<string | null>(null)

  const { data: existingSurvey } = useQuery<Survey>({
    queryKey: ['admin-survey-edit', id],
    queryFn: async () => {
      const res = await client.get<{ data: { survey: Survey } }>(`/surveys/${id}`)
      return res.data.data.survey
    },
    enabled: isAdmin && isEdit,
  })

  useEffect(() => {
    if (existingSurvey) {
      setTitle(existingSurvey.title)
      setDescription(existingSurvey.description ?? '')
      setClosesAt(toDatetimeLocal(existingSurvey.closes_at))
      setQuestions(existingSurvey.questions.map(fromSurveyQuestion))
    }
  }, [existingSurvey])

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        title,
        description: description.trim() || null,
        questions: questions.map((q) => ({
          id: q.id,
          type: q.type,
          title: q.title,
          description: q.description.trim() || null,
          required: q.required,
          options: q.type === 'single' || q.type === 'multi' ? q.options.filter(Boolean) : null,
          scale_min: q.type === 'scale' ? Number(q.scale_min) : null,
          scale_max: q.type === 'scale' ? Number(q.scale_max) : null,
          scale_min_label: q.type === 'scale' ? q.scale_min_label.trim() || null : null,
          scale_max_label: q.type === 'scale' ? q.scale_max_label.trim() || null : null,
        })),
        closes_at: closesAt ? new Date(closesAt).toISOString() : null,
      }
      if (isEdit) {
        const res = await client.put<{ data: { survey: Survey } }>(`/surveys/${id}`, body)
        return res.data.data.survey
      } else {
        const res = await client.post<{ data: { survey: Survey } }>('/surveys', body)
        return res.data.data.survey
      }
    },
    onSuccess: () => {
      toast.success(t('admin.editor.saveSuccess'))
      navigate('/admin/surveys')
    },
    onError: () => {
      toast.error(t('admin.editor.saveFailed'))
    },
  })

  const handleSave = () => {
    if (!title.trim()) {
      setTitleError(t('admin.editor.emptyTitle'))
      return
    }
    setTitleError(null)
    save.mutate()
  }

  const addQuestion = () => {
    setQuestions((prev) => [...prev, newQuestion()])
  }

  const removeQuestion = (index: number) => {
    setQuestions((prev) => prev.filter((_, i) => i !== index))
  }

  const moveQuestion = (index: number, direction: 'up' | 'down') => {
    setQuestions((prev) => {
      const next = [...prev]
      const target = direction === 'up' ? index - 1 : index + 1
      if (target < 0 || target >= next.length) return prev
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  const updateQuestion = (index: number, updates: Partial<QuestionDraft>) => {
    setQuestions((prev) => prev.map((q, i) => (i === index ? { ...q, ...updates } : q)))
  }

  const addOption = (index: number) => {
    updateQuestion(index, { options: [...questions[index].options, ''] })
  }

  const updateOption = (qIndex: number, optIndex: number, value: string) => {
    const opts = [...questions[qIndex].options]
    opts[optIndex] = value
    updateQuestion(qIndex, { options: opts })
  }

  const removeOption = (qIndex: number, optIndex: number) => {
    const opts = questions[qIndex].options.filter((_, i) => i !== optIndex)
    updateQuestion(qIndex, { options: opts.length > 0 ? opts : [''] })
  }

  if (!isAdmin) {
    return (
      <div className="flex h-[100dvh] items-center justify-center bg-theme-page">
        <p className="text-body text-theme-muted">{t('admin.adminOnly')}</p>
      </div>
    )
  }

  const QUESTION_TYPES: QuestionType[] = ['scale', 'single', 'multi', 'text']

  return (
    <div className="flex h-[100dvh] flex-col bg-theme-page">
      <div className="flex-none px-4 pt-6 pb-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/admin/surveys')}
            className="flex h-8 w-8 items-center justify-center rounded-pill hover:bg-theme-surface transition-colors"
          >
            <ArrowLeft size={18} strokeWidth={2} className="text-theme-primary" />
          </button>
          <h1 className="text-display text-theme-primary">
            {isEdit ? t('admin.editor.editTitle') : t('admin.editor.newTitle')}
          </h1>
        </div>
        <button
          onClick={handleSave}
          disabled={save.isPending}
          className="rounded-card bg-accent px-4 py-2 text-body font-semibold text-accent-fg disabled:opacity-60"
        >
          {save.isPending ? t('admin.editor.saving') : t('admin.editor.saveButton')}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-24 space-y-6">
        <div className="space-y-4">
          <div className="space-y-2">
            <label className="text-label font-semibold text-theme-muted">{t('admin.editor.titleLabel')}</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('admin.editor.titlePlaceholder')}
              className="w-full rounded-card border border-theme-border bg-theme-surface px-4 py-3 text-body text-theme-primary placeholder:text-theme-muted outline-none focus:border-accent"
            />
            {titleError && <p className="text-label text-danger">{titleError}</p>}
          </div>

          <div className="space-y-2">
            <label className="text-label font-semibold text-theme-muted">{t('admin.editor.descriptionLabel')}</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('admin.editor.descriptionPlaceholder')}
              rows={3}
              className="w-full resize-none rounded-card border border-theme-border bg-theme-surface px-4 py-3 text-body text-theme-primary placeholder:text-theme-muted outline-none focus:border-accent"
            />
          </div>

          <div className="space-y-2">
            <label className="text-label font-semibold text-theme-muted">{t('admin.editor.closesAtLabel')}</label>
            <input
              type="datetime-local"
              value={closesAt}
              onChange={(e) => setClosesAt(e.target.value)}
              className="w-full rounded-card border border-theme-border bg-theme-surface px-4 py-3 text-body text-theme-primary outline-none focus:border-accent"
            />
          </div>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-body font-semibold text-theme-primary">{t('admin.editor.questionsLabel')}</p>
            <button
              type="button"
              onClick={addQuestion}
              className="flex items-center gap-2 rounded-card bg-theme-surface px-3 py-2 text-label font-semibold text-theme-muted hover:text-theme-primary"
            >
              <Plus size={12} />
              {t('admin.editor.addQuestion')}
            </button>
          </div>

          {questions.map((q, qi) => (
            <div key={q.id} className="rounded-card bg-theme-surface p-4 space-y-4">
              <div className="flex items-center gap-2">
                <span className="text-label font-bold text-theme-muted shrink-0">Q{qi + 1}</span>
                <div className="flex-1 min-w-0">
                  <select
                    value={q.type}
                    onChange={(e) => updateQuestion(qi, { type: e.target.value as QuestionType })}
                    className="w-full rounded-card bg-theme-surface2 px-3 py-2 text-label text-theme-primary outline-none"
                  >
                    {QUESTION_TYPES.map((t_) => (
                      <option key={t_} value={t_}>
                        {t(`admin.editor.types.${t_}`)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    type="button"
                    onClick={() => moveQuestion(qi, 'up')}
                    disabled={qi === 0}
                    className="rounded p-1 text-theme-muted hover:text-theme-primary disabled:opacity-30"
                    aria-label={t('admin.editor.moveUp')}
                  >
                    <ChevronUp size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={() => moveQuestion(qi, 'down')}
                    disabled={qi === questions.length - 1}
                    className="rounded p-1 text-theme-muted hover:text-theme-primary disabled:opacity-30"
                    aria-label={t('admin.editor.moveDown')}
                  >
                    <ChevronDown size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={() => removeQuestion(qi)}
                    className="rounded p-1 text-danger hover:text-danger"
                    aria-label={t('admin.editor.deleteQuestion')}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>

              <div className="space-y-3">
                <input
                  type="text"
                  value={q.title}
                  onChange={(e) => updateQuestion(qi, { title: e.target.value })}
                  placeholder={t('admin.editor.questionTitlePlaceholder')}
                  className="w-full rounded-card border border-theme-border bg-theme-surface2 px-3 py-2 text-body text-theme-primary placeholder:text-theme-muted outline-none focus:border-accent"
                />

                <label className="flex cursor-pointer items-center gap-2 text-label">
                  <input
                    type="checkbox"
                    checked={q.required}
                    onChange={(e) => updateQuestion(qi, { required: e.target.checked })}
                    className="accent-accent"
                  />
                  <span className="text-theme-muted">
                    {q.required ? t('admin.editor.required') : t('admin.editor.optional')}
                  </span>
                </label>

                {(q.type === 'single' || q.type === 'multi') && (
                  <div className="space-y-2">
                    {q.options.map((opt, oi) => (
                      <div key={oi} className="flex items-center gap-2">
                        <input
                          type="text"
                          value={opt}
                          onChange={(e) => updateOption(qi, oi, e.target.value)}
                          placeholder={t('admin.editor.optionPlaceholder')}
                          className="flex-1 rounded-card border border-theme-border bg-theme-surface2 px-3 py-2 text-label text-theme-primary placeholder:text-theme-muted outline-none focus:border-accent"
                        />
                        <button
                          type="button"
                          onClick={() => removeOption(qi, oi)}
                          className="shrink-0 rounded p-1 text-theme-muted hover:text-danger"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() => addOption(qi)}
                      className="flex items-center gap-1 rounded-card px-2 py-2 text-label text-theme-muted hover:text-theme-primary"
                    >
                      <Plus size={11} />
                      {t('admin.editor.addOption')}
                    </button>
                  </div>
                )}

                {q.type === 'scale' && (
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <label className="text-label text-theme-muted">{t('admin.editor.scaleMin')}</label>
                      <input
                        type="number"
                        value={q.scale_min}
                        onChange={(e) => updateQuestion(qi, { scale_min: e.target.value })}
                        className="w-full rounded-card border border-theme-border bg-theme-surface2 px-3 py-2 text-label text-theme-primary outline-none focus:border-accent"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-label text-theme-muted">{t('admin.editor.scaleMax')}</label>
                      <input
                        type="number"
                        value={q.scale_max}
                        onChange={(e) => updateQuestion(qi, { scale_max: e.target.value })}
                        className="w-full rounded-card border border-theme-border bg-theme-surface2 px-3 py-2 text-label text-theme-primary outline-none focus:border-accent"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-label text-theme-muted">{t('admin.editor.scaleMinLabel')}</label>
                      <input
                        type="text"
                        value={q.scale_min_label}
                        onChange={(e) => updateQuestion(qi, { scale_min_label: e.target.value })}
                        className="w-full rounded-card border border-theme-border bg-theme-surface2 px-3 py-2 text-label text-theme-primary outline-none focus:border-accent"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-label text-theme-muted">{t('admin.editor.scaleMaxLabel')}</label>
                      <input
                        type="text"
                        value={q.scale_max_label}
                        onChange={(e) => updateQuestion(qi, { scale_max_label: e.target.value })}
                        className="w-full rounded-card border border-theme-border bg-theme-surface2 px-3 py-2 text-label text-theme-primary outline-none focus:border-accent"
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}

          {questions.length === 0 && (
            <div className="rounded-card bg-theme-surface px-4 py-8 text-center">
              <p className="text-body text-theme-muted">{t('admin.noSurveys')}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
