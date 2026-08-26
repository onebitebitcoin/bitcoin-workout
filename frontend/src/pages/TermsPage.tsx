import { useNavigate } from 'react-router-dom'
import { ChevronLeft } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export default function TermsPage() {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  return (
    <div className="flex flex-col h-[100dvh] bg-theme-page overflow-y-auto pb-8">
      <div className="flex items-center gap-3 px-4 py-4 border-b border-theme-border">
        <button onClick={() => navigate(-1)} className="text-theme-muted">
          <ChevronLeft size={24} />
        </button>
        <h1 className="font-bold text-theme-primary">{t('termsTitle')}</h1>
      </div>

      <div className="px-4 pt-5 pb-6 space-y-6 text-sm text-theme-muted leading-relaxed">
        <p className="text-xs font-semibold uppercase tracking-widest text-theme-muted">{t('termsServiceGuide')}</p>
        <section>
          <h2 className="font-semibold text-theme-primary mb-2">{t('termsSection.intro.title')}</h2>
          <p>{t('termsSection.intro.body')}</p>
        </section>
        <section>
          <h2 className="font-semibold text-theme-primary mb-2">{t('termsSection.categories.title')}</h2>
          <p>{t('termsSection.categories.body')}</p>
        </section>
        <section>
          <h2 className="font-semibold text-theme-primary mb-2">{t('termsSection.uploadPolicy.title')}</h2>
          <p>{t('termsSection.uploadPolicy.body')}</p>
        </section>
        <div className="h-px bg-theme-border" />
        <p className="text-xs font-semibold uppercase tracking-widest text-theme-muted">{t('termsSection.termsLabel')}</p>
        <section>
          <h2 className="font-semibold text-theme-primary mb-2">{t('termsSection.article1.title')}</h2>
          <p>{t('termsSection.article1.body')}</p>
        </section>
        <section>
          <h2 className="font-semibold text-theme-primary mb-2">{t('termsSection.article2.title')}</h2>
          <p>{t('termsSection.article2.body')}</p>
        </section>
        <section>
          <h2 className="font-semibold text-theme-primary mb-2">{t('termsSection.article3.title')}</h2>
          <p>{t('termsSection.article3.body')}</p>
        </section>
        <section>
          <h2 className="font-semibold text-theme-primary mb-2">{t('termsSection.contact.title')}</h2>
          <p>{t('termsSection.contact.body')}</p>
        </section>
      </div>
    </div>
  )
}
