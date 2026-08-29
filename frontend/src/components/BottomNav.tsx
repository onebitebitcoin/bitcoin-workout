import { NavLink, useNavigate } from 'react-router-dom'
import { Bell, Home, Plus, UserCircle, Target } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../store/auth'
import { useUiStore } from '../store/ui'
import { useUnreadNotifications } from '../hooks/useUnreadNotifications'

export default function BottomNav() {
  const navigate = useNavigate()
  const { t } = useTranslation('common')
  const token = useAuthStore((s) => s.token)
  const commentOpen = useUiStore((s) => s.commentOpen)
  const unreadCount = useUnreadNotifications()

  if (commentOpen) return null

  function handleUpload() {
    if (token) {
      navigate('/upload')
    } else {
      navigate('/login')
    }
  }

  const navItem = ({ isActive }: { isActive: boolean }) =>
    `flex flex-col items-center gap-1 px-3 py-1 text-label transition-colors ${
      isActive ? 'text-accent-text' : 'text-theme-muted'
    }`

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 border-t border-theme-border bg-theme-surface pb-safe lg:hidden" style={{ transform: 'translateZ(0)' }}>
      <div className="flex h-16 items-center justify-around">
        <NavLink to="/" end className={navItem}>
          <Home size={22} strokeWidth={1.75} />
          <span>{t('nav.feed')}</span>
        </NavLink>

        <NavLink to="/challenges" className={navItem}>
          <Target size={22} strokeWidth={1.75} />
          <span>{t('nav.challenges')}</span>
        </NavLink>

        {/* FAB — 업로드 */}
        <div className="relative flex flex-col items-center">
          <button
            onClick={handleUpload}
            className="absolute -top-7 flex h-14 w-14 items-center justify-center rounded-pill bg-accent shadow-float transition-transform active:scale-90"
            aria-label={t('nav.uploadAria')}
          >
            <Plus size={24} strokeWidth={2} color="var(--accent-fg)" />
          </button>
          <span className="mt-1 text-label text-transparent select-none" aria-hidden="true">.</span>
        </div>

        <NavLink to="/notifications" className={navItem}>
          <span className="relative">
            <Bell size={22} strokeWidth={1.75} />
            {unreadCount > 0 && (
              <span
                className="absolute -top-1 -right-1 h-2 w-2 rounded-pill bg-danger ring-2 ring-theme-surface"
                aria-label={t('nav.unreadAria', { count: unreadCount })}
              />
            )}
          </span>
          <span>{t('nav.notifications')}</span>
        </NavLink>

        <NavLink to="/profile" className={navItem}>
          <UserCircle size={22} strokeWidth={1.75} />
          <span>{t('nav.profile')}</span>
        </NavLink>
      </div>
    </nav>
  )
}
