import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { clsx } from 'clsx'

interface ExpandableCaptionProps {
  text: string
  className?: string
}

/**
 * 인스타그램식 설명 — 접힌 상태에서 2줄만 보이고 "더보기"로 전문을 펼친다.
 *
 * 잘림 여부는 글자수가 아니라 실제 레이아웃(scrollHeight vs clientHeight)으로 판단한다.
 * 화면 폭·글꼴·줄바꿈에 따라 몇 자에서 잘리는지가 달라져서, 글자수 휴리스틱은
 * 짧은 글에 "더보기"를 띄우거나 잘린 글에 안 띄우는 오판을 낸다.
 */
export default function ExpandableCaption({ text, className }: ExpandableCaptionProps) {
  const { t } = useTranslation('feed')
  const textRef = useRef<HTMLParagraphElement>(null)
  const [expanded, setExpanded] = useState(false)
  const [clipped, setClipped] = useState(false)

  // 피드 카드가 스크롤 중 다른 게시물에 재사용될 수 있다 — 본문이 바뀌면 다시 접는다.
  useEffect(() => {
    setExpanded(false)
  }, [text])

  const measure = useCallback(() => {
    const el = textRef.current
    if (!el) return
    // 소수점 반올림 오차로 1px 차이가 생길 수 있어 여유를 둔다.
    setClipped(el.scrollHeight > el.clientHeight + 1)
  }, [])

  // 펼친 상태에는 clamp 가 없어 측정값이 의미 없으므로 접혔을 때만 잰다.
  useLayoutEffect(() => {
    if (!expanded) measure()
  }, [text, expanded, measure])

  // 화면 회전·리사이즈로 줄 수가 바뀌면 다시 잰다.
  useEffect(() => {
    const el = textRef.current
    if (!el || expanded || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => measure())
    observer.observe(el)
    return () => observer.disconnect()
  }, [expanded, measure])

  // VideoCard 의 탭 재생/일시정지와 충돌하면 안 된다.
  const toggle = (e: React.MouseEvent) => {
    e.stopPropagation()
    setExpanded((prev) => !prev)
  }

  return (
    <div className={clsx('relative', className)}>
      <p
        ref={textRef}
        className={clsx(
          'text-body text-white/80 whitespace-pre-wrap break-words',
          expanded ? 'max-h-[40vh] overflow-y-auto overscroll-contain' : 'line-clamp-2',
        )}
      >
        {text}
      </p>

      {expanded ? (
        <button
          type="button"
          onClick={toggle}
          aria-expanded={true}
          className="mt-1 text-label text-white/60 active:opacity-70"
        >
          {t('captionLess')}
        </button>
      ) : (
        clipped && (
          <button
            type="button"
            onClick={toggle}
            aria-expanded={false}
            // 접힌 2번째 줄 끝에 겹쳐 놓는다. 왼쪽 페이드가 본문과의 경계를 지운다.
            className="absolute bottom-0 right-0 bg-gradient-to-r from-transparent to-black/60 pl-6 text-label text-white/60 active:opacity-70"
          >
            … {t('captionMore')}
          </button>
        )
      )}
    </div>
  )
}
