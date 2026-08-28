import { Trophy, X, Search, Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Challenge } from '../../api/types'
import type { MediaItem } from './StepMedia'
import type { VideoFilterValue } from '../../utils/videoFilter'
import MediaPreviewBox from './MediaPreviewBox'
import { MAIN_CATEGORIES, MAIN_CATEGORY_LABEL_KEYS, type MainCategory } from '../../constants/category'

interface Props {
  mainCategory: MainCategory | null
  setMainCategory: (cat: MainCategory) => void
  hasChallenge: boolean | null
  setHasChallenge: (v: boolean | null) => void
  selectedChallenge: Challenge | null
  selectedChallengeId: number | null
  clearChallenge: () => void
  openChallengeModal: () => void
  showChallengeModal: boolean
  setShowChallengeModal: (v: boolean) => void
  challengeSearch: string
  setChallengeSearch: (v: string) => void
  displayedChallenges: Challenge[]
  selectChallenge: (c: Challenge) => void
  caption: string
  setCaption: (v: string) => void
  limitError: string
  setLimitError: (v: string) => void
  error: string
  uploading: boolean
  onUpload: () => void
  // 업로드 전 접이식 미리보기용
  items: MediaItem[]
  subtitleSource: string
  subtitleLines: string[]
  subtitleSize: 'small' | 'large'
  subtitlePosition: 'top' | 'center' | 'bottom'
  videoFilter: VideoFilterValue
  filteredPreviewUrl: string | null
}

export default function StepMeta({
  mainCategory, setMainCategory,
  hasChallenge, setHasChallenge, selectedChallenge, selectedChallengeId,
  clearChallenge, openChallengeModal, showChallengeModal, setShowChallengeModal,
  challengeSearch, setChallengeSearch, displayedChallenges, selectChallenge,
  caption, setCaption, limitError, setLimitError, error, uploading, onUpload,
  items, subtitleSource, subtitleLines, subtitleSize, subtitlePosition,
  videoFilter, filteredPreviewUrl,
}: Props) {
  const { t } = useTranslation('upload')

  const MAIN_CATEGORY_LABELS = Object.fromEntries(
    MAIN_CATEGORIES.map((cat) => [cat, t(`tagChallenge.${MAIN_CATEGORY_LABEL_KEYS[cat]}`)]),
  ) as Record<MainCategory, string>

  async function handleUpload() {
    setLimitError('')
    if (!mainCategory) {
      setLimitError(t('tagChallenge.categoryRequired'))
      return
    }
    onUpload()
  }

  return (
    <>
      <div className="flex flex-1 flex-col px-6 pt-2 pb-6 overflow-y-auto gap-4">
        {/* 카테고리 */}
        <div>
          <p className="mb-2 text-body font-semibold text-theme-primary">{t('tagChallenge.category')}</p>
          <div className="flex gap-2 mb-3">
            {MAIN_CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setMainCategory(cat)}
                className={`flex-1 rounded-card py-3 text-body font-medium transition-colors ${
                  mainCategory === cat ? 'bg-accent text-accent-fg' : 'bg-theme-surface text-theme-muted'
                }`}
              >
                {MAIN_CATEGORY_LABELS[cat]}
              </button>
            ))}
          </div>

        </div>

        {/* 챌린지 */}
        <div>
          <p className="mb-2 text-body font-semibold text-theme-primary">{t('tagChallenge.challenge')}</p>
          <div className="flex gap-2 mb-3">
            <button onClick={() => { setHasChallenge(false); clearChallenge() }} className={`flex-1 rounded-card py-3 text-body font-medium transition-colors ${hasChallenge === false ? 'bg-accent text-accent-fg' : 'bg-theme-surface text-theme-muted'}`}>{t('tagChallenge.challengeNone')}</button>
            <button onClick={() => { setHasChallenge(true); openChallengeModal() }} className={`flex-1 rounded-card py-3 text-body font-medium transition-colors ${hasChallenge === true ? 'bg-accent text-accent-fg' : 'bg-theme-surface text-theme-muted'}`}>{t('tagChallenge.challengeHas')}</button>
          </div>
          {hasChallenge === true && selectedChallenge && (
            <button onClick={openChallengeModal} className="flex items-center gap-2 rounded-card bg-accent/10 px-4 py-3 text-left w-full">
              <Trophy size={14} className="text-accent flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-body font-medium text-accent truncate">{selectedChallenge.title}</p>
                <p className="text-label text-accent/70 mt-1">{t('tagChallenge.participantCount', { count: selectedChallenge.participant_count })}{t('tagChallenge.participantSeparator')}{selectedChallenge.reward_title}</p>
              </div>
              <X size={15} className="text-accent/60 flex-shrink-0" onClick={(e) => { e.stopPropagation(); clearChallenge() }} />
            </button>
          )}
          {hasChallenge === true && !selectedChallenge && (
            <button onClick={openChallengeModal} className="flex items-center justify-between rounded-card bg-theme-surface px-4 py-3 w-full">
              <span className="text-body text-theme-muted">{t('tagChallenge.challengeSelect')}</span>
            </button>
          )}
        </div>

        {/* 설명 */}
        <div className="flex flex-col gap-1">
          <p className="text-body font-semibold text-theme-primary mb-1">{t('caption.captionLabel')} <span className="text-label font-normal text-theme-muted">{t('caption.captionOptional')}</span></p>
          <textarea
            value={caption}
            onChange={(e) => setCaption(e.target.value.slice(0, 140))}
            maxLength={140}
            placeholder={t('caption.captionPlaceholder')}
            rows={3}
            className="resize-none rounded-card bg-theme-surface px-4 py-3 text-theme-primary placeholder-theme-muted outline-none focus:ring-2 focus:ring-accent"
          />
          <p className="text-right text-label text-theme-muted">{caption.length}/140</p>
        </div>

        {/* 업로드 전 미리보기 */}
        {items.length > 0 && (
          <div>
            <p className="mb-2 text-body font-semibold text-theme-primary">{t('preview.title')}</p>
            <MediaPreviewBox
              items={items}
              subtitleSource={subtitleSource}
              subtitleLines={subtitleLines}
              subtitleSize={subtitleSize}
              subtitlePosition={subtitlePosition}
              videoFilter={videoFilter}
              filteredPreviewUrl={filteredPreviewUrl}
            />
          </div>
        )}

        {limitError && <p className="text-body text-danger">{limitError}</p>}
        {error && <p className="text-body text-danger">{error}</p>}

        <button onClick={handleUpload} disabled={uploading} className="mt-auto w-full rounded-card bg-accent py-3 font-semibold text-accent-fg disabled:opacity-60">
          {t('caption.uploadStart')}
        </button>
      </div>

      {/* 챌린지 선택 모달 */}
      {showChallengeModal && (
        <div className="fixed inset-0 z-50 flex flex-col bg-theme-page lg:max-w-2xl lg:mx-auto">
          <div className="flex items-center gap-3 px-4 pt-5 pb-3 flex-shrink-0">
            <button onClick={() => { setShowChallengeModal(false); setChallengeSearch(''); if (!selectedChallenge) setHasChallenge(null) }} className="text-theme-muted"><X size={20} /></button>
            <h2 className="text-title font-semibold text-theme-primary flex-1">{t('tagChallenge.challengeModalTitle')}</h2>
          </div>
          <div className="px-4 mb-3 flex-shrink-0">
            <div className="flex items-center gap-2 rounded-card bg-theme-surface px-3 py-3">
              <Search size={15} className="text-theme-muted flex-shrink-0" />
              <input type="text" value={challengeSearch} onChange={(e) => setChallengeSearch(e.target.value)} placeholder={t('tagChallenge.challengeSearchPlaceholder')} autoFocus className="flex-1 bg-transparent text-body text-theme-primary placeholder-theme-muted outline-none" />
              {challengeSearch && <button onClick={() => setChallengeSearch('')} className="text-theme-muted flex-shrink-0"><X size={14} /></button>}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-4 pb-6">
            {!challengeSearch && <p className="text-label text-theme-muted mb-2">{t('tagChallenge.challengeOngoing')}</p>}
            {displayedChallenges.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <Trophy size={32} className="text-theme-surface2 mb-3" strokeWidth={1} />
                <p className="text-body text-theme-muted">{challengeSearch ? t('tagChallenge.challengeSearchEmpty') : t('tagChallenge.challengeEmpty')}</p>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {displayedChallenges.map((c) => (
                  <button key={c.id} onClick={() => selectChallenge(c)} className={`flex items-start gap-3 rounded-card px-4 py-3 text-left transition-colors ${selectedChallengeId === c.id ? 'bg-accent text-accent-fg' : 'bg-theme-surface text-theme-primary'}`}>
                    {c.image_thumb_url ? (
                      <img src={c.image_thumb_url} alt="" className="w-10 h-10 rounded-card object-cover flex-shrink-0" />
                    ) : (
                      <div className="w-10 h-10 rounded-card bg-theme-surface2 flex items-center justify-center flex-shrink-0"><Trophy size={16} strokeWidth={1.5} className={selectedChallengeId === c.id ? 'text-accent-fg' : 'text-theme-muted'} /></div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-body font-medium truncate">{c.title}</p>
                      <p className={`text-label mt-1 ${selectedChallengeId === c.id ? 'text-accent-fg/70' : 'text-theme-muted'}`}>{t('tagChallenge.participantCount', { count: c.participant_count })}{t('tagChallenge.participantSeparator')}{c.reward_title}</p>
                    </div>
                    {selectedChallengeId === c.id && <Check size={16} className="text-accent-fg flex-shrink-0 mt-1" />}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
