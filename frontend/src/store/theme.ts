import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const THEMES = ['bitcoin', 'sapphire', 'volt', 'indigo'] as const
export type Theme = (typeof THEMES)[number]

export const THEME_LABELS: Record<Theme, string> = {
  bitcoin: 'Bitcoin',
  sapphire: 'Sapphire',
  volt: 'Volt',
  indigo: 'Royal Indigo',
}

interface ThemeState {
  theme: Theme
  setTheme: (t: Theme) => void
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: 'bitcoin',
      setTheme: (theme) => {
        document.documentElement.setAttribute('data-theme', theme)
        set({ theme })
      },
    }),
    { name: 'app-theme' },
  ),
)

export function initTheme(override?: string | null) {
  const stored = useThemeStore.getState().theme
  const candidate = override && THEMES.includes(override as Theme) ? (override as Theme) : stored
  // 저장된 테마가 구 라이트 테마이면 기본 다크로 마이그레이션
  const t: Theme = THEMES.includes(candidate as Theme) ? (candidate as Theme) : 'bitcoin'
  document.documentElement.setAttribute('data-theme', t)
  if (t !== useThemeStore.getState().theme) {
    useThemeStore.getState().setTheme(t)
  }
}
