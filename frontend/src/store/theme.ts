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
  // 삭제된 구 테마(volt-light/arctic/forest)가 localStorage에 남아 있거나
  // 아예 없던 이름이 들어와도 여기서 기본 테마로 떨어진다.
  const t: Theme = THEMES.includes(candidate as Theme) ? (candidate as Theme) : 'bitcoin'
  document.documentElement.setAttribute('data-theme', t)
  if (t !== useThemeStore.getState().theme) {
    useThemeStore.getState().setTheme(t)
  }
}
