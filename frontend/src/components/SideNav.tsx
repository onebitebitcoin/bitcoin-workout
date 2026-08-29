import { NavLink, useNavigate } from 'react-router-dom'
import { Home, Plus, UserCircle, Target, Bell } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../store/auth'
import LogoMark from './LogoMark'
import { useUnreadNotifications } from '../hooks/useUnreadNotifications'

export default function SideNav() {
  const navigate = useNavigate()
  const { t } = useTranslation('common')
  const token = useAuthStore((s) => s.token)
  const unreadCount = useUnreadNotifications()

  function handleUpload() {
    navigate(token ? '/upload' : '/login')
  }

  const navItem = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-card px-4 py-3 text-body font-medium transition-colors ${
      isActive
        ? 'bg-theme-surface2 text-accent-text'
        : 'text-theme-muted hover:bg-theme-surface2 hover:text-theme-primary'
    }`

  return (
    <nav className="fixed left-0 top-0 z-50 hidden h-full w-60 flex-col border-r border-theme-border bg-theme-surface lg:flex">
      {/* 로고 */}
      <div className="flex items-center gap-2 px-6 py-5">
        <LogoMark size={28} className="text-accent" />
        <span className="text-title text-theme-primary">Orange Story</span>
      </div>

      {/* 네비게이션 항목 */}
      <div className="flex flex-1 flex-col gap-1 px-3">
        <NavLink to="/" end className={navItem}>
          <Home size={20} strokeWidth={1.5} />
          <span>{t('nav.feed')}</span>
        </NavLink>

        <NavLink to="/challenges" className={navItem}>
          <Target size={20} strokeWidth={1.5} />
          <span>{t('nav.challenges')}</span>
        </NavLink>

        <button
          onClick={handleUpload}
          className="flex items-center gap-3 rounded-card px-4 py-3 text-body font-medium text-theme-muted transition-colors hover:bg-theme-surface2 hover:text-theme-primary"
          aria-label={t('nav.uploadAria')}
        >
          <Plus size={20} strokeWidth={1.5} />
          <span>{t('nav.upload')}</span>
        </button>


        <NavLink to="/notifications" className={navItem}>
          <span className="relative">
            <Bell size={20} strokeWidth={1.5} />
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
          <UserCircle size={20} strokeWidth={1.5} />
          <span>{t('nav.profile')}</span>
        </NavLink>
      </div>
    </nav>
  )
}
