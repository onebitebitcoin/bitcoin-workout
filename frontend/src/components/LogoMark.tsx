import { useId, type SVGProps } from 'react'

interface LogoMarkProps extends SVGProps<SVGSVGElement> {
  size?: number
  /**
   * 잎 색. 기본은 브랜드 초록(--leaf).
   * 오렌지 타일처럼 밝은 배경 위에 얹을 때만 진초록(--leaf-deep)으로 낮춘다.
   */
  leafColor?: string
}

/**
 * Coin Play 를 이어받은 오렌지 마크. 열매를 번개가 뚫고 배경이 비친다.
 *
 * 열매는 currentColor 라서 호출부의 text-accent 등으로 계속 물들일 수 있다.
 * 명암을 오렌지 계열 하드코딩이 아니라 흑백 반투명으로 얹은 것도 같은 이유다 —
 * 어떤 색으로 물들여도 그 색의 밝은 면/그늘로 성립한다.
 */
export default function LogoMark({
  size = 48,
  className = '',
  leafColor = 'var(--leaf)',
  ...props
}: LogoMarkProps) {
  const baseId = useId()
  const clipId = `${baseId}-fruit`
  const maskId = `${baseId}-bolt`
  // 20px 아래에서는 명암·잎맥·꼭지가 한 픽셀 안에서 뭉개져 오히려 지저분해진다.
  // 그 크기에서는 실루엣만 남긴다.
  const detailed = size > 20

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      {...props}
    >
      <defs>
        <clipPath id={clipId}>
          <circle cx="24" cy="28" r="14" />
        </clipPath>
        <mask id={maskId}>
          <rect width="48" height="48" fill="white" />
          <path d="M27.6 17.6L18.9 28.8H23.6L20.6 38.6L29.6 26.6H24.7Z" fill="black" />
        </mask>
      </defs>

      {/* 열매 */}
      <g mask={`url(#${maskId})`}>
        <g clipPath={`url(#${clipId})`}>
          <circle cx="24" cy="28" r="14" fill="currentColor" />
          {detailed && (
            <>
              <ellipse cx="34" cy="40" rx="15" ry="13" fill="#000000" opacity={0.16} />
              <ellipse
                cx="18"
                cy="22"
                rx="6.5"
                ry="4.5"
                fill="#FFFFFF"
                opacity={0.22}
                transform="rotate(-35 18 22)"
              />
            </>
          )}
        </g>
      </g>

      {/* 꼭지 */}
      {detailed && (
        <path
          d="M24 15C24 12 24.5 10.5 25.5 9.5"
          stroke="#7A4A22"
          strokeWidth={2.4}
          strokeLinecap="round"
        />
      )}

      {/* 잎 */}
      <path
        d="M25.8 10.6C28.2 4.6 34.4 2.4 38.6 4.2C38.4 9.8 32.8 13.2 25.8 10.6Z"
        fill={leafColor}
      />
      {detailed && (
        <path
          d="M27.2 10.2C30.6 7.4 34.6 5.4 37.6 4.6"
          stroke="var(--leaf-deep)"
          strokeWidth={1.1}
          strokeLinecap="round"
        />
      )}
    </svg>
  )
}
