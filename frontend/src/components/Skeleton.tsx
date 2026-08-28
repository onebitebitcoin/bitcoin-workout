// 스켈레톤은 shimmer 애니메이션을 Tailwind의 `animate-shimmer` 클래스로 받는다.
// 인라인 `animation: 'shimmer ...'`으로 쓰면 JIT이 어떤 파일에서도 `animate-shimmer`를
// 발견하지 못해 @keyframes shimmer 자체를 CSS로 내보내지 않는다 (= 아무 것도 움직이지 않는다).
const SHIMMER_BG = 'linear-gradient(90deg, var(--bg-surface-2) 25%, var(--bg-surface) 50%, var(--bg-surface-2) 75%)'

export function SkeletonCalendarGrid() {
  return (
    <div className="grid grid-cols-7 gap-1">
      {Array.from({ length: 35 }).map((_, i) => (
        <div
          key={i}
          className="aspect-square rounded-card animate-shimmer"
          style={{
            background: SHIMMER_BG,
            backgroundSize: '200% 100%',
            animationDelay: `${(i % 7) * 0.05}s`,
          }}
        />
      ))}
    </div>
  )
}
