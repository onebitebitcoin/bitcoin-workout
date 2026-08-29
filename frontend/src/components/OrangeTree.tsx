export type TreeStage = 'seed' | 'sprout' | 'sapling' | 'tree' | 'grand'
export type FruitSize = 'small' | 'medium' | 'large'

interface OrangeTreeProps {
  /** 나무 성장 단계. 사용자의 기록 진척도를 나타낸다. */
  stage: TreeStage
  /** 열매 개수(0~7). 범위를 벗어나면 clamp된다. 비트코인 가격을 나타낸다. */
  fruitCount?: number
  /** 열매 크기. 비트코인 가격을 나타낸다. */
  fruitSize?: FruitSize
  /** 렌더 크기(px, 정사각형). */
  size?: number
  className?: string
}

const FRUIT_RADIUS: Record<FruitSize, number> = {
  small: 2.8,
  medium: 3.4,
  large: 4.2,
}

// tree/grand 수관 위에 얹는 열매 자리. fruitCount만큼 앞에서부터 쓴다.
const FRUIT_POSITIONS: Array<[number, number]> = [
  [33, 23],
  [47, 30],
  [42, 16],
  [25, 37],
  [56, 35],
  [36, 34],
  [50, 21],
]

// sapling은 수관이 작다(중앙 cx40,cy34,r11 + 좌우 cx31/49,cy42,r7). 위 7개 좌표를 그대로
// 쓰면 수관 밖으로 나가므로, 앞 4개 자리만 sapling 수관 크기에 맞춰 다시 잡았다.
const SAPLING_FRUIT_POSITIONS: Array<[number, number]> = [
  [35, 29],
  [46, 30],
  [41, 25],
  [30, 44],
]

function clampFruitCount(count: number): number {
  return Math.max(0, Math.min(7, Math.round(count)))
}

/**
 * 오렌지 나무 표현 컴포넌트.
 *
 * 나무는 사용자의 기록을 나타내며 stage 5단계로 자란다. 열매는 비트코인 가격을 나타내며
 * 개수·크기만 바뀐다 — 하락장이어도 나무 자체(줄기·수관)는 그대로 유지된다.
 *
 * 순수 표현 컴포넌트다. API 호출·상태관리·i18n 텍스트를 갖지 않는다.
 */
export default function OrangeTree({
  stage,
  fruitCount = 0,
  fruitSize = 'medium',
  size = 150,
  className = '',
}: OrangeTreeProps) {
  // seed/sprout는 잎 덩어리(수관)가 없어 열매를 얹을 자리가 없다.
  const canBearFruit = stage !== 'seed' && stage !== 'sprout'
  const count = clampFruitCount(fruitCount)
  const positions = stage === 'sapling' ? SAPLING_FRUIT_POSITIONS : FRUIT_POSITIONS
  const radius = stage === 'sapling' ? FRUIT_RADIUS[fruitSize] * 0.8 : FRUIT_RADIUS[fruitSize]
  const fruits = canBearFruit ? positions.slice(0, count) : []

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 80 80"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label={`orange-tree-${stage}`}
      className={className}
    >
      {/* 바닥 — 모든 단계 공통 */}
      <path d="M20,70 Q40,61 60,70 Z" fill="#241C14" />
      <ellipse cx="40" cy="70" rx="21" ry="3.5" fill="#111111" />

      {stage === 'seed' && (
        <ellipse cx="40" cy="65" rx="4.5" ry="6" fill="#8B5A2B" transform="rotate(14 40 65)" />
      )}

      {stage === 'sprout' && (
        <>
          <path
            d="M40,68 L40,50"
            stroke="var(--leaf-deep)"
            strokeWidth={2.5}
            strokeLinecap="round"
          />
          <path d="M40,57 C33,57 29,52 29,46 C36,46 40,51 40,57 Z" fill="var(--leaf)" />
          <path d="M40,62 C47,62 51,57 51,51 C44,51 40,56 40,62 Z" fill="#35A866" />
        </>
      )}

      {stage === 'sapling' && (
        <>
          <path d="M40,68 L40,40" stroke="#7A4A22" strokeWidth={3} strokeLinecap="round" />
          <path d="M40,52 L32,45" stroke="#7A4A22" strokeWidth={2} strokeLinecap="round" />
          <path d="M40,56 L48,49" stroke="#7A4A22" strokeWidth={2} strokeLinecap="round" />
          <circle cx="31" cy="42" r="7" fill="#35A866" />
          <circle cx="49" cy="42" r="7" fill="#35A866" />
          <circle cx="40" cy="34" r="11" fill="var(--leaf)" />
        </>
      )}

      {(stage === 'tree' || stage === 'grand') && (
        <>
          <path
            d="M40,68 L40,34"
            stroke="#7A4A22"
            strokeWidth={stage === 'grand' ? 5.5 : 4.5}
            strokeLinecap="round"
          />
          <path d="M40,48 L28,38" stroke="#7A4A22" strokeWidth={3} strokeLinecap="round" />
          <path d="M40,44 L52,34" stroke="#7A4A22" strokeWidth={3} strokeLinecap="round" />
          <circle cx="26" cy="34" r={stage === 'grand' ? 11.5 : 10} fill="#35A866" />
          <circle cx="54" cy="34" r={stage === 'grand' ? 11.5 : 10} fill="#35A866" />
          <circle cx="40" cy="26" r={stage === 'grand' ? 15.5 : 14} fill="var(--leaf)" />
        </>
      )}

      {fruits.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={radius} fill="rgb(var(--accent-rgb))" />
      ))}
    </svg>
  )
}
