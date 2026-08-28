import { getProfileColor } from '../utils/profileColor'

interface UserAvatarProps {
  username: string
  avatarUrl?: string | null
  profileColor?: string | null
  size?: number
  className?: string
}

export default function UserAvatar({ username, avatarUrl, profileColor, size = 36, className = '' }: UserAvatarProps) {
  const color = getProfileColor(username, profileColor)
  const initial = username[0]?.toUpperCase() ?? '?'

  if (avatarUrl) {
    return (
      <img
        src={avatarUrl}
        alt={username}
        style={{ width: size, height: size }}
        className={`rounded-pill object-cover flex-shrink-0 ${className}`}
      />
    )
  }

  return (
    <div
      style={{ width: size, height: size, backgroundColor: color }}
      className={`rounded-pill flex-shrink-0 flex items-center justify-center font-bold text-white ${className}`}
    >
      <span style={{ fontSize: Math.max(10, size * 0.4) }}>{initial}</span>
    </div>
  )
}
