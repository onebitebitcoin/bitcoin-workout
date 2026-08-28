import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, lazy, Suspense } from 'react'
import { Toaster } from 'react-hot-toast'
import { useAuthStore } from './store/auth'
import client from './api/client'
import type { User } from './api/types'
import { useVersionCheck } from './hooks/useVersionCheck'
import UpdateBanner from './components/UpdateBanner'
import BottomNav from './components/BottomNav'
import SideNav from './components/SideNav'
import LoadingScreen from './components/LoadingScreen'
import { isFlutterWebView } from './lib/platform'

// 초기 번들에 포함 (첫 화면 + 자주 방문하는 페이지)
import FeedPage from './pages/FeedPage'
import LoginPage from './pages/LoginPage'
import UserProfilePage from './pages/UserProfilePage'

// 나머지는 lazy load
const UploadPage = lazy(() => import('./pages/UploadPage'))
const ChallengePage = lazy(() => import('./pages/ChallengePage'))
const ChallengeCreatePage = lazy(() => import('./pages/ChallengeCreatePage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const AdminPage = lazy(() => import('./pages/AdminPage'))
const TermsPage = lazy(() => import('./pages/TermsPage'))
const TeamPage = lazy(() => import('./pages/TeamPage'))
const SetupUsernamePage = lazy(() => import('./pages/SetupUsernamePage'))
const MyChallengeDashboardPage = lazy(() => import('./pages/MyChallengeDashboardPage'))
const ChallengeDashboardPage = lazy(() => import('./pages/ChallengeDashboardPage'))
const ChallengeDetailPage = lazy(() => import('./pages/ChallengeDetailPage'))
const ChallengeEditPage = lazy(() => import('./pages/ChallengeEditPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const SharedVideoPage = lazy(() => import('./pages/SharedVideoPage'))
const LightningWalletGuidePage = lazy(() => import('./pages/LightningWalletGuidePage'))
const NotificationsPage = lazy(() => import('./pages/NotificationsPage'))
const PostDetailPage = lazy(() => import('./pages/PostDetailPage'))
const PostEditPage = lazy(() => import('./pages/PostEditPage'))
const FollowListPage = lazy(() => import('./pages/FollowListPage'))
const InvitePage = lazy(() => import('./pages/InvitePage'))
const LightningLoginPage = lazy(() => import('./pages/LightningLoginPage'))
const EmailLoginPage = lazy(() => import('./pages/EmailLoginPage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))
const SurveyPage = lazy(() => import('./pages/SurveyPage'))
const AdminSurveysListPage = lazy(() => import('./pages/AdminSurveysListPage'))
const AdminSurveyEditorPage = lazy(() => import('./pages/AdminSurveyEditorPage'))
const AdminSurveyResponsesPage = lazy(() => import('./pages/AdminSurveyResponsesPage'))

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

const HIDE_NAV = ['/login', '/login/lightning', '/login/email', '/login/register', '/admin', '/terms', '/team', '/setup-username', '/lightning-guide']
const HIDE_NAV_PREFIXES = ['/shorts/', '/survey/']
const KNOWN_ROUTE_SEGMENTS = new Set([
  'login', 'upload', 'challenges', 'my-challenges',
  'profile', 'setup-username', 'users', 'admin', 'terms',
  'settings', 'team', 'share', 'register', 'lightning-guide',
  'notifications', 'posts', 'survey', 'invite',
])

function Layout() {
  const location = useLocation()
  const { pathname } = location
  const segments = pathname.split('/').filter(Boolean)
  const isShareRoute = segments.length === 1 && !KNOWN_ROUTE_SEGMENTS.has(segments[0])
  const hideNav = HIDE_NAV.includes(pathname) || isShareRoute || HIDE_NAV_PREFIXES.some((p) => pathname.startsWith(p))
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)
  const { token, setUser } = useAuthStore()

  // 초대 링크(?ref=CODE) 캡처 — 가입 경로와 무관하게 localStorage에 보관
  useEffect(() => {
    const ref = new URLSearchParams(location.search).get('ref')
    if (ref) {
      try { localStorage.setItem('referral_code', ref) } catch { /* ignore */ }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!token) return
    client
      .get<{ data: User }>('/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((res) => setUser(res.data.data))
      .catch(() => undefined)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const hash = location.hash.slice(1)
    const params = new URLSearchParams(hash)
    const googleToken = params.get('google_token')
    if (!googleToken) return
    const googleRefresh = params.get('google_refresh') ?? ''
    const isNew = params.get('new_user') === '1'
    if (isNew) {
      window.history.replaceState({}, '', '/')
      navigate(`/setup-username?token=${encodeURIComponent(googleToken)}&refresh=${encodeURIComponent(googleRefresh)}`, { replace: true })
      return
    }
    client
      .get<{ data: User }>('/auth/me', {
        headers: { Authorization: `Bearer ${googleToken}` },
      })
      .then((res) => {
        login(googleToken, res.data.data, googleRefresh)
        window.history.replaceState({}, '', '/')
        navigate('/', { replace: true })
      })
      .catch(() => {
        window.history.replaceState({}, '', '/login?error=google_auth_failed')
        navigate('/login?error=google_auth_failed', { replace: true })
      })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const isFlutter = isFlutterWebView()
  const { updateAvailable, serverVersion } = useVersionCheck()

  const showNav = !hideNav && !isFlutter

  return (
    <div className="relative h-full">
      {showNav && <SideNav />}
      {updateAvailable && !isFlutter && <UpdateBanner serverVersion={serverVersion} />}
      <div key={location.key} className={`absolute inset-0 overflow-y-auto page-enter${showNav ? ' lg:left-60' : ''}`}>
      <Suspense fallback={<LoadingScreen />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/login/lightning" element={<LightningLoginPage />} />
        <Route path="/login/email" element={<EmailLoginPage />} />
        <Route path="/login/register" element={<RegisterPage />} />
        <Route path="/" element={<RequireAuth><FeedPage /></RequireAuth>} />
        <Route path="/upload" element={<RequireAuth><UploadPage /></RequireAuth>} />
        <Route path="/challenges" element={<RequireAuth><ChallengePage /></RequireAuth>} />
        <Route path="/challenges/create" element={<RequireAuth><ChallengeCreatePage /></RequireAuth>} />
        <Route path="/challenges/:id" element={<RequireAuth><ChallengeDetailPage /></RequireAuth>} />
        <Route path="/challenges/:id/edit" element={<RequireAuth><ChallengeEditPage /></RequireAuth>} />
        <Route path="/my-challenges" element={<RequireAuth><MyChallengeDashboardPage /></RequireAuth>} />
        <Route path="/challenges/:id/dashboard" element={<RequireAuth><ChallengeDashboardPage /></RequireAuth>} />
        <Route path="/profile" element={<RequireAuth><ProfilePage /></RequireAuth>} />
        <Route path="/setup-username" element={<SetupUsernamePage />} />
        <Route path="/users/:userId" element={<RequireAuth><UserProfilePage /></RequireAuth>} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/settings" element={<RequireAuth><SettingsPage /></RequireAuth>} />
        <Route path="/team" element={<TeamPage />} />
        <Route path="/shorts/:shareToken" element={<SharedVideoPage />} />
        <Route path="/lightning-guide" element={<LightningWalletGuidePage />} />
        <Route path="/notifications" element={<RequireAuth><NotificationsPage /></RequireAuth>} />
        <Route path="/posts/:postId" element={<RequireAuth><PostDetailPage /></RequireAuth>} />
        <Route path="/posts/:postId/edit" element={<RequireAuth><PostEditPage /></RequireAuth>} />
        <Route path="/users/:userId/followers" element={<RequireAuth><FollowListPage mode="followers" /></RequireAuth>} />
        <Route path="/users/:userId/following" element={<RequireAuth><FollowListPage mode="following" /></RequireAuth>} />
        <Route path="/invite" element={<RequireAuth><InvitePage /></RequireAuth>} />
        <Route path="/survey/:slug" element={<SurveyPage />} />
        <Route path="/admin/surveys" element={<AdminSurveysListPage />} />
        <Route path="/admin/surveys/new" element={<AdminSurveyEditorPage />} />
        <Route path="/admin/surveys/:id/edit" element={<AdminSurveyEditorPage />} />
        <Route path="/admin/surveys/:id/responses" element={<AdminSurveyResponsesPage />} />
        <Route path="/feed" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
      </div>
      {showNav && <BottomNav />}
      <Toaster
        position="top-center"
        toastOptions={{
          duration: 2000,
          style: {
            background: 'var(--bg-surface)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
            fontSize: '14px',
            fontFamily: "'IBM Plex Sans KR', 'Apple SD Gothic Neo', sans-serif",
          },
        }}
      />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  )
}
