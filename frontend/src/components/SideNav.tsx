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
    `flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-colors ${
      isActive
        ? 'bg-theme-surface2 text-accent-text'
        : 'text-theme-subtle hover:bg-theme-surface2 hover:text-theme-primary'
    }`

  return (
    <nav className="fixed left-0 top-0 z-50 hidden h-full w-60 flex-col border-r border-theme-border bg-theme-surface lg:flex">
      {/* 로고 */}
      <div className="flex items-center gap-2 px-6 py-5">
        <LogoMark size={28} className="text-accent" />
        <span className="text-base font-bold text-theme-primary">Bitcoiners</span>
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
          className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium text-theme-subtle transition-colors hover:bg-theme-surface2 hover:text-theme-primary"
          aria-label={t('nav.uploadAria')}
        >
          <Plus size={20} strokeWidth={1.5} />
          <span>{t('nav.upload')}</span>
        </button>


        <NavLink to="/notifications" className={navItem}>
          <span className="relative">
            <Bell size={20} strokeWidth={1.5} />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
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
