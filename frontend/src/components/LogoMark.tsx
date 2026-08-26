import { useId, type SVGProps } from 'react'

interface LogoMarkProps extends SVGProps<SVGSVGElement> {
  size?: number
}

export default function LogoMark({ size = 48, className = '', ...props }: LogoMarkProps) {
  const maskId = useId()

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
      <mask id={maskId}>
        <rect x="0" y="0" width="48" height="48" fill="white" />
        <path
          d="M21.6 19.6L21.6 28.4L29.4 24Z"
          fill="black"
          stroke="black"
          strokeWidth={5}
          strokeLinejoin="round"
        />
      </mask>
      {/* Top ticks */}
      <rect x="18.2" y="2.8" width="3.6" height="9.4" rx="1.4" fill="currentColor" />
      <rect x="26.2" y="2.8" width="3.6" height="9.4" rx="1.4" fill="currentColor" />
      {/* Bottom ticks */}
      <rect x="18.2" y="35.8" width="3.6" height="9.4" rx="1.4" fill="currentColor" />
      <rect x="26.2" y="35.8" width="3.6" height="9.4" rx="1.4" fill="currentColor" />
      {/* Coin with play-triangle cutout */}
      <circle cx="24" cy="24" r="15.2" fill="currentColor" mask={`url(#${maskId})`} />
    </svg>
  )
}
